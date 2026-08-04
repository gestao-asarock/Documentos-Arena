"""
Formulários da Fase 1 (AGENTS.md §4.0).

O formulário de solicitação mistura dados da contraparte e do evento de propósito:
para o Clube é um pedido só. A separação em entidades é problema nosso.
"""

from django import forms

from contrapartes.models import deduzir_tipo_pessoa
from documentos.models import SubtipoDocumento, TipoDocumento, TipoPessoa
from documentos.validadores import ACCEPT_HTML, validar_documento

from .campos import DataBRField, MultiploArquivoField

#: Dito no campo, e não só no `clean`: quem preenche precisa saber por que o
#: asterisco está ali e por que o campo some ao digitar um CNPJ (AGENTS.md D43).
AJUDA_PF = "Obrigatório para pessoa física. Não se aplica a CNPJ."

#: Mostrado no lugar dos dois campos quando o documento é de empresa.
AVISO_PJ = "Data de nascimento e RG não se aplicam a pessoa jurídica."


class SolicitacaoForm(forms.Form):
    """Cadastro do perfil: só o que é da pessoa (AGENTS.md D29).

    Evento, data e valor pertencem ao contrato — sem eles aqui, o mesmo perfil
    serve a quantos contratos vierem.

    Tudo é obrigatório, menos o complemento do endereço (que boa parte dos
    endereços não tem) e os campos que só existem para pessoa física.
    """

    #: Só fazem sentido para CPF. Para CNPJ o JS os esconde e o `clean` os limpa.
    CAMPOS_PF = ("data_nascimento", "rg")

    #: O template ancora o aviso de PJ logo depois do último campo desta lista.
    AVISO_PJ = AVISO_PJ

    #: Renderizados juntos, revelados pelo botão "Preencher endereço".
    CAMPOS_ENDERECO = ("logradouro", "numero", "complemento", "bairro", "cidade", "uf")

    nome = forms.CharField(label="Nome da contraparte", max_length=200)
    documento = forms.CharField(
        label="CPF ou CNPJ",
        max_length=18,
        help_text="O sistema identifica sozinho se é pessoa física ou jurídica.",
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "data-mascara": "documento",
                "data-define-tipo-pessoa": "true",
                "autocomplete": "off",
            }
        ),
    )
    # Obrigatórios só para pessoa física: exigidos no `clean`, não aqui, para
    # que o cadastro de uma empresa não peça data de nascimento nem RG.
    data_nascimento = DataBRField(
        label="Data de nascimento",
        required=False,
        help_text=AJUDA_PF,
        widget=forms.TextInput(attrs={"data-so-pf": "true"}),
    )
    rg = forms.CharField(
        label="RG",
        max_length=20,
        required=False,
        help_text=AJUDA_PF,
        widget=forms.TextInput(attrs={"data-so-pf": "true"}),
    )
    email = forms.EmailField(label="E-mail")
    telefone = forms.CharField(
        label="Telefone",
        max_length=20,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "data-mascara": "telefone"}),
    )

    cep = forms.CharField(
        label="CEP",
        max_length=9,
        help_text="Digite o CEP: o endereço é preenchido sozinho.",
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "data-mascara": "cep",
                "data-busca-cep": "true",
                "placeholder": "00000-000",
                "autocomplete": "off",
            }
        ),
    )
    logradouro = forms.CharField(label="Logradouro", max_length=200)
    numero = forms.CharField(label="Número", max_length=20)
    complemento = forms.CharField(label="Complemento", max_length=100, required=False)
    bairro = forms.CharField(label="Bairro", max_length=100)
    cidade = forms.CharField(label="Cidade", max_length=100)
    uf = forms.CharField(label="UF", max_length=2, widget=forms.TextInput(attrs={"maxlength": "2"}))

    def clean_documento(self) -> str:
        documento = self.cleaned_data["documento"]
        try:
            deduzir_tipo_pessoa(documento)
        except ValueError as erro:
            raise forms.ValidationError(str(erro)) from erro
        return documento

    def clean_uf(self) -> str:
        return self.cleaned_data["uf"].upper()

    def clean(self):
        dados = super().clean()

        documento = dados.get("documento")
        if not documento:
            return dados

        if deduzir_tipo_pessoa(documento) == TipoPessoa.JURIDICA:
            # Empresa não tem nascimento nem RG: o que vier é descartado.
            for campo in self.CAMPOS_PF:
                dados[campo] = None if campo == "data_nascimento" else ""
            return dados

        for campo in self.CAMPOS_PF:
            if not dados.get(campo) and campo not in self.errors:
                self.add_error(campo, "Este campo é obrigatório.")

        return dados

    @property
    def campos_da_pessoa(self) -> list:
        """Bloco de cima do formulário: a contraparte, sem o endereço."""
        endereco = ("cep", *self.CAMPOS_ENDERECO)
        return [campo for campo in self if campo.name not in endereco]

    @property
    def campos_do_endereco(self) -> list:
        """Bloco revelado pelo botão, depois da busca por CEP."""
        return [self[nome] for nome in self.CAMPOS_ENDERECO]

    @property
    def endereco_preenchido(self) -> bool:
        """Já há endereço na tela? Então ele nasce visível, sem depender do JS.

        É o caso de voltar do servidor com erro de validação: esconder de novo
        o que a pessoa digitou seria esconder também a mensagem de erro.
        """
        return any(campo.value() or campo.errors for campo in self.campos_do_endereco)

    @property
    def dados_da_contraparte(self) -> dict:
        """Campos que pertencem à contraparte, não à solicitação."""
        campos = (
            "nome",
            "data_nascimento",
            "rg",
            "email",
            "telefone",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
        )
        return {campo: self.cleaned_data.get(campo) for campo in campos}


class EnvioDocumentoForm(forms.Form):
    """Envio de um documento do kit cadastral, com um ou vários arquivos."""

    #: Campos que só aparecem para certos tipos de documento. Nascem escondidos
    #: no template e o JS os revela conforme a escolha.
    CAMPOS_CONDICIONAIS = ("subtipo", "data_emissao")

    #: Preenchidos em __init__; o template os usa para configurar o JS.
    tipos_com_subtipo: list[int] = []
    tipos_com_emissao: list[int] = []

    tipo = forms.ModelChoiceField(
        queryset=TipoDocumento.objects.none(),
        label="Documento",
        widget=forms.Select(attrs={"data-controla-campos": "true"}),
    )
    subtipo = forms.ModelChoiceField(
        queryset=SubtipoDocumento.objects.none(),
        label="Qual documento",
        required=False,
        help_text="Obrigatório para documentos de identificação.",
    )
    arquivos = MultiploArquivoField(
        label="Arquivos",
        help_text="PDF, JPG ou PNG, até 25 MB cada. Pode enviar frente e verso juntos.",
    )
    data_emissao = DataBRField(
        label="Data de emissão",
        required=False,
        help_text="Usada para calcular a validade.",
    )

    def __init__(self, *args, tipos_pendentes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivos"].widget.attrs["accept"] = ACCEPT_HTML

        if tipos_pendentes is None:
            return

        ids = [tipo.id for tipo in tipos_pendentes]
        self.fields["tipo"].queryset = TipoDocumento.objects.filter(id__in=ids)
        self.fields["subtipo"].queryset = SubtipoDocumento.objects.filter(
            tipo_documento_id__in=ids, ativo=True
        )

        # O JS usa estes mapas para mostrar apenas os campos que se aplicam ao
        # tipo escolhido — subtipo só para identificação, emissão só onde vale.
        self.tipos_com_subtipo = [
            tipo.id for tipo in tipos_pendentes if tipo.subtipos.filter(ativo=True).exists()
        ]
        self.tipos_com_emissao = [tipo.id for tipo in tipos_pendentes if tipo.exige_data_emissao]
        self.fields["subtipo"].widget.attrs["data-depende-de"] = "identificacao"
        self.fields["data_emissao"].widget.attrs["data-depende-de"] = "emissao"

    def clean_arquivos(self) -> list:
        arquivos = self.cleaned_data["arquivos"]
        for arquivo in arquivos:
            validar_documento(arquivo)
        return arquivos

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        if tipo is None:
            return dados

        subtipo = dados.get("subtipo")
        if tipo.subtipos.filter(ativo=True).exists() and subtipo is None:
            self.add_error("subtipo", "Informe qual documento está sendo enviado.")
        if subtipo is not None and subtipo.tipo_documento_id != tipo.id:
            self.add_error("subtipo", "Este subtipo não pertence ao documento escolhido.")

        # A emissão do RG não define validade alguma; não faz sentido pedir.
        if not tipo.exige_data_emissao:
            dados["data_emissao"] = None

        return dados
