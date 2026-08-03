"""Formulários de risco e crédito."""

from django import forms

from documentos.validadores import ACCEPT_HTML, validar_documento

from .models import BlocoCredito, EvidenciaCredito, ParecerCredito


class ParecerCreditoForm(forms.ModelForm):
    class Meta:
        model = ParecerCredito
        fields = list(BlocoCredito.values) + [
            "veredito",
            "justificativa",
            "registrado_em_nome_do_time",
        ]
        widgets = {campo: forms.Textarea(attrs={"rows": 3}) for campo in BlocoCredito.values}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["justificativa"].widget = forms.Textarea(attrs={"rows": 3})
        # Validado ao concluir, não ao salvar rascunho.
        self.fields["veredito"].required = False

    @property
    def campos_dos_blocos(self):
        return [self[campo] for campo in BlocoCredito.values]

    @property
    def campos_da_conclusao(self):
        return [self["veredito"], self["justificativa"], self["registrado_em_nome_do_time"]]


class EvidenciaCreditoForm(forms.ModelForm):
    class Meta:
        model = EvidenciaCredito
        fields = ("bloco", "arquivo", "descricao")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivo"].widget.attrs["accept"] = ACCEPT_HTML
        self.fields["arquivo"].help_text = "Print da consulta ou documento. Até 25 MB."

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        validar_documento(arquivo)
        return arquivo
