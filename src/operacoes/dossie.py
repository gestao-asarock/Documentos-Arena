"""
Dossiê do contrato: tudo que foi checado, por quem e quando (AGENTS.md §4.10).

É o que o Clube vê antes de assinar e o que sustenta a operação numa auditoria.

Uma regra vale para o arquivo inteiro: **cada checagem aparece uma única vez**.
As etapas do contrato são a fonte da verdade; o parecer de crédito e o de
compliance entram como detalhe da etapa correspondente, não como item à parte.
"""

from dataclasses import dataclass, field

from contrapartes.models import Habilitacao
from documentos.models import StatusDocumento

from .estados import ETAPAS_DA_HABILITACAO, Etapa, StatusEtapa, StatusOperacao

#: Contrato que não chegou a existir: não há PDF para levar à assinatura.
ESTADOS_SEM_CONTRATO = frozenset(
    {
        StatusOperacao.REPROVADA,
        StatusOperacao.CANCELADA,
        StatusOperacao.DISPENSADA,
    }
)

#: Situações possíveis de uma checagem — mapeadas para cor no template.
CONCLUIDA = "concluida"
PENDENTE = "pendente"
ATENCAO = "atencao"
EXTERNA = "externa"


@dataclass
class Checagem:
    titulo: str
    situacao: str
    responsavel: str = ""
    data: object = None
    detalhe: str = ""
    itens: list = field(default_factory=list)


def _do_perfil(habilitacao: Habilitacao | None) -> list[Checagem]:
    """As validações do perfil, que não se repetem por contrato (D29)."""
    if habilitacao is None:
        return [Checagem("Perfil da contraparte", PENDENTE, detalhe="Perfil não validado.")]

    aprovados = [
        f"{d.rotulo}: {d.get_status_display()}"
        for d in habilitacao.contraparte.documentos_cadastrais.select_related("tipo", "subtipo")
        if d.status == StatusDocumento.APROVADO
    ]
    checagens = [
        Checagem(
            "Documentos base do perfil",
            CONCLUIDA if aprovados else PENDENTE,
            detalhe=(
                f"{len(aprovados)} documento(s) aprovados no cadastro."
                if aprovados
                else "Nenhum documento aprovado no cadastro."
            ),
            itens=aprovados,
        )
    ]

    parecer = getattr(habilitacao, "parecer_compliance", None)
    if parecer and parecer.esta_concluido:
        checagens.append(
            Checagem(
                "Due diligence (Compliance)",
                CONCLUIDA,
                responsavel=str(parecer.analista or "-"),
                data=parecer.data_conclusao,
                detalhe=f"{parecer.get_veredito_display()}. {parecer.justificativa}",
                itens=[f"{rotulo}: {texto}" for rotulo, texto in parecer.blocos_preenchidos()],
            )
        )
    else:
        checagens.append(Checagem("Due diligence (Compliance)", PENDENTE))

    checagens.append(_credito_do_perfil(habilitacao))
    return checagens


def _credito_do_perfil(habilitacao: Habilitacao) -> Checagem:
    """A análise de crédito acontece na esteira do perfil, uma vez só (D30)."""
    from credito.models import ParecerCredito

    parecer = next(
        (
            p
            for p in ParecerCredito.objects.filter(contraparte_id=habilitacao.contraparte_id)
            if p.esta_vigente
        ),
        None,
    )
    if parecer is None:
        return Checagem(
            "Risco e crédito (perfil)",
            PENDENTE,
            detalhe="Perfil validado antes de o crédito entrar na esteira.",
        )

    return Checagem(
        "Risco e crédito (perfil)",
        CONCLUIDA,
        responsavel=str(parecer.analista or "-"),
        data=parecer.data_conclusao,
        detalhe=f"{parecer.get_veredito_display()}. {parecer.justificativa}",
        itens=[f"{rotulo}: {texto}" for rotulo, texto in parecer.blocos_preenchidos()],
    )


def _documentos_do_contrato(operacao) -> Checagem:
    """Estado real da documentação: aprovada, em conferência, ou faltando."""
    situacao = operacao.situacao_documental()

    itens = [f"{d.rotulo}: {d.get_status_display()}" for d in situacao["aprovados"]]
    itens += [f"{d.rotulo}: em conferência" for d in situacao["em_analise"]]
    itens += [f"{d.rotulo}: {d.get_status_display()}" for d in situacao["com_problema"]]
    itens += [f"{tipo.nome}: não enviado" for tipo in situacao["faltando"]]

    if not operacao.documentos_exigidos():
        return Checagem(
            "Documentos do contrato", CONCLUIDA, detalhe="Nenhuma exigência além do perfil."
        )

    if operacao.documentacao_completa:
        estado, detalhe = CONCLUIDA, "Documentação conferida e aprovada."
    elif situacao["com_problema"]:
        estado, detalhe = ATENCAO, "Documento recusado: precisa de reenvio."
    elif situacao["faltando"]:
        estado, detalhe = PENDENTE, "Falta enviar documento exigido."
    else:
        estado, detalhe = PENDENTE, "Enviado, aguardando conferência."

    return Checagem("Documentos do contrato", estado, detalhe=detalhe, itens=itens)


def _situacao_da_etapa(etapa) -> str:
    if etapa.status == StatusEtapa.APROVADA:
        return CONCLUIDA
    if etapa.status == StatusEtapa.REPROVADA:
        return ATENCAO
    if etapa.status == StatusEtapa.REGISTRADA_EXTERNAMENTE:
        # Acontece na Genial, fora do sistema: dizer "concluída" seria mentira.
        return EXTERNA
    return PENDENTE


def montar(operacao) -> list[Checagem]:
    """Todas as checagens do contrato, sem repetir nenhuma."""
    checagens = _do_perfil(operacao.contraparte.habilitacao_vigente)
    checagens.append(_documentos_do_contrato(operacao))

    for etapa in operacao.etapas.all():
        # Triagem, due diligence e crédito já entraram pelo perfil — não repetir.
        if Etapa(etapa.etapa) in ETAPAS_DA_HABILITACAO:
            continue

        situacao = _situacao_da_etapa(etapa)
        checagens.append(
            Checagem(
                etapa.get_etapa_display(),
                situacao,
                responsavel=str(etapa.decidida_por or ""),
                data=etapa.data_decisao,
                detalhe=etapa.parecer
                or ("Fora do sistema, na Genial." if situacao == EXTERNA else ""),
            )
        )

    return checagens


def pronto_para_assinatura(operacao) -> bool:
    """Só libera o download quando tudo que precede a assinatura passou.

    A etapa de assinatura em si é cumprida pelo download: baixar registra quem
    baixou e quando. Um contrato já baixado continua liberado — o Clube pode
    precisar do PDF de novo, e rebaixar não reabre nem reescreve nada. O que
    fecha a porta é o contrato ter dado errado: reprovado, cancelado ou
    dispensado.
    """
    if operacao.status in ESTADOS_SEM_CONTRATO or not operacao.documentacao_completa:
        return False

    for etapa in operacao.etapas.all():
        if etapa.etapa == Etapa.ASSINATURAS:
            continue
        if etapa.status in {StatusEtapa.PENDENTE, StatusEtapa.EM_ANALISE}:
            return False
    return True
