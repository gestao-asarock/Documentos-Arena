"""
Cabeçalho de coluna ordenável, num lugar só.

Mora em `operacoes` pelo mesmo motivo de `formatacao`: é a biblioteca de tags
que as duas listas carregam, e criar um app só para hospedar dois filtros custa
migration e entrada em `INSTALLED_APPS` sem trazer nada.

A ordem em vigor vem do contexto (`ordem`, um `arena.listagem.Ordem`), e o link
de cada coluna nasce da URL atual: assim o clique no cabeçalho preserva os
filtros. `pagina` é a única coisa descartada, porque a página 4 de uma lista
ordenada por valor não é a página 4 da mesma lista ordenada por data.
"""

from django import template

register = template.Library()

#: Setas do cabeçalho. O `aria-sort` diz o mesmo para quem usa leitor de tela,
#: então a seta é decorativa e sai da leitura.
SETAS = {"asc": "▲", "desc": "▼"}

ARIA = {"asc": "ascending", "desc": "descending"}


@register.inclusion_tag("_coluna.html", takes_context=True)
def coluna(context, chave, rotulo, numero=False):
    """Um `th` que ordena a lista pela chave dada.

    `numero` alinha à direita, para dinheiro e contagem, como o resto do sistema.
    """
    ordem = context["ordem"]
    parametros = context["request"].GET.copy()
    parametros["ordem"] = ordem.alternar(chave)
    parametros.pop("pagina", None)

    direcao = ordem.direcao_de(chave)
    return {
        "rotulo": rotulo,
        "url": f"?{parametros.urlencode()}",
        "direcao": direcao,
        "seta": SETAS.get(direcao, ""),
        "aria": ARIA.get(direcao, "none"),
        "numero": numero,
    }


@register.simple_tag(takes_context=True)
def url_da_pagina(context, numero):
    """A URL desta mesma lista, noutra página, com os filtros preservados."""
    parametros = context["request"].GET.copy()
    parametros["pagina"] = str(numero)
    return f"?{parametros.urlencode()}"


@register.simple_tag(takes_context=True)
def url_com(context, **valores):
    """A URL desta lista com estes parâmetros trocados. Vazio remove o parâmetro.

    É o link da aba: trocar de tipo de contrato mantém a busca e os filtros em
    vigor, porque a aba é um recorte a mais e não um recomeço.
    """
    parametros = context["request"].GET.copy()
    for chave, valor in valores.items():
        if valor in (None, ""):
            parametros.pop(chave, None)
        else:
            parametros[chave] = str(valor)
    parametros.pop("pagina", None)
    consulta = parametros.urlencode()
    return f"?{consulta}" if consulta else "?"


@register.simple_tag(takes_context=True)
def url_apenas_com(context, *chaves):
    """A URL desta lista guardando só os parâmetros dados. É o "limpar filtros".

    Listar o que fica é mais seguro que listar o que sai: filtro novo entra sem
    ninguém lembrar de acrescentá-lo aqui, e o botão continua limpando tudo.
    """
    parametros = context["request"].GET.copy()
    guardados = {chave: parametros.getlist(chave) for chave in chaves if chave in parametros}
    parametros.clear()
    for chave, valores in guardados.items():
        parametros.setlist(chave, valores)
    consulta = parametros.urlencode()
    return f"?{consulta}" if consulta else "?"


@register.simple_tag(takes_context=True)
def url_sem(context, *chaves):
    """A URL atual sem os parâmetros dados. É o "x" que remove um filtro."""
    parametros = context["request"].GET.copy()
    for chave in (*chaves, "pagina"):
        parametros.pop(chave, None)
    consulta = parametros.urlencode()
    return f"?{consulta}" if consulta else "?"
