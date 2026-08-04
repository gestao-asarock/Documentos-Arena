"""
Crédito na esteira do perfil (AGENTS.md D30).

A análise da pessoa acontece uma vez, sem valor de referência, e vale até que um
contrato mude de tipo ou de faixa.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group

from contas.models import Papel, Usuario
from contrapartes.models import Contraparte, Habilitacao, StatusHabilitacao
from credito.models import Veredito
from credito.servicos import (
    ParecerIncompleto,
    concluir_parecer_do_perfil,
    fila_de_perfis,
    obter_ou_criar_parecer_do_perfil,
    recusar_perfil,
)
from operacoes.estados import Etapa, StatusEtapa
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar
from solicitacoes.models import Solicitacao, StatusSolicitacao

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def crm():
    return _usuario("crm.perfil", Papel.CRM)


@pytest.fixture
def habilitacao(crm):
    contraparte = Contraparte.objects.create(nome="Contratante Fictício", documento="58974790890")
    registro = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.EM_CREDITO
    )
    Solicitacao.objects.create(contraparte=contraparte, habilitacao=registro, criada_por=crm)
    return registro


def _concluir(habilitacao, crm, veredito=Veredito.BAIXO):
    parecer = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=crm)
    parecer.veredito = veredito
    parecer.justificativa = "Score 812, nada consta."
    concluir_parecer_do_perfil(parecer, habilitacao, usuario=crm)
    return parecer


def _contrato(contraparte, crm, valor="2000.00"):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor_total=Decimal(valor),
        criada_por=crm,
    )
    return enquadrar(operacao, usuario=crm)


def test_fila_traz_perfis_em_credito(habilitacao):
    assert list(fila_de_perfis()) == [habilitacao]


def test_perfil_nao_e_validado_sem_credito(habilitacao):
    """O erro que o responsável apontou: perfil virava contrato sem passar por crédito."""
    assert not habilitacao.contraparte.esta_habilitada


def test_contrato_de_perfil_sem_parecer_ainda_assim_nao_pede_credito(habilitacao, crm):
    """Perfis validados antes da mudança não reabrem crédito no contrato.

    A etapa vem cumprida com a nota de que veio do perfil; se for preciso
    reanalisar, isso é revalidação do perfil (AGENTS.md D30).
    """
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.save()

    contrato = _contrato(habilitacao.contraparte, crm)
    etapa = contrato.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.CUMPRIDA_NA_HABILITACAO


def test_parecer_do_perfil_nasce_sem_enquadramento(habilitacao, crm):
    parecer = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=crm)

    assert parecer.regra is None


def test_concluir_exige_veredito_e_justificativa(habilitacao, crm):
    parecer = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=crm)

    with pytest.raises(ParecerIncompleto):
        concluir_parecer_do_perfil(parecer, habilitacao, usuario=crm)


def test_conclusao_valida_o_perfil(habilitacao, crm):
    _concluir(habilitacao, crm)
    habilitacao.refresh_from_db()
    perfil = habilitacao.solicitacoes.first()
    perfil.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.HABILITADA
    assert habilitacao.contraparte.esta_habilitada
    assert perfil.status == StatusSolicitacao.PRONTA_PARA_CONTRATO


def test_contrato_aproveita_o_credito_do_perfil(habilitacao, crm):
    """O contrato não refaz a análise: ela é do perfil (AGENTS.md D30)."""
    _concluir(habilitacao, crm)

    contrato = _contrato(habilitacao.contraparte, crm)
    etapa = contrato.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.CUMPRIDA_NA_HABILITACAO
    assert "Risco baixo" in etapa.parecer


def test_recusa_no_credito_barra_o_perfil(habilitacao, crm):
    recusar_perfil(habilitacao, usuario=crm, motivo="Restrições graves.")
    habilitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.RECUSADA
    assert not habilitacao.contraparte.esta_habilitada
