"""
Estado do perfil da contraparte, derivado do dossiê (AGENTS.md §4.6, D29).

O documento cadastral pertence à **contraparte**, não ao cadastro que o enviou:
é o que permite reaproveitá-lo em perfis e contratos seguintes. A consequência é
que a situação da habilitação não pode ser atualizada só quando alguém aprova um
documento — um perfil novo pode nascer com o kit inteiro já aprovado, sem que
nenhuma aprovação vá acontecer. Por isso o estado é **derivado do dossiê**,
sempre que se olha para ele, como já se faz com a operação em `operacoes.servicos.avancar`.
"""

from auditoria.servicos import Acao, registrar
from documentos.models import StatusDocumento

from .models import Habilitacao, StatusHabilitacao

#: Estados que a conferência documental não governa mais. Depois que o perfil
#: passa para o crédito, aprovar um documento não pode puxá-lo de volta para o
#: compliance — quem decide dali em diante é o parecer, não o dossiê.
ESTADOS_ALEM_DA_CONFERENCIA = frozenset(
    {
        StatusHabilitacao.EM_CREDITO,
        StatusHabilitacao.HABILITADA,
        StatusHabilitacao.RECUSADA,
    }
)


def avancar_habilitacao(habilitacao: Habilitacao | None, *, usuario=None) -> Habilitacao | None:
    """Põe a habilitação no estado que o dossiê da contraparte descreve.

    Kit completo e sem rejeição → segue para o compliance. Documento esperando
    conferência → análise documental. Documento rejeitado → pendência. Nada
    enviado → aguardando documentos.

    Idempotente: sem mudança de estado, não grava nem registra nada.
    """
    if habilitacao is None or habilitacao.status in ESTADOS_ALEM_DA_CONFERENCIA:
        return habilitacao

    contraparte = habilitacao.contraparte
    documentos = contraparte.documentos_cadastrais

    if documentos.filter(status=StatusDocumento.REJEITADO).exists():
        novo = StatusHabilitacao.COM_PENDENCIA
    elif contraparte.kit_completo():
        novo = StatusHabilitacao.EM_COMPLIANCE
    elif documentos.filter(
        status__in=[StatusDocumento.ENVIADO, StatusDocumento.PROCESSANDO]
    ).exists():
        novo = StatusHabilitacao.EM_ANALISE_DOCUMENTAL
    else:
        novo = StatusHabilitacao.AGUARDANDO_DOCUMENTOS

    if habilitacao.status == novo:
        return habilitacao

    anterior = habilitacao.get_status_display()
    habilitacao.status = novo
    habilitacao.save()
    registrar(
        acao=Acao.TRANSICAO_ESTADO,
        descricao=(
            f"Habilitação da contraparte #{contraparte.pk}: "
            f"{anterior} → {habilitacao.get_status_display()}"
        ),
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao


__all__ = ["avancar_habilitacao", "ESTADOS_ALEM_DA_CONFERENCIA"]
