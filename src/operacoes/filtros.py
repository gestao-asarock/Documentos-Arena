"""
A barra de filtros da lista de contratos (CLAUDE.md, robustez do fluxo).

Uma tabela sem recorte funciona com trinta contratos e deixa de funcionar com
trezentos: quem procura um caso específico rola a página até achar, e quem
precisa saber o que travou não tem como perguntar. Aqui estão as perguntas que a
tela sabe responder.

Tudo o que filtra é coluna do banco ou vem de `consultas.com_etapa_atual`.
Nenhum filtro carrega os registros em memória para decidir: paginação e recorte
precisam concordar, e um filtro em Python quebraria a contagem da página.
"""

from django import forms
from django.db.models import Count, Exists, OuterRef, Q

from arena.filtros import OPCOES_SIM_NAO, FiltroBase, SelecaoMultipla, partes_da_busca
from contrapartes.models import DocumentoCadastral
from documentos.models import StatusDocumento
from solicitacoes.campos import DataBRField, MoedaBRField

from .estados import Etapa, StatusOperacao
from .models import RegraEnquadramento, TipoOperacao

#: Chave da URL para os campos do banco por onde ela ordena. Só o que está aqui
#: pode ser ordenado: o resto da URL é ignorado (arena/listagem.py).
COLUNAS = {
    "numero": ("pk",),
    "contraparte": ("contraparte__nome",),
    "tipo": ("tipo_operacao__nome",),
    "valor": ("valor_total",),
    "enquadramento": ("regra__criterio",),
    "situacao": ("status",),
    "etapa": ("etapa_atual_ordem",),
    "evento": ("data_evento",),
    "criacao": ("data_criacao",),
    "movimentacao": ("data_atualizacao",),
}

#: Mais recentes primeiro, como já era antes de existir barra de filtros.
ORDEM_PADRAO = "-criacao"

#: Os três estados que o documento pode ter aos olhos de quem vê a lista. São
#: perguntas sobre **o que está gravado**, e é por isso que cada uma cabe numa
#: cláusula de SQL. "Falta documento" é o próprio estado do contrato: é assim
#: que a máquina de estados registra a espera (operacoes/estados.py).
DOC_FALTA = "falta"
DOC_RECUSADO = "recusado"
DOC_CONFERENCIA = "conferencia"
DOC_APROVADO = "aprovado"

OPCOES_DOCUMENTACAO = [
    ("", "Qualquer situação"),
    (DOC_FALTA, "Falta documento"),
    (DOC_RECUSADO, "Documento recusado"),
    (DOC_CONFERENCIA, "Aguardando conferência"),
    (DOC_APROVADO, "Tudo aprovado"),
]

#: Recusado de verdade: precisa de ação do Clube para o contrato andar.
STATUS_RECUSADOS = (StatusDocumento.REJEITADO, StatusDocumento.FALHA_ANALISE)
#: Entregue e ainda sem decisão humana.
STATUS_EM_CONFERENCIA = (
    StatusDocumento.ENVIADO,
    StatusDocumento.PROCESSANDO,
    StatusDocumento.ANALISADO,
)


class FiltroOperacoes(FiltroBase):
    """Os recortes da lista de contratos."""

    #: O tipo é a aba, não um filtro qualquer: escolher uma aba não deveria
    #: acender o aviso de "há filtros aplicados".
    campos_fora_da_contagem = ("tipo",)

    #: O painel de filtros é lido de cima para baixo: primeiro o que recorta o
    #: trabalho (situação, etapa, dinheiro), depois quem e quando.
    field_order = [
        "situacao",
        "etapa",
        "documentacao",
        "enquadramento",
        "valor_de",
        "valor_ate",
        "evento_de",
        "evento_ate",
        "parado",
        "criador",
        "parte_relacionada",
        "criado_de",
        "criado_ate",
        "movimentado_de",
        "movimentado_ate",
    ]

    tipo = forms.ModelChoiceField(
        label="Tipo de contrato",
        required=False,
        queryset=TipoOperacao.objects.filter(ativo=True).order_by("nome"),
    )
    situacao = forms.MultipleChoiceField(
        label="Situação",
        required=False,
        choices=StatusOperacao.choices,
        widget=SelecaoMultipla,
    )
    etapa = forms.MultipleChoiceField(
        label="Etapa atual",
        required=False,
        choices=Etapa.choices,
        widget=SelecaoMultipla,
    )
    enquadramento = forms.ModelChoiceField(
        label="Enquadramento",
        required=False,
        queryset=RegraEnquadramento.objects.filter(ativa=True).order_by("criterio"),
    )
    valor_de = MoedaBRField(label="Valor mínimo", required=False)
    valor_ate = MoedaBRField(label="Valor máximo", required=False)
    evento_de = DataBRField(label="Evento a partir de", required=False)
    evento_ate = DataBRField(label="Evento até", required=False)
    documentacao = forms.ChoiceField(
        label="Documentação", required=False, choices=OPCOES_DOCUMENTACAO
    )
    parte_relacionada = forms.ChoiceField(
        label="Parte relacionada", required=False, choices=OPCOES_SIM_NAO
    )

    def condicao_de_busca(self, termo: str) -> Q:
        """Número do contrato, nome ou CPF/CNPJ da contraparte, ou a descrição.

        O documento é comparado só por dígitos: quem cola de outra tela traz a
        pontuação junto, e o banco guarda sem ela. Quem decide o que é número e o
        que é documento é `partes_da_busca` (arena/filtros.py).
        """
        condicao = Q(contraparte__nome__icontains=termo) | Q(descricao__icontains=termo)

        numero, digitos = partes_da_busca(termo)
        if numero is not None:
            condicao |= Q(pk=numero)
        if digitos:
            condicao |= Q(contraparte__documento__contains=digitos)

        return condicao

    def _aplicar_proprios(self, queryset):
        if tipo := self.valor("tipo"):
            queryset = queryset.filter(tipo_operacao=tipo)
        if situacoes := self.valor("situacao"):
            queryset = queryset.filter(status__in=situacoes)
        if etapas := self.valor("etapa"):
            # Vem de `com_etapa_atual`: a mesma regra de `Operacao.etapa_atual`,
            # escrita em SQL para caber num WHERE (operacoes/consultas.py).
            queryset = queryset.filter(etapa_atual_codigo__in=etapas)
        if regra := self.valor("enquadramento"):
            queryset = queryset.filter(regra=regra)

        if (minimo := self.valor("valor_de")) is not None:
            queryset = queryset.filter(valor_total__gte=minimo)
        if (maximo := self.valor("valor_ate")) is not None:
            queryset = queryset.filter(valor_total__lte=maximo)

        queryset = self.entre_datas(queryset, "data_evento", "evento_de", "evento_ate")

        if relacionada := self.valor("parte_relacionada"):
            queryset = queryset.filter(contraparte__parte_relacionada=relacionada == "sim")

        return self._por_documentacao(queryset)

    def _por_documentacao(self, queryset):
        """Recorta pelo estado dos documentos **vinculados ao contrato**.

        "Falta documento" é o estado do próprio contrato, e não uma contagem de
        arquivos: a exigência documental depende do enquadramento e da faixa de
        valor da contraparte, e quem já resolveu essa conta é a máquina de
        estados, ao gravar `AGUARDANDO_DOCUMENTOS` (operacoes/servicos.avancar).
        """
        escolha = self.valor("documentacao")
        if not escolha:
            return queryset

        do_contrato = DocumentoCadastral.objects.filter(operacoes=OuterRef("pk"))

        if escolha == DOC_FALTA:
            return queryset.filter(status=StatusOperacao.AGUARDANDO_DOCUMENTOS)
        if escolha == DOC_RECUSADO:
            return queryset.filter(Exists(do_contrato.filter(status__in=STATUS_RECUSADOS)))
        if escolha == DOC_CONFERENCIA:
            return queryset.filter(Exists(do_contrato.filter(status__in=STATUS_EM_CONFERENCIA)))
        if escolha == DOC_APROVADO:
            return queryset.filter(
                Exists(do_contrato),
                ~Exists(do_contrato.exclude(status=StatusDocumento.APROVADO)),
            )
        return queryset


def montar_abas(dados, visiveis, escolhido):
    """As abas de tipo de contrato, cada uma com a sua contagem.

    A contagem respeita **os outros filtros**, e não o tipo: a pergunta que a
    aba responde é "quantos dos que estou vendo são de aluguel?". Contar sobre a
    lista inteira faria a soma das abas não bater com o que está na tela.

    Tipo sem nenhum contrato continua aparecendo, com zero: a aba é a divisão do
    trabalho, e uma que some quando esvazia esconde que o tipo existe.
    """
    dados_sem_tipo = dados.copy()
    dados_sem_tipo.pop("tipo", None)
    sem_tipo = FiltroOperacoes(dados_sem_tipo, visiveis=visiveis).aplicar(visiveis)

    contagem = dict(
        sem_tipo.order_by().values_list("tipo_operacao_id").annotate(quantos=Count("pk"))
    )

    abas = [
        {
            "tipo": None,
            "rotulo": "Todos",
            "total": sum(contagem.values()),
            "ativa": escolhido is None,
        }
    ]
    for tipo in TipoOperacao.objects.filter(ativo=True).order_by("nome"):
        abas.append(
            {
                "tipo": tipo,
                "rotulo": tipo.nome,
                "total": contagem.get(tipo.pk, 0),
                "ativa": escolhido == tipo,
            }
        )
    return abas


__all__ = ["COLUNAS", "ORDEM_PADRAO", "FiltroOperacoes", "montar_abas"]
