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
        return "-"
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return "-"

    inteiro, _, centavos = f"{numero:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")

    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)

    return f"{'-' if negativo else ''}R$ {'.'.join(grupos)},{centavos}"


@register.filter
def cpf_cnpj(valor) -> str:
    """123.456.789-09 ou 12.345.678/0001-95.

    O banco guarda só os dígitos, de propósito: é assim que se procura e se
    compara sem depender de quem digitou com ponto ou sem. A pontuação é
    assunto de exibição, e mora aqui — nenhuma tela remonta isso na mão.
    """
    digitos = "".join(c for c in str(valor or "") if c.isdigit())

    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"

    # Nem CPF nem CNPJ: mostra o que existe. Cadastro torto precisa aparecer na
    # tela para ser corrigido, não sumir atrás de um travessão.
    return digitos or "-"


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
        return "-"
    return _no_fuso_local(valor).strftime("%d/%m/%Y")


@register.filter
def data_hora_br(valor) -> str:
    """31/07/2026 14:30."""
    if not valor:
        return "-"
    valor = _no_fuso_local(valor)
    if not isinstance(valor, datetime):
        # Sem hora para mostrar: melhor a data sozinha do que "00:00" inventado.
        return valor.strftime("%d/%m/%Y")
    return valor.strftime("%d/%m/%Y %H:%M")
