"""
Análise de risco e crédito (AGENTS.md §4.8, D9 e D23).

É a última etapa da Fase 1: concluir aqui habilita a contraparte.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import StatusHabilitacao
from credito.models import ParecerCredito, Veredito
from credito.servicos import (
    ParecerIncompleto,
    concluir_parecer,
    fila_de_credito,
    obter_ou_criar_parecer,
    pode_analisar,
    recusar_contraparte,
)
from operacoes.models import TipoOperacao
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.credito", Papel.CLUBE)


@pytest.fixture
def crm():
    return _usuario("crm.credito", Papel.CRM)


@pytest.fixture
def solicitacao(clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    return Solicitacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor=Decimal("2000.00"),
        criada_por=clube,
    )


@pytest.fixture
def habilitacao(solicitacao, clube):
    registro = abrir_habilitacao(solicitacao, usuario=clube)
    registro.status = StatusHabilitacao.EM_CREDITO
    registro.save()
    return registro


def test_fila_traz_quem_esta_em_credito(habilitacao):
    assert list(fila_de_credito()) == [habilitacao]


def test_crm_e_compliance_registram_o_parecer():
    """O time de Risco não é usuário no MVP (D9)."""
    assert pode_analisar(_usuario("crm.perm", Papel.CRM))
    assert pode_analisar(_usuario("compliance.perm", Papel.COMPLIANCE))
    assert not pode_analisar(_usuario("clube.perm", Papel.CLUBE))
    assert not pode_analisar(_usuario("juridico.perm", Papel.JURIDICO))


def test_clube_nao_acessa(client, clube, habilitacao):
    client.force_login(clube)

    assert client.get(reverse("credito:fila")).status_code == 403
    assert client.get(reverse("credito:parecer", args=[habilitacao.pk])).status_code == 403


def test_concluir_exige_veredito_e_justificativa(habilitacao, crm):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=crm)

    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, usuario=crm)

    parecer.veredito = Veredito.BAIXO
    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, usuario=crm)


def test_conclusao_habilita_a_contraparte(habilitacao, solicitacao, crm):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=crm)
    parecer.veredito = Veredito.BAIXO
    parecer.justificativa = "Sem restrições; renda compatível com o valor."

    concluir_parecer(parecer, usuario=crm)
    habilitacao.refresh_from_db()
    solicitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.HABILITADA
    assert habilitacao.contraparte.esta_habilitada
    assert habilitacao.data_conclusao is not None
    # A Fase 2 pode começar.
    assert solicitacao.status == StatusSolicitacao.PRONTA_PARA_CONTRATO


def test_recusa_encerra_o_fluxo(habilitacao, crm):
    recusar_contraparte(habilitacao, usuario=crm, motivo="Restrições financeiras graves.")
    habilitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.RECUSADA
    assert not habilitacao.contraparte.esta_habilitada


def test_recusa_exige_motivo(habilitacao, crm):
    with pytest.raises(ParecerIncompleto):
        recusar_contraparte(habilitacao, usuario=crm, motivo="")


def test_parecer_pela_tela_conclui(client, habilitacao, crm):
    client.force_login(crm)

    client.post(
        reverse("credito:parecer", args=[habilitacao.pk]),
        {
            "consulta": "Serasa consultado em 03/08/2026, score 812.",
            "restricoes": "Nada consta.",
            "pendencias": "Nada consta.",
            "capacidade": "Renda declarada compatível com R$ 2.000,00.",
            "balanco": "",
            "veredito": Veredito.BAIXO,
            "justificativa": "Sem restrições.",
            "registrado_em_nome_do_time": "on",
            "acao": "concluir",
        },
    )

    parecer = ParecerCredito.objects.get(habilitacao=habilitacao)
    habilitacao.refresh_from_db()

    assert parecer.esta_concluido
    assert habilitacao.status == StatusHabilitacao.HABILITADA


def test_blocos_em_branco_sao_listados(habilitacao, crm):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=crm)
    parecer.consulta = "Score 700."
    parecer.save()

    em_branco = parecer.blocos_em_branco()

    assert "Consulta de crédito (Serasa e afins)" not in em_branco
    assert "Balanço, DRE e faturamento" in em_branco
