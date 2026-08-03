"""Formatação brasileira: R$ 1.234,56 e 31/07/2026 (AGENTS.md §8)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from operacoes.templatetags.formatacao import data_br, data_hora_br, moeda


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
        (None, "—"),
    ],
)
def test_moeda(valor, esperado):
    assert moeda(valor) == esperado


def test_datas():
    momento = datetime(2026, 7, 31, 14, 30)

    assert data_br(momento) == "31/07/2026"
    assert data_hora_br(momento) == "31/07/2026 14:30"
    assert data_br(None) == "—"


def test_aceita_date_sem_hora():
    """Data de evento e de emissão são `date`, não `datetime`."""
    dia = date(2026, 8, 24)

    assert data_br(dia) == "24/08/2026"
    assert data_hora_br(dia) == "24/08/2026"


def test_datetime_com_fuso_e_convertido_para_o_horario_local():
    momento = timezone.make_aware(datetime(2026, 7, 31, 14, 30))

    assert data_hora_br(momento) == "31/07/2026 14:30"
