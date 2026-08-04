"""
Cor e símbolo de cada situação, num lugar só (AGENTS.md §8).

Sem isto, cada template decide sua própria cor e o sistema fica inconsistente —
foi o que aconteceu quando surgiram os status de perfil.

São cinco famílias, e nada além delas:

    sucesso    verde     terminou bem, ou já está válido
    erro       vermelho  terminou mal, foi cancelado ou recusado
    atencao    âmbar     travado esperando correção de alguém
    andamento  azul      em curso, seguindo o fluxo
    neutro     cinza     não se aplica a este caso

Estado nunca depende só de cor: o símbolo acompanha, porque parte dos usuários
não distingue vermelho de verde e esta é uma tela de aprovar e reprovar.
"""

from django import template

register = template.Library()

FAMILIAS = {
    # -- Terminou bem, ou está válido --------------------------------------
    "aprovada": "sucesso",
    "aprovado": "sucesso",
    "assinada": "sucesso",
    "concluida": "sucesso",
    "concluido": "sucesso",
    "habilitada": "sucesso",
    "pronta_para_contrato": "sucesso",
    "cumprida_na_habilitacao": "sucesso",
    # -- Terminou mal ------------------------------------------------------
    "cancelada": "erro",
    "falha_analise": "erro",
    "recusada": "erro",
    "rejeitado": "erro",
    "reprovada": "erro",
    # -- Travado, esperando alguém corrigir --------------------------------
    "com_pendencia": "atencao",
    # -- Em curso ----------------------------------------------------------
    "aguardando_assinatura": "andamento",
    "aguardando_documentos": "andamento",
    # Analisado pela IA, ainda esperando a decisão humana (AGENTS.md §5.1).
    "analisado": "andamento",
    "em_analise": "andamento",
    "em_analise_documental": "andamento",
    "em_aprovacao": "andamento",
    "em_compliance": "andamento",
    "em_credito": "andamento",
    "em_habilitacao": "andamento",
    "enviado": "andamento",
    "pendente": "andamento",
    "processando": "andamento",
    "rascunho": "andamento",
    # -- Não se aplica -----------------------------------------------------
    "dispensada": "neutro",
    # Perfil cancelado: a validação parou de importar (solicitacoes/models.py).
    "nao_se_aplica": "neutro",
    "registrada_externamente": "neutro",
}

SIMBOLOS = {
    "sucesso": "✓",  # ✓
    "erro": "✗",  # ✗
    "atencao": "⚠",  # ⚠
    "andamento": "●",  # ●
    "neutro": "–",  # –
}


@register.filter
def familia(status: str) -> str:
    """Família visual de um status. Desconhecido vira 'andamento', nunca some da tela."""
    return FAMILIAS.get(status, "andamento")


@register.filter
def simbolo(status: str) -> str:
    return SIMBOLOS[familia(status)]
