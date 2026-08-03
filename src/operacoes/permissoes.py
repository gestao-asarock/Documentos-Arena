"""
Quem pode decidir cada etapa (AGENTS.md §4.2).

A alçada é do papel, não do usuário: qualquer pessoa do Compliance decide a etapa
de due diligence. Administrador e superusuário passam por todas.
"""

from contas.models import Papel

from .estados import Etapa
from .models import EtapaAprovacao

#: Risco/Crédito não tem usuário próprio no MVP: CRM ou Compliance registra o
#: parecer em nome do time (AGENTS.md D9).
PAPEIS_POR_ETAPA = {
    Etapa.TRIAGEM: {Papel.CRM},
    Etapa.DUE_DILIGENCE: {Papel.COMPLIANCE},
    Etapa.RISCO_CREDITO: {Papel.CRM, Papel.COMPLIANCE},
    Etapa.JURIDICO: {Papel.JURIDICO},
    Etapa.ASSINATURAS: {Papel.CLUBE},
    Etapa.ENVIO_NF: {Papel.CLUBE},
    Etapa.BOLETAGEM: {Papel.CRM},
    Etapa.LIQUIDACAO: {Papel.CRM},
}


def pode_decidir(usuario, etapa: EtapaAprovacao) -> bool:
    """O usuário tem papel para decidir esta etapa?

    Não verifica se a etapa está pendente nem se é a atual — isso é regra de
    fluxo e fica no serviço.
    """
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.tem_papel(Papel.ADMINISTRADOR):
        return True

    permitidos = PAPEIS_POR_ETAPA.get(Etapa(etapa.etapa), set())
    return usuario.groups.filter(name__in=permitidos).exists()


def pode_cancelar(usuario, registro) -> bool:
    """Cancela quem criou, ou qualquer pessoa interna da ASAROCK.

    O usuário do Clube só mexe no que é dele; a ASAROCK precisa poder encerrar
    pedido abandonado (AGENTS.md §4.2).
    """
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.eh_interno:
        return True
    return registro.criada_por_id == usuario.id


def pode_criar_operacao(usuario) -> bool:
    """CRM cria operações; o Clube também, para seus próprios terceiros."""
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.tem_papel(Papel.ADMINISTRADOR):
        return True
    return usuario.groups.filter(name__in={Papel.CRM, Papel.CLUBE}).exists()
