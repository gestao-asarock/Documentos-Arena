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


def _status_inicial_da_etapa(etapa: Etapa) -> str:
    """Como cada etapa nasce num contrato.

    Triagem, due diligence e crédito vieram do perfil; as três últimas acontecem
    na Genial. Ao contrato restam a revisão jurídica e a assinatura.
    """
    if etapa in ETAPAS_DA_HABILITACAO:
        return StatusEtapa.CUMPRIDA_NA_HABILITACAO
    if etapa in ETAPAS_NO_ESCOPO:
        return StatusEtapa.PENDENTE
    return StatusEtapa.REGISTRADA_EXTERNAMENTE


def _parecer_de_credito_vigente(operacao: Operacao):
    """Parecer de crédito que cobre este contrato, se houver (AGENTS.md D30).

    Serve o parecer já ancorado neste enquadramento ou, na falta dele, o parecer
    do perfil ainda não usado por contrato nenhum — que é o caso do primeiro
    contrato depois da validação.
    """
    from credito.models import ParecerCredito

    pareceres = ParecerCredito.objects.filter(contraparte_id=operacao.contraparte_id)

    for parecer in pareceres.filter(regra_id=operacao.regra_id):
        if parecer.esta_vigente:
            return parecer

    for parecer in pareceres.filter(regra__isnull=True):
        if parecer.esta_vigente:
            return parecer
    return None


def _ancorar_parecer_de_credito(operacao: Operacao) -> None:
    """Fixa o parecer do perfil no enquadramento do primeiro contrato que o usa.

    A partir daí, contrato de outro tipo ou de outra faixa não o reaproveita e
    exige análise nova — que é a regra que o responsável definiu (D30).
    """
    parecer = _parecer_de_credito_vigente(operacao)
    if parecer is not None and parecer.regra_id is None:
        parecer.regra = operacao.regra
        parecer.operacao = operacao
        parecer.save(update_fields=["regra", "operacao"])


def _parecer_da_habilitacao(etapa: Etapa, habilitacao, operacao: Operacao) -> str:
    """Traz para a etapa o resultado já obtido, para não perder o rastro."""
    if etapa == Etapa.TRIAGEM:
        return f"Documentos base conferidos no perfil #{habilitacao.pk}."

    if etapa == Etapa.DUE_DILIGENCE:
        parecer = getattr(habilitacao, "parecer_compliance", None)
        if parecer is None or not parecer.veredito:
            return f"Cumprida na validação do perfil #{habilitacao.pk}."
        return (
            f"Perfil #{habilitacao.pk} — {parecer.get_veredito_display()}: {parecer.justificativa}"
        )

    if etapa == Etapa.RISCO_CREDITO:
        parecer = _parecer_de_credito_vigente(operacao)
        if parecer is None:
            return f"Cumprida na validação do perfil #{habilitacao.pk}."
        return (
            f"Perfil #{habilitacao.pk} — {parecer.get_veredito_display()}: "
            f"{parecer.justificativa}"
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
                status=_status_inicial_da_etapa(etapa),
                parecer=_parecer_da_habilitacao(etapa, habilitacao, operacao),
            )
            for etapa in regra.etapas_exigidas()
        ]
    )

    _ancorar_parecer_de_credito(operacao)

    registrar(
        acao=Acao.ENQUADRAMENTO,
        descricao=f"Operação #{operacao.pk} enquadrada como '{regra.criterio}'",
        objeto=operacao,
        usuario=usuario,
    )

    # Sem isto o contrato nascia parado: nada o levava à primeira etapa real.
    return avancar(operacao)


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

    # O fluxo é linear: ninguém analisa o que ainda não foi enviado. Sem isto era
    # possível aprovar a revisão jurídica de um contrato inexistente.
    if not operacao.documentacao_completa:
        faltando = ", ".join(tipo.nome for tipo in operacao.documentos_pendentes())
        raise TransicaoInvalida(
            f"Documentação incompleta: falta {faltando}. "
            "Envie e aprove os documentos antes de decidir as etapas."
        )

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


def registrar_download_para_assinatura(operacao: Operacao, *, usuario) -> EtapaAprovacao | None:
    """Cumpre a etapa de assinatura no ato do download do contrato.

    A etapa 5 é do Clube e não é um julgamento: não há o que aprovar ou reprovar
    num contrato que já passou por todas as checagens. O que a marca como
    cumprida é o Clube levar o PDF para assinar — então é o download que a
    fecha, guardando quem baixou e quando.

    Devolve a etapa cumprida, ou `None` quando não havia o que cumprir (contrato
    sem etapa de assinatura, ou já baixado antes — rebaixar não reescreve a data
    do primeiro download).
    """
    etapa = next(
        (e for e in operacao.etapas.all() if e.etapa == Etapa.ASSINATURAS),
        None,
    )
    if etapa is None or etapa.esta_decidida:
        return None

    etapa.status = StatusEtapa.APROVADA
    etapa.decidida_por = usuario
    etapa.data_decisao = timezone.now()
    etapa.parecer = "Contrato baixado pelo Clube para coleta de assinaturas."
    etapa.save()

    registrar(
        acao=Acao.APROVACAO,
        descricao=f"{etapa.get_etapa_display()} da operação #{operacao.pk} cumprida por download",
        objeto=operacao,
        usuario=usuario,
    )

    avancar(operacao, etapa_decidida=Etapa.ASSINATURAS)
    return etapa


def avancar(operacao: Operacao, *, etapa_decidida: Etapa | None = None) -> Operacao:
    """Leva a operação ao estado correspondente às etapas já decididas.

    O fluxo não é linear: as etapas aplicáveis vêm do enquadramento, então o
    estado é derivado do que resta pendente, nunca assumido (AGENTS.md §4.7).
    """
    if operacao.esta_encerrada:
        return operacao

    # Rascunho ainda não foi enquadrado: não tem etapas, e "nenhuma etapa
    # pendente" aqui não significa concluído.
    if operacao.esta_em_rascunho:
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

    # A ordem importa: sem os documentos do contrato não há o que analisar, então
    # a falta deles vem antes de qualquer etapa. E falta enviar é diferente de
    # enviado esperando conferência — o estado precisa dizer qual dos dois é.
    if not operacao.documentacao_completa:
        situacao = operacao.situacao_documental()
        esperando_conferencia = (
            situacao["em_analise"] and not situacao["faltando"] and not situacao["com_problema"]
        )
        destino = (
            StatusOperacao.EM_ANALISE_DOCUMENTAL
            if esperando_conferencia
            else StatusOperacao.AGUARDANDO_DOCUMENTOS
        )
    elif proxima.etapa == Etapa.ASSINATURAS:
        destino = StatusOperacao.AGUARDANDO_ASSINATURA
    else:
        destino = StatusOperacao.EM_APROVACAO

    if operacao.status != destino:
        operacao._transicionar(destino)
        operacao.save()

    return operacao


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
    "registrar_download_para_assinatura",
    "Etapa",
]
