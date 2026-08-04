"""
Quem pode decidir cada etapa (AGENTS.md §4.2).

A alçada é do papel, não do usuário: qualquer pessoa do Compliance decide a etapa
de due diligence. Administrador e superusuário passam por todas.
"""

from contas.models import Papel

from .estados import Etapa
from .models import EtapaAprovacao

#: Cada área atua na sua etapa (AGENTS.md §4.2, D34):
#:
#:   crm         triagem documental e análise de crédito
#:   compliance  due diligence — e triagem, se quiser ajudar
#:   juridico    revisão dos contratos, e só
#:   clube       envia e acompanha; decide apenas a assinatura
PAPEIS_POR_ETAPA = {
    Etapa.TRIAGEM: {Papel.CRM, Papel.COMPLIANCE},
    Etapa.DUE_DILIGENCE: {Papel.COMPLIANCE},
    # Risco/Crédito não tem usuário próprio no MVP: o CRM registra o parecer em
    # nome do time, consultando o Serasa (AGENTS.md D9).
    Etapa.RISCO_CREDITO: {Papel.CRM},
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


def eh_dono_ou_interno(usuario, registro) -> bool:
    """Quem abriu o registro, ou qualquer pessoa interna da ASAROCK.

    É a régua das ações que **desfazem** coisa: cancelar, excluir. O Clube
    enxerga a esteira inteira do time (D35), mas desfazer o que outra pessoa fez
    continua sendo de quem fez — ou da ASAROCK, que precisa poder encerrar
    pedido abandonado (AGENTS.md §4.2).
    """
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.eh_interno:
        return True
    return registro.criada_por_id == usuario.id


def pode_cancelar(usuario, registro) -> bool:
    return eh_dono_ou_interno(usuario, registro)


def pode_criar_operacao(usuario) -> bool:
    """CRM cria operações; o Clube também, para seus próprios terceiros."""
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.tem_papel(Papel.ADMINISTRADOR):
        return True
    return usuario.groups.filter(name__in={Papel.CRM, Papel.CLUBE}).exists()
