"""Formulários de operação. Validação de domínio fica no modelo/serviço."""

from django import forms

from solicitacoes.models import Solicitacao


class OperacaoForm(forms.Form):
    """Contrato a partir de uma solicitação habilitada.

    Contraparte, tipo e valor **não são digitados de novo**: vêm da solicitação,
    que já passou por compliance e crédito com aqueles dados (AGENTS.md §4.0).
    """

    solicitacao = forms.ModelChoiceField(
        queryset=Solicitacao.objects.none(),
        label="Solicitação",
        help_text="Só aparecem pedidos com a contraparte já habilitada.",
    )
    descricao = forms.CharField(
        label="Descrição do contrato",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="O que está sendo contratado, para que e quando.",
    )

    def __init__(self, *args, solicitacoes=None, **kwargs):
        super().__init__(*args, **kwargs)
        if solicitacoes is not None:
            self.fields["solicitacao"].queryset = solicitacoes


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
