"""
Percurso do fluxo piloto: da criação à conclusão (AGENTS.md §4.1 e §4.7).

O estado da operação é derivado das etapas pendentes, nunca assumido.
"""

import pytest

from operacoes.estados import ORDEM_ETAPAS, Etapa, StatusEtapa, StatusOperacao
from operacoes.servicos import decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db


def _decidir_ate(operacao, ultima: Etapa, usuario):
    """Aprova as etapas em ordem, parando depois de `ultima`."""
    limite = ORDEM_ETAPAS.index(ultima)
    while (etapa := operacao.etapa_atual) is not None:
        if ORDEM_ETAPAS.index(Etapa(etapa.etapa)) > limite:
            break
        decidir_etapa(etapa, aprovada=True, parecer="Conferido.", usuario=usuario)
        operacao.refresh_from_db()
    return operacao


def test_etapas_do_perfil_chegam_cumpridas(criar_operacao, regra_piloto, usuario):
    """O contrato não refaz triagem nem due diligence (AGENTS.md D29)."""
    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)

    cumpridas = {
        e.etapa for e in operacao.etapas.filter(status=StatusEtapa.CUMPRIDA_NA_HABILITACAO)
    }

    assert cumpridas == {Etapa.TRIAGEM, Etapa.DUE_DILIGENCE}
    # Crédito depende do valor e é analisado por contrato (D30).
    assert operacao.etapa_atual.etapa == Etapa.RISCO_CREDITO


def test_apos_juridico_a_bola_passa_para_o_clube(criar_operacao, regra_piloto, usuario):
    """Assinatura é etapa do Clube: o estado próprio deixa isso visível."""
    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)
    _decidir_ate(operacao, Etapa.JURIDICO, usuario)

    assert operacao.status == StatusOperacao.AGUARDANDO_ASSINATURA
    assert operacao.etapa_atual.etapa == Etapa.ASSINATURAS


def test_fluxo_completo_conclui_a_operacao(criar_operacao, regra_piloto, usuario):
    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)
    _decidir_ate(operacao, Etapa.LIQUIDACAO, usuario)

    assert operacao.etapa_atual is None
    assert operacao.status == StatusOperacao.CONCLUIDA


def test_reprovacao_no_meio_interrompe_o_fluxo(criar_operacao, regra_piloto, usuario):
    """Reprovar o jurídico para o contrato antes da assinatura."""
    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)

    decidir_etapa(
        operacao.etapa_atual,
        aprovada=False,
        parecer="Cláusula de rescisão incompatível com o modelo.",
        usuario=usuario,
    )
    operacao.refresh_from_db()

    assert operacao.status == StatusOperacao.REPROVADA
    assert operacao.motivo_reprovacao == "Cláusula de rescisão incompatível com o modelo."
    # A assinatura continua pendente: o fluxo parou, não foi concluído.
    assert operacao.etapas.filter(status=StatusEtapa.PENDENTE).exists()


def test_operacao_reprovada_nao_recebe_novas_decisoes(criar_operacao, regra_piloto, usuario):
    from operacoes.estados import TransicaoInvalida

    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)
    primeira = operacao.etapa_atual
    decidir_etapa(primeira, aprovada=False, parecer="Sem documentação.", usuario=usuario)
    operacao.refresh_from_db()

    with pytest.raises(TransicaoInvalida):
        decidir_etapa(operacao.etapa_atual, aprovada=True, parecer="Tentativa.", usuario=usuario)
