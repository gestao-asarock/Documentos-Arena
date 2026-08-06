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


def eh_administrador(usuario) -> bool:
    """Superusuário ou papel administrador.

    É a régua dos **poderes de correção** (AGENTS.md D58): apagar registro
    cancelado e editar cadastro que o fluxo normal já travou. Nenhum deles é
    parte do fluxo; existem porque fluxo real tem engano, e sem uma saída o
    engano vira intervenção no banco, que não passa por auditoria nenhuma.
    """
    if not usuario.is_authenticated:
        return False
    return usuario.is_superuser or usuario.tem_papel(Papel.ADMINISTRADOR)


def pode_excluir(usuario, registro) -> bool:
    """Apagar de vez: só o administrador, e só o que já está cancelado.

    Cancelado primeiro não é burocracia: obriga a passar pelas guardas do
    cancelamento, que recusam encerrar um registro com contrato em andamento.
    Sem isso, apagar seria um atalho para furar aquelas regras.
    """
    return eh_administrador(usuario) and registro.esta_cancelada


def pode_editar_perfil(usuario, solicitacao) -> bool:
    """Quem pode alterar os dados cadastrais do perfil (AGENTS.md D47, D58).

    Regra normal: quem abriu o registro ou a ASAROCK, e só enquanto a
    contraparte não foi validada. O administrador passa por cima disso,
    inclusive em perfil validado ou cancelado. É a contrapartida do D57: com o
    cadastro duplicado barrado, um endereço errado em perfil já aprovado ficaria
    sem nenhum conserto possível.
    """
    if not eh_dono_ou_interno(usuario, solicitacao):
        return False
    return eh_administrador(usuario) or solicitacao.pode_ser_editada


def pode_criar_operacao(usuario) -> bool:
    """CRM cria operações; o Clube também, para seus próprios terceiros."""
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser or usuario.tem_papel(Papel.ADMINISTRADOR):
        return True
    return usuario.groups.filter(name__in={Papel.CRM, Papel.CLUBE}).exists()
