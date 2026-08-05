"""Formulários de risco e crédito."""

from django import forms

from documentos.validadores import ACCEPT_HTML_SO_PDF, validar_pdf
from solicitacoes.campos import MultiploArquivoField

from .models import ParecerCredito


class ParecerCreditoForm(forms.ModelForm):
    class Meta:
        model = ParecerCredito
        # `registrado_em_nome_do_time` existe no modelo (D9) mas ficou fora da
        # tela: é sempre verdadeiro enquanto o time de Risco não for usuário, e
        # uma caixa que ninguém desmarca só ocupa espaço. Volta se o time entrar.
        fields = ["veredito", "justificativa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["justificativa"].widget = forms.Textarea(attrs={"rows": 3})
        self.fields["justificativa"].label = "Justificativa (opcional)"
        # Validado ao concluir, não ao salvar rascunho.
        self.fields["veredito"].required = False


class RelatorioCreditoForm(forms.Form):
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
