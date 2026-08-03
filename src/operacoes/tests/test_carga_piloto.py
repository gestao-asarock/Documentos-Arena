"""A carga inicial precisa refletir o guia — se divergir, o guia prevalece."""

from decimal import Decimal

import pytest

from operacoes.models import RegraEnquadramento
from operacoes.servicos import encontrar_regra

pytestmark = pytest.mark.django_db


def test_apenas_o_piloto_esta_implementado():
    """O MVP roda um enquadramento por vez (AGENTS.md D11)."""
    implementadas = RegraEnquadramento.objects.filter(implementada=True)

    assert implementadas.count() == 1
    assert implementadas.get().criterio == "Evento até R$ 5.000,00"


def test_piloto_exige_todas_as_alcadas_da_matriz():
    regra = RegraEnquadramento.objects.get(criterio="Evento até R$ 5.000,00")

    assert regra.exige_triagem
    assert regra.exige_due_diligence
    assert regra.exige_risco_credito
    assert regra.exige_juridico
    assert regra.exige_assinaturas
    assert regra.exige_boletagem
    assert not regra.waiver


def test_piloto_exige_o_contrato_com_o_cessionario():
    regra = RegraEnquadramento.objects.get(criterio="Evento até R$ 5.000,00")
    exigidos = {e.tipo_documento.nome for e in regra.exigencias.all()}

    assert exigidos == {"Contrato entre o Fundo e o Cessionário"}


def test_operacao_de_5000_reais_e_enquadrada_pela_carga():
    """Fronteira do guia, agora contra os dados reais de produção."""
    regra = RegraEnquadramento.objects.get(criterio="Evento até R$ 5.000,00")

    assert encontrar_regra(regra.tipo_operacao_id, Decimal("5000.00")) == regra
