"""
O que as duas barras de filtro têm em comum (CLAUDE.md, robustez do fluxo).

Perfis e contratos filtram por coisas diferentes, mas compartilham a mecânica:
busca por texto, recorte por quem cadastrou, faixas de data e "parado há tanto
tempo". Isso mora aqui; o que é específico de cada tela fica no app dela.

Duas regras valem para toda a família:

1. **Campo vazio não filtra.** A barra inteira em branco devolve a lista inteira.
2. **Data inválida não some com a lista.** O campo mostra o erro e é ignorado no
   `WHERE`; filtrar por um valor que a pessoa não digitou seria pior do que não
   filtrar.
"""

from datetime import timedelta

from django import forms
from django.db import models
from django.db.models import Q
from django.utils import timezone

from contrapartes.models import apenas_digitos
from solicitacoes.campos import DataBRField

#: Faixas de "sem movimento há", em dias. É o filtro que revela o que travou na
#: esteira: o registro parado não muda de status sozinho, então ninguém o procura.
OPCOES_PARADO = [
    ("", "Qualquer tempo"),
    ("3", "Mais de 3 dias"),
    ("7", "Mais de 7 dias"),
    ("15", "Mais de 15 dias"),
    ("30", "Mais de 30 dias"),
]

OPCOES_SIM_NAO = [("", "Tanto faz"), ("sim", "Sim"), ("nao", "Não")]


class SelecaoMultipla(forms.CheckboxSelectMultiple):
    """Caixas de seleção que o CSS empilha dentro de um `details`."""

    def __init__(self, attrs=None):
        padrao = {"class": "selecao-multipla"}
        padrao.update(attrs or {})
        super().__init__(padrao)


class FiltroBase(forms.Form):
    """Base das barras de filtro. A tela concreta declara o resto."""

    #: Caminhos até os campos que a base filtra. A tela sobrescreve se o nome
    #: mudar (perfil guarda `data_criacao`, contrato também, mas nem sempre foi
    #: assim e nem sempre será).
    campo_criacao = "data_criacao"
    campo_movimentacao = "data_atualizacao"
    campo_contraparte = "contraparte"
    campo_criador = "criada_por"

    #: Campos que não contam como "filtro aplicado". Serve para o que é
    #: navegação e não recorte, como a aba de tipo de contrato: escolher uma aba
    #: não deveria acender o aviso de que a lista está filtrada.
    campos_fora_da_contagem = ()

    busca = forms.CharField(
        label="Buscar",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Nome, CPF/CNPJ ou número",
                "autocomplete": "off",
                "class": "campo-busca",
            }
        ),
    )
    #: Escolha vinda do autocomplete: fixa **uma** contraparte, em vez de buscar
    #: por texto parecido. Fica escondido porque quem o preenche é a sugestão
    #: clicada, e a tela mostra o nome escolhido como etiqueta removível.
    contraparte = forms.IntegerField(required=False, widget=forms.HiddenInput)
    criador = forms.ChoiceField(label="Cadastrado por", required=False, choices=[])
    # Cada ponta da faixa se explica sozinha: "até" como rótulo depende de o
    # campo anterior estar do lado, e a grade quebra a linha onde couber.
    criado_de = DataBRField(label="Cadastrado a partir de", required=False)
    criado_ate = DataBRField(label="Cadastrado até", required=False)
    movimentado_de = DataBRField(label="Movimentado a partir de", required=False)
    movimentado_ate = DataBRField(label="Movimentado até", required=False)
    parado = forms.ChoiceField(label="Sem movimento há", required=False, choices=OPCOES_PARADO)

    def __init__(self, dados=None, *, visiveis=None, **kwargs):
        """`visiveis` é o queryset que o usuário pode ver, antes de filtrar.

        As opções de "cadastrado por" saem dele, não da tabela de usuários
        inteira: oferecer um nome que não tem registro nenhum na lista devolve
        tela vazia e parece defeito.
        """
        super().__init__(dados or None, **kwargs)
        self.visiveis = visiveis
        self.fields["criador"].choices = self._opcoes_de_criador()

        # `is_valid()` uma vez só, no começo: os métodos de filtro leem
        # `cleaned_data` e ele só existe depois da validação.
        self.is_valid()

    def _opcoes_de_criador(self):
        if self.visiveis is None:
            return [("", "Qualquer pessoa")]

        from contas.models import Usuario

        ids = self.visiveis.values_list(f"{self.campo_criador}_id", flat=True).distinct()
        pessoas = Usuario.objects.filter(pk__in=ids).order_by("first_name", "username")
        return [("", "Qualquer pessoa")] + [
            (str(pessoa.pk), pessoa.get_full_name() or pessoa.get_username()) for pessoa in pessoas
        ]

    # -- Leitura -------------------------------------------------------------

    def valor(self, campo: str):
        """O valor limpo do campo, ou `None` se estiver vazio ou inválido.

        `cleaned_data` nem sempre existe: formulário não vinculado (barra em
        branco) não passa por validação nenhuma. Ler com `getattr` evita
        espalhar `if self.is_bound` por todo lado.
        """
        return getattr(self, "cleaned_data", {}).get(campo) or None

    @property
    def tem_filtro(self) -> bool:
        """Se algum campo está preenchido. A tela usa isso para oferecer "Limpar"."""
        return any(
            self.valor(campo) for campo in self.fields if campo not in self.campos_fora_da_contagem
        )

    @property
    def contraparte_escolhida(self):
        """A contraparte fixada pelo autocomplete, se ainda existir."""
        pk = self.valor("contraparte")
        if not pk:
            return None

        from contrapartes.models import Contraparte

        return Contraparte.objects.filter(pk=pk).first()

    #: Campos que respondem "quando" sem serem data. Moram no painel de datas,
    #: junto das faixas: "sem movimento há 15 dias" é recorte de tempo como
    #: qualquer outro, e separá-lo deles obrigaria a procurar em dois lugares.
    campos_de_tempo = ("parado",)

    @property
    def campos_avancados(self):
        """O que o painel de filtros desenha.

        Ficam de fora a busca (primeira linha, sempre visível), a contraparte
        escolhida (campo escondido, preenchido pelo autocomplete) e o que a tela
        já desenha de outro jeito, como o tipo de contrato, que é aba. Sem essa
        última exclusão o tipo aparecia três vezes na mesma página: aba, campo
        escondido e select do painel, os três com o mesmo `name`.
        """
        fora = ("busca", "contraparte", *self.campos_fora_da_contagem)
        return [campo for campo in self if campo.name not in fora]

    def _eh_de_tempo(self, campo) -> bool:
        return campo.name in self.campos_de_tempo or isinstance(campo.field, forms.DateField)

    @property
    def campos_gerais(self):
        """O que recorta por natureza do registro: situação, etapa, valor, quem."""
        return [campo for campo in self.campos_avancados if not self._eh_de_tempo(campo)]

    @property
    def campos_de_data(self):
        """O que recorta por tempo. Vive num painel próprio (AGENTS.md D56).

        São oito campos e quase todos ficam vazios na maioria dos dias: no meio
        dos demais eles dobravam a altura do painel e escondiam o que se usa
        toda hora. Fechados por padrão, aparecem quando são o assunto.
        """
        return [campo for campo in self.campos_avancados if self._eh_de_tempo(campo)]

    def _quantos_preenchidos(self, campos) -> int:
        return sum(1 for campo in campos if self.valor(campo.name))

    @property
    def filtros_gerais(self) -> int:
        """Quantos filtros gerais estão em vigor. Zero deixa o painel fechado."""
        return self._quantos_preenchidos(self.campos_gerais)

    @property
    def filtros_de_data(self) -> int:
        """Quantos filtros de tempo estão em vigor."""
        return self._quantos_preenchidos(self.campos_de_data)

    def resumo(self):
        """Os filtros em vigor, em texto, para as etiquetas removíveis.

        É o que responde "por que esta lista está curta?" sem obrigar a abrir o
        painel de filtros. A etiqueta do tipo de contrato fica de fora: quem a
        mostra é a aba acesa.
        """
        itens = []
        for nome, campo in self.fields.items():
            if nome in self.campos_fora_da_contagem:
                continue
            valor = self.valor(nome)
            if not valor:
                continue
            itens.append(
                {"campo": nome, "rotulo": campo.label, "texto": self._em_texto(nome, campo, valor)}
            )
        return itens

    def _em_texto(self, nome: str, campo, valor) -> str:
        """O valor do filtro como a pessoa o reconhece, não como o banco o guarda."""
        from operacoes.templatetags.formatacao import data_br, moeda

        if nome == "contraparte":
            escolhida = self.contraparte_escolhida
            return escolhida.nome if escolhida else str(valor)
        if isinstance(campo, forms.DecimalField):
            return moeda(valor)
        if isinstance(campo, forms.DateField):
            return data_br(valor)
        if isinstance(valor, (list, tuple)):
            rotulos = dict(campo.choices)
            return ", ".join(str(rotulos.get(item, item)) for item in valor)
        if getattr(campo, "choices", None) and not isinstance(campo, forms.ModelChoiceField):
            return str(dict(campo.choices).get(valor, valor))
        return str(valor)

    # -- Aplicação -----------------------------------------------------------

    def condicao_de_busca(self, termo: str) -> Q:
        """O que "buscar" quer dizer nesta tela. Cada uma responde a sua."""
        raise NotImplementedError

    def aplicar(self, queryset):
        """Aplica os filtros comuns e depois os da tela."""
        queryset = self._aplicar_comuns(queryset)
        return self._aplicar_proprios(queryset)

    def _aplicar_proprios(self, queryset):
        return queryset

    def _aplicar_comuns(self, queryset):
        termo = self.valor("busca")
        if termo:
            queryset = queryset.filter(self.condicao_de_busca(termo.strip()))

        contraparte = self.valor("contraparte")
        if contraparte:
            queryset = queryset.filter(**{f"{self.campo_contraparte}_id": contraparte})

        criador = self.valor("criador")
        if criador:
            queryset = queryset.filter(**{f"{self.campo_criador}_id": criador})

        queryset = self.entre_datas(queryset, self.campo_criacao, "criado_de", "criado_ate")
        queryset = self.entre_datas(
            queryset, self.campo_movimentacao, "movimentado_de", "movimentado_ate"
        )

        dias = self.valor("parado")
        if dias:
            limite = timezone.now() - timedelta(days=int(dias))
            queryset = queryset.filter(**{f"{self.campo_movimentacao}__lt": limite})

        return queryset

    def entre_datas(self, queryset, campo: str, de: str, ate: str):
        """Faixa fechada nas duas pontas, comparando **data**, não instante.

        Em campo com hora, `__date` é obrigatório: `data_criacao` guarda o
        instante, e um registro criado hoje às 14h ficaria de fora de um filtro
        "até hoje" se a comparação fosse com a meia-noite de hoje. Em campo de
        data pura (a data do evento), o mesmo `__date` é erro de consulta, então
        o tipo do campo decide, e não quem chama.
        """
        inicio, fim = self.valor(de), self.valor(ate)
        if not inicio and not fim:
            return queryset

        alvo = f"{campo}__date" if _guarda_hora(queryset, campo) else campo
        if inicio:
            queryset = queryset.filter(**{f"{alvo}__gte": inicio})
        if fim:
            queryset = queryset.filter(**{f"{alvo}__lte": fim})
        return queryset


def _guarda_hora(queryset, campo: str) -> bool:
    """Se o campo é data com hora. Campo desconhecido é tratado como tal.

    Errar para o lado do `__date` é o lado seguro: em campo com hora, sem ele o
    filtro perde o dia inteiro; em campo de data pura, o Django avisa alto, com
    `FieldError`, em vez de devolver resultado errado em silêncio.
    """
    from django.core.exceptions import FieldDoesNotExist

    try:
        return isinstance(queryset.model._meta.get_field(campo), models.DateTimeField)
    except FieldDoesNotExist:
        return True


#: Menos de quatro dígitos casa com quase todo CPF/CNPJ da base: "1" está em
#: praticamente todos eles. Sequência curta é número de registro, não documento.
MINIMO_DE_DIGITOS_DO_DOCUMENTO = 4


def partes_da_busca(termo: str) -> tuple[int | None, str]:
    """Separa o termo em número de registro e dígitos de documento.

    Procurar "#12" trazia, além do contrato #12, todos os que tivessem "12" em
    algum lugar do CNPJ, que na prática eram todos. Daí as duas regras: `#`
    é pedido explícito de número e não procura mais nada, e documento só entra
    com dígitos suficientes para significar alguma coisa.
    """
    limpo = termo.strip()
    numero = int(limpo.lstrip("#").strip()) if eh_numero_de_registro(limpo) else None

    if limpo.startswith("#"):
        return numero, ""

    digitos = apenas_digitos(limpo)
    return numero, digitos if len(digitos) >= MINIMO_DE_DIGITOS_DO_DOCUMENTO else ""


def eh_numero_de_registro(termo: str) -> bool:
    """Se o termo é o número do registro, com ou sem `#`.

    Só vale quando o termo **inteiro** é o número: senão procurar "2024" traria
    o registro #2024 no meio dos que têm 2024 no texto.
    """
    return termo.lstrip("#").strip().isdigit()


__all__ = [
    "OPCOES_PARADO",
    "OPCOES_SIM_NAO",
    "FiltroBase",
    "SelecaoMultipla",
    "apenas_digitos",
    "eh_numero_de_registro",
    "partes_da_busca",
]
