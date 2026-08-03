"""Transições de estado, inclusive as inválidas (AGENTS.md §4.7)."""

import pytest
from django.core.exceptions import ValidationError

from operacoes.estados import StatusEtapa, StatusOperacao, TransicaoInvalida
from operacoes.servicos import decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db


def test_nao_enquadra_operacao_duas_vezes(criar_operacao, regra_piloto):
    operacao = enquadrar(criar_operacao("1000.00"))

    with pytest.raises(TransicaoInvalida):
        enquadrar(operacao)


def test_transicao_invalida_levanta_excecao(criar_operacao, regra_piloto):
    """Rascunho não salta direto para assinatura."""
    operacao = criar_operacao("1000.00")

    with pytest.raises(TransicaoInvalida):
        operacao._transicionar(StatusOperacao.AGUARDANDO_ASSINATURA)


def test_reprovacao_exige_motivo(criar_operacao, regra_piloto):
    operacao = enquadrar(criar_operacao("1000.00"))

    with pytest.raises(ValidationError):
        operacao.reprovar("   ")


def test_reprovacao_encerra_a_operacao(criar_operacao, regra_piloto):
    operacao = enquadrar(criar_operacao("1000.00"))
    operacao.reprovar("Contrato social divergente do cadastro.")

    assert operacao.status == StatusOperacao.REPROVADA
    assert operacao.esta_encerrada

    with pytest.raises(TransicaoInvalida):
        operacao.reprovar("Outro motivo qualquer.")


def test_decisao_de_etapa_exige_parecer(criar_operacao, regra_piloto, usuario):
    operacao = enquadrar(criar_operacao("1000.00"))
    etapa = operacao.etapa_atual

    with pytest.raises(ValueError):
        decidir_etapa(etapa, aprovada=True, parecer="", usuario=usuario)


def test_reprovar_etapa_reprova_a_operacao(criar_operacao, regra_piloto, usuario):
    operacao = enquadrar(criar_operacao("1000.00"))
    etapa = operacao.etapa_atual

    decidir_etapa(etapa, aprovada=False, parecer="Documentação incompleta.", usuario=usuario)
    operacao.refresh_from_db()

    assert etapa.status == StatusEtapa.REPROVADA
    assert operacao.status == StatusOperacao.REPROVADA


def test_etapa_nao_e_decidida_duas_vezes(criar_operacao, regra_piloto, usuario):
    operacao = enquadrar(criar_operacao("1000.00"))
    etapa = operacao.etapa_atual
    decidir_etapa(etapa, aprovada=True, parecer="Documentos conferidos.", usuario=usuario)

    with pytest.raises(TransicaoInvalida):
        decidir_etapa(etapa, aprovada=True, parecer="De novo.", usuario=usuario)


def test_valor_congelado_apos_o_inicio(criar_operacao, regra_piloto):
    """AGENTS.md D13: valor e tipo imutáveis fora do rascunho."""
    from decimal import Decimal

    operacao = enquadrar(criar_operacao("1000.00"))
    operacao.valor_total = Decimal("4500.00")

    with pytest.raises(ValidationError):
        operacao.clean()
