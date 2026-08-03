"""
Formulários da Fase 1 (AGENTS.md §4.0).

O formulário de solicitação mistura dados da contraparte e do evento de propósito:
para o Clube é um pedido só. A separação em entidades é problema nosso.
"""

from django import forms

from contrapartes.models import deduzir_tipo_pessoa
from documentos.models import SubtipoDocumento, TipoDocumento
from documentos.validadores import ACCEPT_HTML, validar_documento

from .campos import DataBRField, MultiploArquivoField


class SolicitacaoForm(forms.Form):
    """Cadastro do perfil: só o que é da pessoa (AGENTS.md D29).

    Evento, data e valor pertencem ao contrato — sem eles aqui, o mesmo perfil
    serve a quantos contratos vierem.
    """

    nome = forms.CharField(label="Nome da contraparte", max_length=200)
    documento = forms.CharField(
        label="CPF ou CNPJ",
        max_length=18,
        help_text="O sistema identifica sozinho se é pessoa física ou jurídica.",
        widget=forms.TextInput(
            attrs={"inputmode": "numeric", "data-mascara": "documento", "autocomplete": "off"}
        ),
    )
    data_nascimento = DataBRField(label="Data de nascimento", required=False)
    rg = forms.CharField(label="RG", max_length=20, required=False)
    email = forms.EmailField(label="E-mail", required=False)
    telefone = forms.CharField(
        label="Telefone",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "data-mascara": "telefone"}),
    )

    cep = forms.CharField(
        label="CEP",
        max_length=9,
        required=False,
        help_text="Preenche o endereço automaticamente.",
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
    logradouro = forms.CharField(label="Logradouro", max_length=200, required=False)
    numero = forms.CharField(label="Número", max_length=20, required=False)
    complemento = forms.CharField(label="Complemento", max_length=100, required=False)
    bairro = forms.CharField(label="Bairro", max_length=100, required=False)
    cidade = forms.CharField(label="Cidade", max_length=100, required=False)
    uf = forms.CharField(
        label="UF", max_length=2, required=False, widget=forms.TextInput(attrs={"maxlength": "2"})
    )

    #: Campos que abrem um bloco novo no formulário, com título.
    BLOCOS = {"cep": "Endereço"}

    def clean_documento(self) -> str:
        documento = self.cleaned_data["documento"]
        try:
            deduzir_tipo_pessoa(documento)
        except ValueError as erro:
            raise forms.ValidationError(str(erro)) from erro
        return documento

    def clean_uf(self) -> str:
        return self.cleaned_data["uf"].upper()

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
