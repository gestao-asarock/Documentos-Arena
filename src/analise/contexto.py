"""
Contexto disponível em todos os templates.

O menu mostra apenas o que a área faz — cada papel tem função própria e telas
próprias (AGENTS.md §4.2, D34). Isto controla só a navegação: cada view continua
verificando permissão por conta própria (AGENTS.md §6).
"""

from compliance.servicos import pode_analisar
from credito.servicos import pode_analisar as pode_analisar_credito
from juridico.servicos import pode_revisar

from .servicos import pode_conferir


def papeis(request):
    usuario = getattr(request, "user", None)
    if usuario is None:
        return {}
    return {
        "pode_conferir": pode_conferir(usuario),
        "pode_analisar_compliance": pode_analisar(usuario),
        "pode_analisar_credito": pode_analisar_credito(usuario),
        "pode_revisar_juridico": pode_revisar(usuario),
    }
