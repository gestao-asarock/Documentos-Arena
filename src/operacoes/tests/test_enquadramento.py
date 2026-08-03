"""
Testes de enquadramento, com fronteira em cada limite de valor (AGENTS.md §8).

Enquadrar errado é o pior defeito possível do sistema: aprova com a alçada errada.
"""

from decimal import Decimal

import pytest

from operacoes.estados import Etapa, StatusEtapa, StatusOperacao
from operacoes.models import RegraEnquadramento
from operacoes.servicos import (
    EnquadramentoAmbiguo,
    EnquadramentoNaoEncontrado,
    encontrar_regra,
    enquadrar,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "valor",
    ["0.01", "2500.00", "4999.99", "5000.00"],
    ids=["minimo", "meio", "centavo_antes_do_limite", "exatamente_no_limite"],
)
def test_valores_dentro_da_faixa_sao_enquadrados(valor, regra_piloto, aluguel):
    """O limite de R$ 5.000,00 é inclusivo: 'até R$ 5.000,00' inclui o próprio."""
    regra = encontrar_regra(aluguel.id, Decimal(valor))
    assert regra == regra_piloto


@pytest.mark.parametrize("valor", ["5000.01", "9999.99"])
def test_valor_acima_do_limite_nao_tem_enquadramento(valor, regra_piloto, aluguel):
    """Acima de R$ 5.000,00 seria 'Jogo ou Temporada', ainda não implementado."""
    with pytest.raises(EnquadramentoNaoEncontrado):
        encontrar_regra(aluguel.id, Decimal(valor))


def test_regra_nao_implementada_e_ignorada(regra_piloto, aluguel):
    """O MVP roda um enquadramento por vez (AGENTS.md D11)."""
    regra_piloto.implementada = False
    regra_piloto.save()

    with pytest.raises(EnquadramentoNaoEncontrado):
        encontrar_regra(aluguel.id, Decimal("1000.00"))


def test_faixas_sobrepostas_falham_alto(regra_piloto, aluguel):
    """Tabela inconsistente não pode enquadrar em silêncio pela primeira que achar."""
    RegraEnquadramento.objects.create(
        tipo_operacao=aluguel,
        criterio="Faixa cadastrada errada, sobreposta",
        valor_minimo=Decimal("1000.00"),
        valor_maximo=Decimal("8000.00"),
        implementada=True,
    )

    with pytest.raises(EnquadramentoAmbiguo):
        encontrar_regra(aluguel.id, Decimal("2000.00"))


def test_enquadrar_gera_as_etapas_da_matriz(criar_operacao, regra_piloto, usuario):
    """O piloto exerce as seis colunas da matriz (AGENTS.md §4.3)."""
    operacao = enquadrar(criar_operacao("4000.00"), usuario=usuario)

    # Esta regra de teste não tem exigência documental, então o contrato já
    # começa na primeira etapa a decidir — o crédito (AGENTS.md D30).
    assert operacao.status == StatusOperacao.EM_CREDITO
    assert operacao.regra == regra_piloto

    etapas = {e.etapa for e in operacao.etapas.all()}
    assert etapas == {
        Etapa.TRIAGEM,
        Etapa.DUE_DILIGENCE,
        Etapa.RISCO_CREDITO,
        Etapa.JURIDICO,
        Etapa.ASSINATURAS,
        Etapa.ENVIO_NF,
        Etapa.BOLETAGEM,
        Etapa.LIQUIDACAO,
    }


def test_etapas_nascem_no_estado_certo(criar_operacao, regra_piloto):
    """Cada etapa nasce conforme onde de fato acontece (AGENTS.md §4.0, D8)."""
    operacao = enquadrar(criar_operacao("1000.00"))

    por_etapa = {e.etapa: e.status for e in operacao.etapas.all()}

    # Perfil: resolvidas na validação da contraparte, não se repetem por contrato.
    assert por_etapa[Etapa.TRIAGEM] == StatusEtapa.CUMPRIDA_NA_HABILITACAO
    assert por_etapa[Etapa.DUE_DILIGENCE] == StatusEtapa.CUMPRIDA_NA_HABILITACAO
    # Crédito é do contrato: depende do valor (AGENTS.md D30).
    assert por_etapa[Etapa.RISCO_CREDITO] == StatusEtapa.PENDENTE
    assert por_etapa[Etapa.JURIDICO] == StatusEtapa.PENDENTE
    assert por_etapa[Etapa.ASSINATURAS] == StatusEtapa.PENDENTE
    # Genial: só registro.
    assert por_etapa[Etapa.BOLETAGEM] == StatusEtapa.REGISTRADA_EXTERNAMENTE
    assert por_etapa[Etapa.LIQUIDACAO] == StatusEtapa.REGISTRADA_EXTERNAMENTE


def test_contrato_exige_contraparte_habilitada(
    contraparte_sem_habilitacao, aluguel, usuario, regra_piloto
):
    """Não existe contrato sem passar pela Fase 1 (AGENTS.md §4.0)."""
    from decimal import Decimal

    from operacoes.models import Operacao
    from operacoes.servicos import ContraparteNaoHabilitada

    operacao = Operacao.objects.create(
        contraparte=contraparte_sem_habilitacao,
        tipo_operacao=aluguel,
        valor_total=Decimal("1000.00"),
        descricao="Contrato sem habilitação",
        criada_por=usuario,
    )

    with pytest.raises(ContraparteNaoHabilitada):
        enquadrar(operacao)


def test_primeira_etapa_a_trabalhar_e_o_credito(criar_operacao, regra_piloto):
    """O piloto exige Risco/Crédito, e ele não vem do perfil (AGENTS.md D30)."""
    operacao = enquadrar(criar_operacao("1000.00"))

    assert operacao.etapa_atual.etapa == Etapa.RISCO_CREDITO


def test_fluxo_sem_compliance_e_risco_nao_gera_essas_etapas(criar_operacao, aluguel):
    """Reembolso pula Compliance e Risco — o motor precisa respeitar a matriz."""
    RegraEnquadramento.objects.create(
        tipo_operacao=aluguel,
        criterio="Fluxo curto de teste",
        valor_minimo=Decimal("0.01"),
        valor_maximo=Decimal("5000.00"),
        exige_triagem=True,
        exige_due_diligence=False,
        exige_risco_credito=False,
        exige_juridico=True,
        exige_assinaturas=True,
        exige_boletagem=True,
        implementada=True,
    )

    operacao = enquadrar(criar_operacao("100.00"))
    etapas = {e.etapa for e in operacao.etapas.all()}

    assert Etapa.DUE_DILIGENCE not in etapas
    assert Etapa.RISCO_CREDITO not in etapas
    assert Etapa.TRIAGEM in etapas


def test_waiver_dispensa_documentacao_e_etapas(criar_operacao, aluguel):
    """Compras até R$ 10.000,00: dispensa total, com registro (AGENTS.md §4.4)."""
    RegraEnquadramento.objects.create(
        tipo_operacao=aluguel,
        criterio="Waiver de teste",
        valor_minimo=Decimal("0.01"),
        valor_maximo=Decimal("10000.00"),
        waiver=True,
        implementada=True,
    )

    operacao = enquadrar(criar_operacao("500.00"))

    assert operacao.status == StatusOperacao.DISPENSADA
    assert operacao.etapas.count() == 0
