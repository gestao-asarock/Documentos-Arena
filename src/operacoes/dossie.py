"""
Dossiê do contrato: tudo que foi checado, por quem e quando (AGENTS.md §4.10).

É o que o Clube vê antes de assinar e o que sustenta a operação numa auditoria.

Uma regra vale para o arquivo inteiro: **cada checagem aparece uma única vez**.
As etapas do contrato são a fonte da verdade; o parecer de crédito e o de
compliance entram como detalhe da etapa correspondente, não como item à parte.
"""

from dataclasses import dataclass, field

from django.urls import reverse

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
class Anexo:
    """Arquivo que sustenta a checagem, baixável de dentro do dossiê."""

    titulo: str
    url: str
    descricao: str = ""


@dataclass
class Checagem:
    titulo: str
    situacao: str
    responsavel: str = ""
    data: object = None
    detalhe: str = ""
    itens: list = field(default_factory=list)
    #: Texto que a área escreveu (justificativa do veredito, por exemplo).
    observacao: str = ""
    anexos: list = field(default_factory=list)


def _anexos_do_parecer(parecer, operacao, origem: str) -> list[Anexo]:
    """Relatórios de compliance ou de crédito, com link de download.

    Quem assina precisa poder ler o parecer inteiro, não só o veredito: é o que
    sustenta a assinatura numa auditoria (AGENTS.md §4.10).
    """
    return [
        Anexo(
            titulo=relatorio.nome_original or "relatório",
            url=reverse("operacoes:baixar_relatorio", args=[operacao.pk, origem, relatorio.pk]),
            descricao=relatorio.descricao,
        )
        for relatorio in parecer.relatorios.all()
    ]


def _do_perfil(habilitacao: Habilitacao | None, operacao) -> list[Checagem]:
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
                detalhe=f"{parecer.get_veredito_display()}.",
                observacao=parecer.justificativa,
                anexos=_anexos_do_parecer(parecer, operacao, "compliance"),
            )
        )
    else:
        checagens.append(Checagem("Due diligence (Compliance)", PENDENTE))

    checagens.append(_credito_do_perfil(habilitacao, operacao))
    return checagens


def _credito_do_perfil(habilitacao: Habilitacao, operacao) -> Checagem:
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
        detalhe=f"{parecer.get_veredito_display()}.",
        observacao=parecer.justificativa,
        anexos=_anexos_do_parecer(parecer, operacao, "credito"),
    )


def _documentos_do_contrato(operacao) -> Checagem:
    """Estado real da documentação: enviada, recusada, ou faltando.

    **Enviar já conclui esta checagem**, mesmo antes da conferência. O que ela
    responde é "o Clube fez a parte dele?", e conferir o conteúdo é trabalho da
    revisão jurídica, que aparece logo abaixo como a etapa pendente. Enquanto
    dizia "pendente" com o documento já enviado, a tela cobrava duas vezes a
    mesma coisa e escondia de quem lê onde a bola realmente está.
    """
    situacao = operacao.situacao_documental()

    itens = [f"{d.rotulo}: {d.get_status_display()}" for d in situacao["aprovados"]]
    itens += [f"{d.rotulo}: em conferência" for d in situacao["em_analise"]]
    itens += [f"{d.rotulo}: {d.get_status_display()}" for d in situacao["com_problema"]]
    itens += [f"{tipo.nome}: não enviado" for tipo in situacao["faltando"]]

    if not operacao.documentos_exigidos():
        return Checagem(
            "Documentos do contrato", CONCLUIDA, detalhe="Nenhuma exigência além do perfil."
        )

    if situacao["com_problema"]:
        estado, detalhe = ATENCAO, "Documento recusado: precisa de reenvio."
    elif situacao["faltando"]:
        estado, detalhe = PENDENTE, "Falta enviar documento exigido."
    elif operacao.documentacao_completa:
        estado, detalhe = CONCLUIDA, "Documentação conferida e aprovada."
    else:
        estado, detalhe = CONCLUIDA, "Documentação enviada; a conferência é da revisão jurídica."

    envio = _ultimo_envio(operacao)
    return Checagem(
        "Documentos do contrato",
        estado,
        responsavel=str(envio.enviado_por or "-") if envio else "",
        data=envio.data_envio if envio else None,
        detalhe=detalhe,
        itens=itens,
    )


def _ultimo_envio(operacao):
    """O documento mais recente do contrato: diz quem enviou e quando."""
    return operacao.documentos.order_by("-data_envio").first()


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
    checagens = _do_perfil(operacao.contraparte.habilitacao_vigente, operacao)
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
