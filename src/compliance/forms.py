"""Formulários de due diligence."""

from django import forms

from documentos.validadores import ACCEPT_HTML, validar_documento

from .models import BlocoParecer, EvidenciaParecer, ParecerCompliance


class ParecerForm(forms.ModelForm):
    class Meta:
        model = ParecerCompliance
        # `comunicado_ao_coaf` existe no modelo mas ficou fora da tela: não altera
        # o fluxo e confunde quem preenche. Volta quando o compliance definir se
        # quer registrar a comunicação por aqui (P9 no CLAUDE.md).
        fields = list(BlocoParecer.values) + [
            "termos_pesquisados",
            "veredito",
            "justificativa",
        ]
        widgets = {campo: forms.Textarea(attrs={"rows": 3}) for campo in BlocoParecer.values}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["justificativa"].widget = forms.Textarea(attrs={"rows": 3})
        # O veredito é validado ao concluir, não ao salvar rascunho.
        self.fields["veredito"].required = False

    @property
    def campos_dos_blocos(self):
        """Os blocos de verificação, para o template renderizar em seção própria."""
        return [self[campo] for campo in BlocoParecer.values]

    @property
    def campos_da_conclusao(self):
        return [self["termos_pesquisados"], self["veredito"], self["justificativa"]]


class EvidenciaForm(forms.ModelForm):
    class Meta:
        model = EvidenciaParecer
        fields = ("bloco", "arquivo", "descricao")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivo"].widget.attrs["accept"] = ACCEPT_HTML
        self.fields["arquivo"].help_text = "Print ou documento. PDF, JPG ou PNG, até 25 MB."

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        validar_documento(arquivo)
        return arquivo
