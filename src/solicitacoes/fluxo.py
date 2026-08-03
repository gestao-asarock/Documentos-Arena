"""
Linha do tempo da validação do perfil (AGENTS.md §4.10, D29).

Requisito de produto: mostrar o que passou, o que está em andamento, o que falta
e o que está travado. Aqui só se descreve — a regra de estado mora nos serviços.
"""

from dataclasses import dataclass

from contrapartes.models import StatusHabilitacao

#: Etapas da validação do perfil, na ordem da esteira (AGENTS.md D29, D30).
ETAPAS_DO_PERFIL = [
    (StatusHabilitacao.AGUARDANDO_DOCUMENTOS, "Documentos base"),
    (StatusHabilitacao.EM_ANALISE_DOCUMENTAL, "Conferência dos documentos"),
    (StatusHabilitacao.EM_COMPLIANCE, "Due diligence (Compliance)"),
    (StatusHabilitacao.EM_CREDITO, "Análise de crédito"),
    (StatusHabilitacao.HABILITADA, "Perfil validado"),
]


@dataclass
class PassoFluxo:
    rotulo: str
    situacao: str  # concluida | atual | travada | futura
    detalhe: str = ""


def montar(perfil) -> list[PassoFluxo]:
    """Descreve o andamento do perfil, dos documentos base à validação."""
    habilitacao = perfil.habilitacao
    if habilitacao is None:
        return [PassoFluxo(rotulo, "futura") for _, rotulo in ETAPAS_DO_PERFIL]

    if habilitacao.status == StatusHabilitacao.RECUSADA:
        return [PassoFluxo("Perfil recusado", "travada", habilitacao.motivo_recusa)]

    ordem = [status for status, _ in ETAPAS_DO_PERFIL]

    # `COM_PENDENCIA` não é uma etapa: é a conferência, travada (§4.6).
    status_atual = habilitacao.status
    travada = status_atual == StatusHabilitacao.COM_PENDENCIA
    if travada:
        status_atual = StatusHabilitacao.EM_ANALISE_DOCUMENTAL

    posicao = ordem.index(status_atual) if status_atual in ordem else 0
    passos: list[PassoFluxo] = []

    for indice, (status, rotulo) in enumerate(ETAPAS_DO_PERFIL):
        if status == StatusHabilitacao.HABILITADA and habilitacao.esta_vigente:
            situacao = "concluida"
        elif indice < posicao:
            situacao = "concluida"
        elif indice > posicao:
            situacao = "futura"
        else:
            situacao = "travada" if travada else "atual"

        detalhe = ""
        if status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS and situacao == "atual":
            faltam = len(perfil.pendencias_cadastrais())
            plural = "s" if faltam != 1 else ""
            detalhe = f"{faltam} documento{plural} pendente{plural}"
        elif situacao == "travada":
            detalhe = "Pendência aberta: corrija para prosseguir"

        passos.append(PassoFluxo(rotulo, situacao, detalhe))

    return passos
