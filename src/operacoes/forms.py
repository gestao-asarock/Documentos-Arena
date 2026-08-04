"""Formulários de operação. Validação de domínio fica no modelo/serviço."""

from django import forms

from contrapartes.models import Contraparte, StatusHabilitacao
from documentos.models import SubtipoDocumento, TipoDocumento
from documentos.validadores import ACCEPT_HTML_COM_DOCX, validar_documento
from solicitacoes.campos import DataBRField, MultiploArquivoField

from .models import TipoOperacao


class OperacaoForm(forms.Form):
    """Contrato: o que acontece, quando e por quanto (AGENTS.md D29).

    A contraparte precisa ter perfil validado; os dados dela não são redigitados
    aqui, porque já foram conferidos na validação do perfil.
    """

    contraparte = forms.ModelChoiceField(
        queryset=Contraparte.objects.none(),
        label="Contraparte",
        help_text="Só aparecem perfis já validados.",
    )
    tipo_operacao = forms.ModelChoiceField(
        queryset=TipoOperacao.objects.filter(ativo=True), label="Tipo de operação"
    )
    descricao = forms.CharField(
        label="Descrição do evento ou serviço",
        max_length=255,
        help_text="Ex.: formatura de balé, ensaio fotográfico, manutenção elétrica.",
    )
    data_evento = DataBRField(label="Data do evento", required=False)
    horario_evento = forms.TimeField(
        label="Horário",
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "hh:mm", "inputmode": "numeric", "data-mascara": "hora"}
        ),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    valor_total = forms.DecimalField(
        label="Valor (R$)",
        max_digits=14,
        decimal_places=2,
        min_value=0.01,
        help_text="Define o enquadramento e os documentos exigidos.",
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "0,00"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contraparte"].queryset = Contraparte.objects.filter(
            ativa=True, habilitacoes__status=StatusHabilitacao.HABILITADA
        ).distinct()


class DecisaoEtapaForm(forms.Form):
    """Decisão humana de uma etapa: sempre com parecer (AGENTS.md §5.1)."""

    parecer = forms.CharField(
        label="Parecer",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Registrado na auditoria junto com seu nome. Obrigatório.",
    )
    aprovar = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def clean_parecer(self) -> str:
        parecer = self.cleaned_data["parecer"].strip()
        if not parecer:
            raise forms.ValidationError("Informe o parecer da decisão.")
        return parecer


class EnvioDocumentoContratoForm(forms.Form):
    """Envia um documento complementar exigido por este contrato.

    O arquivo é guardado **no perfil** da contraparte, não no contrato: assim
    outro contrato do mesmo tipo pode reaproveitá-lo (AGENTS.md D29).
    """

    tipo = forms.ModelChoiceField(queryset=TipoDocumento.objects.none(), label="Documento")
    subtipo = forms.ModelChoiceField(
        queryset=SubtipoDocumento.objects.none(),
        label="Qual documento",
        required=False,
    )
    arquivos = MultiploArquivoField(label="Arquivos", help_text="PDF, JPG ou PNG, até 25 MB cada.")
    data_emissao = DataBRField(
        label="Data de emissão", required=False, help_text="Usada para calcular a validade."
    )

    CAMPOS_CONDICIONAIS = ("subtipo", "data_emissao")

    def __init__(self, *args, operacao=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Documento de contrato aceita DOCX: o Termo de Adesão vem em Word (D32).
        self.fields["arquivos"].widget.attrs["accept"] = ACCEPT_HTML_COM_DOCX
        self.fields["arquivos"].help_text = "PDF, JPG, PNG ou DOCX, até 25 MB cada."
        if operacao is None:
            return

        # Só o que ainda precisa de envio — não o que já está em conferência.
        pendentes = operacao.tipos_a_enviar()
        ids = [tipo.id for tipo in pendentes]
        self.fields["tipo"].queryset = TipoDocumento.objects.filter(id__in=ids)
        self.fields["subtipo"].queryset = SubtipoDocumento.objects.filter(
            tipo_documento_id__in=ids, ativo=True
        )
        self.tipos_com_subtipo = [
            tipo.id for tipo in pendentes if tipo.subtipos.filter(ativo=True).exists()
        ]
        self.tipos_com_emissao = [tipo.id for tipo in pendentes if tipo.exige_data_emissao]
        self.fields["subtipo"].widget.attrs["data-depende-de"] = "identificacao"
        self.fields["data_emissao"].widget.attrs["data-depende-de"] = "emissao"
        self.fields["tipo"].widget.attrs["data-controla-campos"] = "true"

    def clean_arquivos(self) -> list:
        arquivos = self.cleaned_data["arquivos"]
        for arquivo in arquivos:
            validar_documento(arquivo, aceitar_docx=True)
        return arquivos

    def clean(self):
        dados = super().clean()
        tipo = dados.get("tipo")
        if tipo is None:
            return dados

        if tipo.subtipos.filter(ativo=True).exists() and dados.get("subtipo") is None:
            self.add_error("subtipo", "Informe qual documento está sendo enviado.")
        if not tipo.exige_data_emissao:
            dados["data_emissao"] = None
        return dados


class VincularDocumentosForm(forms.Form):
    """Escolhe, entre os documentos já validados do perfil, os que atendem ao contrato.

    O documento pertence ao perfil: usá-lo aqui não o consome, apenas o vincula —
    é o que permite reaproveitá-lo em contratos futuros (AGENTS.md D29).
    """

    def __init__(self, *args, operacao=None, **kwargs):
        super().__init__(*args, **kwargs)
        if operacao is None:
            return

        # Só oferece reaproveitamento para o que ainda falta.
        exigidos = operacao.tipos_a_enviar()
        disponiveis = operacao.contraparte.documentos_validos_de(exigidos)
        vinculados = {d.id for d in operacao.documentos.all()}

        for tipo in exigidos:
            opcoes = disponiveis.get(tipo.id, [])
            campo = forms.ModelMultipleChoiceField(
                queryset=operacao.contraparte.documentos_cadastrais.filter(
                    id__in=[d.id for d in opcoes]
                ),
                required=False,
                label=tipo.nome,
                widget=forms.CheckboxSelectMultiple,
                initial=[d.id for d in opcoes if d.id in vinculados],
                help_text=(
                    "Nenhum documento validado deste tipo — envie um novo abaixo."
                    if not opcoes
                    else "Documentos já validados no perfil."
                ),
            )
            self.fields[f"tipo_{tipo.id}"] = campo

    def documentos_escolhidos(self) -> list:
        escolhidos = []
        for nome, valor in self.cleaned_data.items():
            if nome.startswith("tipo_"):
                escolhidos.extend(valor)
        return escolhidos
