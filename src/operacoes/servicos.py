"""
Serviços de operação: enquadramento e avanço do fluxo (AGENTS.md §4.4).

Toda regra de negócio mora aqui ou no modelo — nunca na view.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar

from .estados import (
    ETAPAS_DA_HABILITACAO,
    ETAPAS_NO_ESCOPO,
    Etapa,
    StatusEtapa,
    StatusOperacao,
    TransicaoInvalida,
)
from .models import EtapaAprovacao, Operacao, RegraEnquadramento


class EnquadramentoNaoEncontrado(Exception):
    """Nenhuma regra ativa cobre este tipo de operação e valor."""


class EnquadramentoAmbiguo(Exception):
    """Mais de uma regra cobre o mesmo valor — a tabela de regras está inconsistente."""


def encontrar_regra(tipo_operacao_id: int, valor: Decimal) -> RegraEnquadramento:
    """Localiza a regra que enquadra a operação.

    Faixas são inclusivas nos dois extremos. Sobreposição de faixas é erro de
    cadastro e falha alto: enquadrar errado significa aprovar com a alçada errada.
    """
    candidatas = [
        regra
        for regra in RegraEnquadramento.objects.filter(
            tipo_operacao_id=tipo_operacao_id, ativa=True, implementada=True
        )
        if regra.cobre(valor)
    ]

    if not candidatas:
        raise EnquadramentoNaoEncontrado(
            "Nenhum enquadramento implementado cobre este tipo de operação e valor. "
            "No MVP apenas o fluxo piloto está liberado (AGENTS.md §4.3)."
        )
    if len(candidatas) > 1:
        criterios = ", ".join(r.criterio for r in candidatas)
        raise EnquadramentoAmbiguo(
            f"O valor cai em mais de uma faixa ({criterios}). Corrija a tabela de regras."
        )
    return candidatas[0]


class ContraparteNaoHabilitada(Exception):
    """A Fase 2 só começa com a contraparte habilitada e a habilitação vigente."""


def _status_inicial_da_etapa(etapa: Etapa, operacao: Operacao) -> str:
    """Como cada etapa nasce num contrato.

    Triagem e due diligence vieram do perfil; as três últimas acontecem na
    Genial. O crédito depende do valor: reaproveita o parecer se já houver um
    vigente para este mesmo enquadramento (AGENTS.md D30).
    """
    if etapa in ETAPAS_DA_HABILITACAO:
        return StatusEtapa.CUMPRIDA_NA_HABILITACAO
    if etapa == Etapa.RISCO_CREDITO and _parecer_de_credito_vigente(operacao):
        return StatusEtapa.CUMPRIDA_NA_HABILITACAO
    if etapa in ETAPAS_NO_ESCOPO:
        return StatusEtapa.PENDENTE
    return StatusEtapa.REGISTRADA_EXTERNAMENTE


def _parecer_de_credito_vigente(operacao: Operacao):
    """Parecer de crédito já concluído para esta contraparte neste enquadramento."""
    from credito.models import ParecerCredito

    for parecer in ParecerCredito.objects.filter(
        contraparte_id=operacao.contraparte_id, regra_id=operacao.regra_id
    ):
        if parecer.esta_vigente:
            return parecer
    return None


def _parecer_da_habilitacao(etapa: Etapa, habilitacao, operacao: Operacao) -> str:
    """Traz para a etapa o resultado já obtido, para não perder o rastro."""
    if etapa == Etapa.TRIAGEM:
        return f"Documentos base conferidos no perfil #{habilitacao.pk}."

    if etapa == Etapa.DUE_DILIGENCE:
        parecer = getattr(habilitacao, "parecer_compliance", None)
        if parecer is None or not parecer.veredito:
            return f"Cumprida na validação do perfil #{habilitacao.pk}."
        return f"Perfil #{habilitacao.pk} — {parecer.get_veredito_display()}: {parecer.justificativa}"

    if etapa == Etapa.RISCO_CREDITO:
        parecer = _parecer_de_credito_vigente(operacao)
        if parecer is None:
            return ""
        return (
            f"Parecer de crédito reaproveitado ({parecer.regra.criterio}) — "
            f"{parecer.get_veredito_display()}: {parecer.justificativa}"
        )

    return ""


@transaction.atomic
def enquadrar(operacao: Operacao, *, usuario=None) -> Operacao:
    """Enquadra a operação e gera as etapas exigidas.

    A partir daqui valor e tipo ficam congelados (AGENTS.md D13).
    """
    if not operacao.esta_em_rascunho:
        raise TransicaoInvalida("A operação já foi enquadrada.")

    habilitacao = operacao.contraparte.habilitacao_vigente
    if habilitacao is None:
        raise ContraparteNaoHabilitada(
            "A contraparte precisa estar habilitada antes do contrato: "
            "kit cadastral, due diligence e crédito acontecem na Fase 1."
        )

    regra = encontrar_regra(operacao.tipo_operacao_id, operacao.valor_total)
    operacao.regra = regra

    if regra.waiver:
        # Compras até R$ 10.000,00: dispensadas de documentação e de todas as
        # etapas de aprovação. É regra da tabela, não atalho de código.
        operacao.status = StatusOperacao.DISPENSADA
        operacao.save()
        registrar(
            acao=Acao.DISPENSA,
            descricao=f"Operação #{operacao.pk} dispensada por waiver: {regra.criterio}",
            objeto=operacao,
            usuario=usuario,
        )
        return operacao

    operacao.status = StatusOperacao.AGUARDANDO_DOCUMENTOS
    operacao.save()

    EtapaAprovacao.objects.bulk_create(
        [
            EtapaAprovacao(
                operacao=operacao,
                etapa=etapa,
                status=_status_inicial_da_etapa(etapa, operacao),
                parecer=_parecer_da_habilitacao(etapa, habilitacao, operacao),
            )
            for etapa in regra.etapas_exigidas()
        ]
    )

    registrar(
        acao=Acao.ENQUADRAMENTO,
        descricao=f"Operação #{operacao.pk} enquadrada como '{regra.criterio}'",
        objeto=operacao,
        usuario=usuario,
    )
    return operacao


@transaction.atomic
def decidir_etapa(
    etapa: EtapaAprovacao, *, aprovada: bool, parecer: str, usuario=None
) -> EtapaAprovacao:
    """Registra a decisão humana de uma etapa.

    A IA nunca decide: ela produz evidência, a decisão é humana e auditada
    (AGENTS.md §5.1).
    """
    if etapa.esta_decidida:
        raise TransicaoInvalida("Esta etapa já foi decidida.")
    if not parecer.strip():
        raise ValueError("O parecer é obrigatório para registrar a decisão.")

    operacao = etapa.operacao
    if operacao.esta_encerrada:
        raise TransicaoInvalida("Operação encerrada não recebe novas decisões.")

    etapa.status = StatusEtapa.APROVADA if aprovada else StatusEtapa.REPROVADA
    etapa.parecer = parecer
    etapa.decidida_por = usuario
    etapa.data_decisao = timezone.now()
    etapa.save()

    registrar(
        acao=Acao.APROVACAO if aprovada else Acao.REPROVACAO,
        descricao=f"{etapa.get_etapa_display()} da operação #{operacao.pk}",
        objeto=operacao,
        usuario=usuario,
    )

    if aprovada:
        avancar(operacao, etapa_decidida=Etapa(etapa.etapa))
    else:
        # Reprovação em qualquer etapa interrompe o fluxo (AGENTS.md §4.7).
        operacao.reprovar(parecer)
        operacao.save()

    return etapa


def avancar(operacao: Operacao, *, etapa_decidida: Etapa | None = None) -> Operacao:
    """Leva a operação ao estado correspondente às etapas já decididas.

    O fluxo não é linear: as etapas aplicáveis vêm do enquadramento, então o
    estado é derivado do que resta pendente, nunca assumido (AGENTS.md §4.7).
    """
    if operacao.esta_encerrada:
        return operacao

    # A assinatura é do Clube e acontece fora do nosso controle: o estado
    # próprio existe para deixar visível que a bola está com eles.
    assinatura_registrada = (
        etapa_decidida == Etapa.ASSINATURAS
        and operacao.status == StatusOperacao.AGUARDANDO_ASSINATURA
    )
    if assinatura_registrada:
        operacao._transicionar(StatusOperacao.ASSINADA)
        operacao.save()

    proxima = operacao.etapa_atual

    if proxima is None:
        if operacao.status != StatusOperacao.CONCLUIDA:
            operacao._transicionar(StatusOperacao.CONCLUIDA)
            operacao.save()
        return operacao

    if proxima.etapa == Etapa.ASSINATURAS:
        destino = StatusOperacao.AGUARDANDO_ASSINATURA
    elif proxima.etapa == Etapa.RISCO_CREDITO:
        destino = StatusOperacao.EM_CREDITO
    elif not operacao.documentacao_completa:
        # Sem os documentos do contrato não há o que analisar.
        destino = StatusOperacao.AGUARDANDO_DOCUMENTOS
    else:
        destino = StatusOperacao.EM_APROVACAO

    if operacao.status != destino:
        operacao._transicionar(destino)
        operacao.save()

    return operacao


def solicitacoes_prontas_para_contrato(usuario):
    """Solicitações cuja contraparte já está habilitada e ainda não viraram contrato."""
    from solicitacoes.models import StatusSolicitacao
    from solicitacoes.servicos import solicitacoes_visiveis_para

    return (
        solicitacoes_visiveis_para(usuario)
        .filter(status=StatusSolicitacao.PRONTA_PARA_CONTRATO)
        .exclude(operacoes__isnull=False)
    )


def operacoes_visiveis_para(usuario):
    """Queryset filtrado por papel.

    O usuário do Clube é externo: enxerga apenas o que seu time criou, sem
    pareceres internos (AGENTS.md §4.2).
    """
    base = Operacao.objects.select_related("contraparte", "tipo_operacao", "regra")
    if usuario.is_superuser or usuario.eh_interno:
        return base
    if usuario.eh_do_clube:
        return base.filter(criada_por=usuario)
    return base.none()


__all__ = [
    "EnquadramentoAmbiguo",
    "EnquadramentoNaoEncontrado",
    "avancar",
    "decidir_etapa",
    "encontrar_regra",
    "enquadrar",
    "operacoes_visiveis_para",
    "Etapa",
]
