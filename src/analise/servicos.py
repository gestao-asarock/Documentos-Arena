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
from contrapartes.servicos import avancar_habilitacao
from documentos.models import StatusDocumento
from solicitacoes.models import StatusSolicitacao

#: A triagem é do CRM, conforme o guia. O Compliance pode conferir também — é
#: quem sofre a consequência de documento mal triado (AGENTS.md D34).
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
    """O cadastro de perfil ativo mais recente da contraparte.

    Perfil cancelado não recebe a decisão: quando o Clube refaz o cadastro da
    mesma pessoa, o mais recente pode ser o antigo, e a aprovação ia mexer no
    registro errado — deixando o perfil em uso parado.
    """
    return (
        documento.contraparte.solicitacoes.exclude(status=StatusSolicitacao.CANCELADA)
        .order_by("-data_criacao")
        .first()
    )


@transaction.atomic
def aprovar_documento(documento: DocumentoCadastral, *, usuario, observacao: str = ""):
    """Aceita o documento e reavalia se o dossiê ficou completo.

    Aprovar um documento já fora do prazo é aceitá-lo assim mesmo: a dispensa fica
    gravada, com quanto tempo tinha, para o dossiê não o devolver à pendência logo
    em seguida (AGENTS.md D55).
    """
    documento.status = StatusDocumento.APROVADO
    documento.observacao = observacao

    fora_do_prazo = documento.esta_vencido
    if fora_do_prazo:
        documento.prazo_dispensado = True
    documento.save()

    descricao = f"{documento.rotulo} aprovado na conferência documental"
    if fora_do_prazo:
        descricao += f", fora do prazo (emitido há {documento.dias_desde_emissao} dias)"
    registrar(
        acao=Acao.APROVACAO,
        descricao=descricao,
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
    # Rejeitar desfaz a dispensa: se este documento voltar a ser aprovado, o prazo
    # é avaliado de novo, na conferência daquele momento.
    documento.prazo_dispensado = False
    documento.save()

    registrar(
        acao=Acao.REPROVACAO,
        descricao=f"{documento.rotulo} rejeitado na conferência documental",
        objeto=documento,
        usuario=usuario,
    )
    # Também na rejeição: o contrato volta a esperar envio, não fica "em análise".
    _reavaliar_contratos(documento)

    perfil = _perfil_de(documento)
    habilitacao = perfil.habilitacao if perfil else None
    if habilitacao and habilitacao.status != StatusHabilitacao.COM_PENDENCIA:
        habilitacao.status = StatusHabilitacao.COM_PENDENCIA
        habilitacao.save()

    return habilitacao


def _reavaliar_habilitacao(documento: DocumentoCadastral, *, usuario=None):
    """Move a habilitação do perfil conforme o estado real do dossiê.

    A regra em si mora em `contrapartes.servicos`: ela também vale na abertura do
    perfil, quando não houve aprovação nenhuma para disparar este caminho.
    """
    perfil = _perfil_de(documento)
    if perfil is None:
        return None
    return avancar_habilitacao(perfil.habilitacao, usuario=usuario)
