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
from credito.models import ParecerCredito, Veredito
from credito.servicos import (
    ParecerIncompleto,
    concluir_parecer_do_perfil,
    fila_de_perfis,
    obter_ou_criar_parecer_do_perfil,
    recusar_perfil,
)
from operacoes.estados import Etapa, StatusEtapa
from operacoes.models import Operacao, RegraEnquadramento, TipoOperacao
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
    contraparte = Contraparte.objects.create(
        nome="Contratante Fictício", documento="58974790890"
    )
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


def test_primeiro_contrato_aproveita_o_credito_do_perfil(habilitacao, crm):
    """Não se refaz a análise logo em seguida (AGENTS.md D30)."""
    _concluir(habilitacao, crm)

    contrato = _contrato(habilitacao.contraparte, crm)
    etapa = contrato.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.CUMPRIDA_NA_HABILITACAO
    assert "análise do perfil" in etapa.parecer


def test_primeiro_contrato_ancora_o_parecer_no_enquadramento(habilitacao, crm):
    """A partir daí, outro tipo ou outra faixa exigem análise nova."""
    _concluir(habilitacao, crm)

    contrato = _contrato(habilitacao.contraparte, crm)
    parecer = ParecerCredito.objects.get(contraparte=habilitacao.contraparte)

    assert parecer.regra == contrato.regra
    assert parecer.operacao == contrato


def test_contrato_de_outro_enquadramento_exige_nova_analise(habilitacao, crm):
    _concluir(habilitacao, crm)
    _contrato(habilitacao.contraparte, crm)

    # Enquadramento diferente: outro tipo de operação com regra própria.
    outro_tipo = TipoOperacao.objects.create(nome="Serviços NQA")
    RegraEnquadramento.objects.create(
        tipo_operacao=outro_tipo,
        criterio="Prestadores até R$ 5.000,00/mês",
        valor_minimo=Decimal("0.01"),
        valor_maximo=Decimal("5000.00"),
        exige_risco_credito=True,
        implementada=True,
    )
    outro = Operacao.objects.create(
        contraparte=habilitacao.contraparte,
        tipo_operacao=outro_tipo,
        descricao="Serviço de manutenção",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    enquadrar(outro, usuario=crm)

    etapa = outro.etapas.get(etapa=Etapa.RISCO_CREDITO)
    assert etapa.status == StatusEtapa.PENDENTE


def test_perfil_validado_sem_parecer_cai_na_fila_do_contrato(habilitacao, crm):
    """Perfis validados antes de o crédito entrar na esteira não têm parecer.

    O contrato então pede a análise em vez de presumir que ela existiu — é o que
    acontece com os cadastros anteriores à mudança (AGENTS.md D30).
    """
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.save()
    assert not ParecerCredito.objects.filter(contraparte=habilitacao.contraparte).exists()

    contrato = _contrato(habilitacao.contraparte, crm)
    etapa = contrato.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.PENDENTE
    assert contrato.status.startswith("aguardando") or contrato.status == "em_credito"


def test_recusa_no_credito_barra_o_perfil(habilitacao, crm):
    recusar_perfil(habilitacao, usuario=crm, motivo="Restrições graves.")
    habilitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.RECUSADA
    assert not habilitacao.contraparte.esta_habilitada
