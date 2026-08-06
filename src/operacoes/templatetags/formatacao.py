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


#: Espaço que não quebra linha. Caractere de verdade, não entidade HTML: assim o
#: Django não o escapa. Escrito pelo nome Unicode, e não colado literalmente no
#: fonte, porque um U+00A0 cru é invisível para quem lê o código e um editor o
#: troca por espaço comum sem ninguém notar.
ESPACO_FIXO = "\N{NO-BREAK SPACE}"


@register.filter
def moeda_sem_quebra(texto) -> str:
    """Cola o `R$` ao número em **texto livre**, para a linha não quebrar entre os dois.

    Serve para o que vem do banco e não passa pelo filtro `moeda`, como o critério
    do enquadramento ("Evento até R$ 5.000,00"). Em coluna estreita a quebra caía
    entre o símbolo e o valor e o resultado parecia defeito de renderização.

    O texto continua quebrando **entre palavras**, que é o certo: o que não se
    parte é só o par símbolo e número.

    Não é o `moeda` que muda, e é de propósito: `solicitacoes/campos.py` faz
    `removeprefix("R$ ")` na saída dele para preencher o campo de texto, e trocar
    aquele espaço por um fixo deixaria o prefixo sobrando dentro do input.
    """
    return str(texto or "").replace("R$ ", f"R${ESPACO_FIXO}")


@register.filter
def codigo_contraparte(valor) -> str:
    """`K7M42QX9BT5R` vira `K7M4-2QX9-BT5R` (AGENTS.md D59).

    A mesma regra do `cpf_cnpj`: o banco guarda o valor limpo, e a pontuação é
    assunto de exibição. Delega para `contrapartes.codigo` porque o agrupamento
    depende do tamanho do código, que é definido lá.
    """
    from contrapartes.codigo import formatar_codigo

    return formatar_codigo(str(valor or ""))


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
