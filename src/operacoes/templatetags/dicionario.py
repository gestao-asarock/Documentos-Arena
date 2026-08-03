"""Acesso a dicionário por chave dentro do template."""

from django import template

register = template.Library()


@register.filter
def get(dicionario, chave):
    """`{{ meu_dict|get:variavel }}` — o Django não faz isso nativamente."""
    if hasattr(dicionario, "get"):
        return dicionario.get(chave, "")
    return ""
