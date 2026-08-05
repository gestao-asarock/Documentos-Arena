"""Formulários de due diligence."""

from django import forms

from documentos.validadores import ACCEPT_HTML_SO_PDF, validar_pdf
from solicitacoes.campos import MultiploArquivoField

from .models import ParecerCompliance


class ParecerForm(forms.ModelForm):
    class Meta:
        model = ParecerCompliance
        # `comunicado_ao_coaf` existe no modelo mas ficou fora da tela: não altera
        # o fluxo e confunde quem preenche. Volta quando o compliance definir se
        # quer registrar a comunicação por aqui (P9 no CLAUDE.md).
        fields = ["veredito", "justificativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["justificativa"].widget = forms.Textarea(attrs={"rows": 3})
        self.fields["justificativa"].label = "Justificativa (opcional)"
        # O veredito é validado ao concluir, não ao salvar rascunho.
        self.fields["veredito"].required = False


class RelatorioForm(forms.Form):
    """Um ou mais PDFs de relatório, enviados de uma vez."""

    arquivos = MultiploArquivoField(
        label="Relatório",
        help_text="Somente PDF, até 25 MB cada. Pode enviar mais de um arquivo.",
    )
    descricao = forms.CharField(
        label="Comentário (opcional)",
        max_length=255,
        required=False,
        help_text="Vale para todos os arquivos deste envio.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivos"].widget.attrs["accept"] = ACCEPT_HTML_SO_PDF

    def clean_arquivos(self) -> list:
        arquivos = self.cleaned_data["arquivos"]
        for arquivo in arquivos:
            validar_pdf(arquivo)
        return arquivos
