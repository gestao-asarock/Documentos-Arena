"""Contexto disponível em todos os templates."""

from compliance.servicos import pode_analisar
from credito.servicos import pode_analisar as pode_analisar_credito

from .servicos import pode_conferir


def papeis(request):
    """Deixa o menu saber o que o usuário pode acessar.

    Só controla o que aparece na navegação — cada view continua verificando
    permissão por conta própria (AGENTS.md §6).
    """
    usuario = getattr(request, "user", None)
    if usuario is None:
        return {}
    return {
        "pode_conferir": pode_conferir(usuario),
        "pode_analisar_compliance": pode_analisar(usuario),
        "pode_analisar_credito": pode_analisar_credito(usuario),
    }
