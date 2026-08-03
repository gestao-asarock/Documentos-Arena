"""
Campos de formulário reutilizáveis (AGENTS.md §8).

Data em padrão brasileiro, digitável e colável — o seletor nativo do navegador
não aceita texto colado, o que atrapalha quem trabalha copiando dados.
"""

from django import forms

#: Aceita 31/07/2026, 31-07-2026 e o formato ISO que o navegador às vezes envia.
FORMATOS_DE_DATA = ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"]


class DataBRWidget(forms.TextInput):
    """Campo de texto com máscara, em vez do seletor nativo."""

    def __init__(self, attrs=None):
        padrao = {
            "placeholder": "dd/mm/aaaa",
            "inputmode": "numeric",
            "autocomplete": "off",
            "maxlength": "10",
            "data-mascara": "data",
        }
        padrao.update(attrs or {})
        super().__init__(padrao)


class DataBRField(forms.DateField):
    def __init__(self, **kwargs):
        kwargs.setdefault("input_formats", FORMATOS_DE_DATA)
        kwargs.setdefault("widget", DataBRWidget())
        super().__init__(**kwargs)


class MultiploArquivoWidget(forms.ClearableFileInput):
    """Permite selecionar vários arquivos de uma vez (frente e verso, páginas)."""

    allow_multiple_selected = True


class MultiploArquivoField(forms.FileField):
    def __init__(self, **kwargs):
        kwargs.setdefault("widget", MultiploArquivoWidget())
        super().__init__(**kwargs)

    def clean(self, data, initial=None):
        """Valida cada arquivo da seleção, não só o primeiro."""
        limpar = super().clean
        if isinstance(data, (list, tuple)):
            if not data and not self.required:
                return []
            return [limpar(arquivo, initial) for arquivo in data]
        return [limpar(data, initial)]
