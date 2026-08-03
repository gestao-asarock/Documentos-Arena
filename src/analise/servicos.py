"""
Conferência documental — etapas 3 a 5 da Fase 1 (AGENTS.md §4.6).

Por enquanto a conferência é inteiramente humana. Quando a análise por IA entrar,
ela preenche a evidência (campos extraídos, recortes, divergências) e **continua**
sendo a pessoa quem aprova ou rejeita: a IA nunca decide (AGENTS.md §5.1).
"""

from django.db import transaction
from django.db.models import Q

from auditoria.servicos import Acao, registrar
from contas.models import Papel
from contrapartes.models import DocumentoCadastral, StatusHabilitacao
from documentos.models import StatusDocumento

#: Quem confere documento. O guia atribui a triagem ao CRM; Compliance participa
#: porque é quem sofre a consequência de documento mal conferido.
PAPEIS_QUE_CONFEREM = {Papel.CRM, Papel.COMPLIANCE, Papel.ADMINISTRADOR}


def pode_conferir(usuario) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=PAPEIS_QUE_CONFEREM).exists()


def fila_de_conferencia():
    """Documentos aguardando decisão humana, mais antigos primeiro.

    Fila é fila: quem chegou antes é analisado antes.
    """
    return (
        DocumentoCadastral.objects.filter(
            Q(status=StatusDocumento.ENVIADO)
            | Q(status=StatusDocumento.PROCESSANDO)
            | Q(status=StatusDocumento.ANALISADO)
        )
        .select_related("contraparte", "tipo", "subtipo", "enviado_por")
        .prefetch_related("arquivos")
        .order_by("data_envio")
    )


def _perfil_de(documento: DocumentoCadastral):
    """O cadastro de perfil mais recente da contraparte."""
    return documento.contraparte.solicitacoes.order_by("-data_criacao").first()


@transaction.atomic
def aprovar_documento(documento: DocumentoCadastral, *, usuario, observacao: str = ""):
    """Aceita o documento e reavalia se o dossiê ficou completo."""
    documento.status = StatusDocumento.APROVADO
    documento.observacao = observacao
    documento.save()

    registrar(
        acao=Acao.APROVACAO,
        descricao=f"{documento.rotulo} aprovado na conferência documental",
        objeto=documento,
        usuario=usuario,
    )
    _reavaliar_contratos(documento)
    return _reavaliar_habilitacao(documento, usuario=usuario)


def _reavaliar_contratos(documento: DocumentoCadastral) -> None:
    """Move os contratos que dependiam deste documento.

    O documento pertence ao perfil, mas pode estar vinculado a contratos: sem
    isto, aprovar o último documento não tirava o contrato de 'aguardando
    documentos' e ele nunca chegava à fila seguinte (AGENTS.md D29).
    """
    from operacoes.servicos import avancar

    for operacao in documento.operacoes.all():
        avancar(operacao)


@transaction.atomic
def rejeitar_documento(documento: DocumentoCadastral, *, usuario, motivo: str):
    """Devolve o documento ao Clube, com o motivo — a pendência trava o fluxo (§4.6)."""
    if not motivo.strip():
        raise ValueError("Informe o motivo da rejeição para o Clube poder corrigir.")

    documento.status = StatusDocumento.REJEITADO
    documento.observacao = motivo
    documento.save()

    registrar(
        acao=Acao.REPROVACAO,
        descricao=f"{documento.rotulo} rejeitado na conferência documental",
        objeto=documento,
        usuario=usuario,
    )

    perfil = _perfil_de(documento)
    habilitacao = perfil.habilitacao if perfil else None
    if habilitacao and habilitacao.status != StatusHabilitacao.COM_PENDENCIA:
        habilitacao.status = StatusHabilitacao.COM_PENDENCIA
        habilitacao.save()

    return habilitacao


def _reavaliar_habilitacao(documento: DocumentoCadastral, *, usuario=None):
    """Move a habilitação conforme o estado real do dossiê.

    Kit completo e sem rejeição pendente → segue para compliance. Enquanto faltar
    documento, volta a aguardar envio: o estado é derivado, nunca assumido.
    """
    perfil = _perfil_de(documento)
    if perfil is None or perfil.habilitacao is None:
        return None

    habilitacao = perfil.habilitacao
    if habilitacao.status in {StatusHabilitacao.HABILITADA, StatusHabilitacao.RECUSADA}:
        return habilitacao

    contraparte = documento.contraparte
    tem_rejeitado = contraparte.documentos_cadastrais.filter(
        status=StatusDocumento.REJEITADO
    ).exists()

    if tem_rejeitado:
        novo = StatusHabilitacao.COM_PENDENCIA
    elif perfil.kit_completo:
        novo = StatusHabilitacao.EM_COMPLIANCE
    elif contraparte.documentos_cadastrais.filter(
        status__in=[StatusDocumento.ENVIADO, StatusDocumento.PROCESSANDO]
    ).exists():
        novo = StatusHabilitacao.EM_ANALISE_DOCUMENTAL
    else:
        novo = StatusHabilitacao.AGUARDANDO_DOCUMENTOS

    if habilitacao.status != novo:
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
