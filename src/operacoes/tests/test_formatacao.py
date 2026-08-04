"""Formatação brasileira: R$ 1.234,56, 31/07/2026 e 589.747.908-90 (AGENTS.md §8)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from operacoes.templatetags.formatacao import cpf_cnpj, data_br, data_hora_br, moeda


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("0.00"), "R$ 0,00"),
        (Decimal("5.5"), "R$ 5,50"),
        (Decimal("1234.56"), "R$ 1.234,56"),
        (Decimal("5000.00"), "R$ 5.000,00"),
        (Decimal("199999.99"), "R$ 199.999,99"),
        (Decimal("1234567.89"), "R$ 1.234.567,89"),
        (Decimal("-250.00"), "-R$ 250,00"),
        (None, "-"),
    ],
)
def test_moeda(valor, esperado):
    assert moeda(valor) == esperado


def test_datas():
    momento = datetime(2026, 7, 31, 14, 30)

    assert data_br(momento) == "31/07/2026"
    assert data_hora_br(momento) == "31/07/2026 14:30"
    assert data_br(None) == "-"


def test_aceita_date_sem_hora():
    """Data de evento e de emissão são `date`, não `datetime`."""
    dia = date(2026, 8, 24)

    assert data_br(dia) == "24/08/2026"
    assert data_hora_br(dia) == "24/08/2026"


def test_datetime_com_fuso_e_convertido_para_o_horario_local():
    momento = timezone.make_aware(datetime(2026, 7, 31, 14, 30))

    assert data_hora_br(momento) == "31/07/2026 14:30"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        # O banco guarda só dígitos; a tela mostra pontuado.
        ("58974790890", "589.747.908-90"),
        ("00000000000191", "00.000.000/0001-91"),
        # Já pontuado (colado de outro sistema) não vira remendo em cima de remendo.
        ("589.747.908-90", "589.747.908-90"),
        ("00.000.000/0001-91", "00.000.000/0001-91"),
        (None, "-"),
        ("", "-"),
    ],
)
def test_cpf_cnpj(valor, esperado):
    assert cpf_cnpj(valor) == esperado


def test_documento_torto_aparece_como_esta():
    """Cadastro errado precisa ficar visível para ser corrigido, não sumir."""
    assert cpf_cnpj("12345") == "12345"
