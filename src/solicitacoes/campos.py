"""
Campos de formulário reutilizáveis (AGENTS.md §8).

Data em padrão brasileiro, digitável e colável — o seletor nativo do navegador
não aceita texto colado, o que atrapalha quem trabalha copiando dados. Dinheiro
em texto com máscara, pelo mesmo motivo e por mais um: `type="number"` deixa o
valor à mercê da roda do mouse.
"""

import re
from decimal import Decimal, InvalidOperation

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


#: Formato que a máscara produz: 1.234,56. Também aceito sem os pontos.
PADRAO_MILHAR = re.compile(r"^\d{1,3}(\.\d{3})+$")


class MoedaBRWidget(forms.TextInput):
    """Campo de texto com máscara, em vez de `type="number"`.

    O `input[type=number]` traz as setinhas do navegador, e com elas a roda do
    mouse: passar o cursor sobre o campo e rolar a página trocava o valor do
    contrato sem ninguém perceber. Texto não tem esse comportamento.
    """

    def __init__(self, attrs=None):
        padrao = {
            "placeholder": "0,00",
            "inputmode": "decimal",
            "autocomplete": "off",
            "data-mascara": "moeda",
        }
        padrao.update(attrs or {})
        super().__init__(padrao)

    def format_value(self, value):
        """Mostra 1.234,56 quando o valor vem do banco, e não `1234.56`.

        Texto passa intocado: se o formulário voltou com erro, o que está ali é
        o que a pessoa digitou, e reescrevê-lo atrapalharia a correção.
        """
        if value is None or isinstance(value, str):
            return super().format_value(value)

        from operacoes.templatetags.formatacao import moeda

        return moeda(value).removeprefix("R$ ")


class MoedaBRField(forms.DecimalField):
    """Dinheiro digitado à brasileira: 1.234,56.

    `Decimal`, nunca `float` (AGENTS.md §3). O que chega da tela é normalizado
    aqui; a validação de faixa continua a cargo do `DecimalField`.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", MoedaBRWidget())
        super().__init__(**kwargs)

    def to_python(self, valor):
        if valor in self.empty_values:
            return None

        texto = str(valor).strip().removeprefix("R$").strip().replace(" ", "")

        if "," in texto:
            # Vírgula é o separador decimal: o ponto que sobrar é de milhar.
            texto = texto.replace(".", "").replace(",", ".")
        elif PADRAO_MILHAR.match(texto):
            # 1.234 é mil duzentos e trinta e quatro, não um inteiro com decimais.
            texto = texto.replace(".", "")

        try:
            return Decimal(texto)
        except InvalidOperation:
            raise forms.ValidationError(
                "Informe um valor em reais, como 1.234,56.", code="invalid"
            ) from None


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
