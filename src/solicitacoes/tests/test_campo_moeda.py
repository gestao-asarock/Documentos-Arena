"""
Valor em reais digitado à brasileira (AGENTS.md §3, §8).

O campo é de texto, e não `type="number"`: a roda do mouse sobre um campo
numérico troca o valor do contrato sem que ninguém perceba. O preço disso é ter
de normalizar aqui o que a máscara escreve na tela.
"""

from decimal import Decimal

import pytest
from django import forms

from solicitacoes.campos import MoedaBRField


class _Form(forms.Form):
    valor = MoedaBRField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))


def _limpo(digitado: str) -> Decimal:
    form = _Form({"valor": digitado})
    assert form.is_valid(), form.errors
    return form.cleaned_data["valor"]


@pytest.mark.parametrize(
    ("digitado", "esperado"),
    [
        ("1.234,56", "1234.56"),
        ("1234,56", "1234.56"),
        ("0,01", "0.01"),
        ("5.000,00", "5000.00"),
        ("1.234.567,89", "1234567.89"),
        ("R$ 1.234,56", "1234.56"),
        # Sem vírgula: 1.234 é milhar, não um número com casas decimais.
        ("1.234", "1234"),
        ("5000", "5000"),
        # O que vem de script ou de colagem crua continua valendo.
        ("1234.56", "1234.56"),
    ],
)
def test_formatos_aceitos(digitado, esperado):
    assert _limpo(digitado) == Decimal(esperado)


def test_valor_de_fronteira_do_piloto():
    """R$ 5.000,00 é o limite do enquadramento piloto (AGENTS.md §4.3)."""
    assert _limpo("5.000,00") == Decimal("5000.00")


def test_texto_sem_numero_e_recusado():
    form = _Form({"valor": "cinco mil"})

    assert not form.is_valid()
    assert "1.234,56" in form.errors["valor"][0]


def test_campo_nao_e_input_numerico():
    """A regressão que motivou o campo: setinha e roda do mouse no valor."""
    html = _Form().as_p()

    assert 'type="text"' in html
    assert 'type="number"' not in html
    assert 'inputmode="decimal"' in html


def test_valor_do_banco_chega_formatado_na_tela():
    html = _Form(initial={"valor": Decimal("1234.56")}).as_p()

    assert 'value="1.234,56"' in html


def test_valor_digitado_nao_e_reescrito_pelo_servidor_no_erro():
    """Formulário recusado devolve o texto da pessoa, não uma reescrita dele.

    A máscara do navegador ainda normaliza o campo ao carregar a página; o que
    esta garantia impede é o servidor decidir sozinho o que a pessoa quis dizer.
    """
    html = _Form({"valor": "abc"}).as_p()

    assert 'value="abc"' in html
