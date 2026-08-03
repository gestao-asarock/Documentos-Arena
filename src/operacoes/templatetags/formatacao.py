"""
Formatação brasileira (AGENTS.md §8).

Ponto único de formatação: não formate valor nem data no meio de view ou template,
e não confie no locale do servidor, que varia entre a EC2 e a máquina local.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def moeda(valor) -> str:
    """R$ 1.234,56 — milhar com ponto, decimal com vírgula, sempre duas casas."""
    if valor is None or valor == "":
        return "—"
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return "—"

    inteiro, _, centavos = f"{numero:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")

    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)

    return f"{'-' if negativo else ''}R$ {'.'.join(grupos)},{centavos}"


def _no_fuso_local(valor):
    """Converte para o fuso local quando houver hora; `date` passa direto.

    `timezone.is_aware` exige um datetime — um `date` (data do evento, emissão de
    documento) quebraria aqui.
    """
    if isinstance(valor, datetime) and timezone.is_aware(valor):
        return timezone.localtime(valor)
    return valor


@register.filter
def data_br(valor) -> str:
    """31/07/2026. Aceita `date` e `datetime`."""
    if not valor:
        return "—"
    return _no_fuso_local(valor).strftime("%d/%m/%Y")


@register.filter
def data_hora_br(valor) -> str:
    """31/07/2026 14:30."""
    if not valor:
        return "—"
    valor = _no_fuso_local(valor)
    if not isinstance(valor, datetime):
        # Sem hora para mostrar: melhor a data sozinha do que "00:00" inventado.
        return valor.strftime("%d/%m/%Y")
    return valor.strftime("%d/%m/%Y %H:%M")
