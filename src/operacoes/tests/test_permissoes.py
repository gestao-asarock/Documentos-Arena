"""Cada etapa é decidida pelo papel responsável (AGENTS.md §4.2)."""

import pytest
from django.contrib.auth.models import Group

from contas.models import Papel, Usuario
from operacoes.estados import Etapa
from operacoes.permissoes import pode_criar_operacao, pode_decidir
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db


def _usuario(papel: str) -> Usuario:
    # Prefixo próprio: a fixture `usuario` do conftest já ocupa "crm.teste".
    pessoa = Usuario.objects.create_user(username=f"papel.{papel}", password="senha-de-teste")
    pessoa.groups.add(Group.objects.get(name=papel))
    return pessoa


@pytest.fixture
def etapas(criar_operacao, regra_piloto, usuario):
    operacao = enquadrar(criar_operacao("3000.00"), usuario=usuario)
    return {Etapa(e.etapa): e for e in operacao.etapas.all()}


@pytest.mark.parametrize(
    ("papel", "etapa", "permitido"),
    [
        (Papel.CRM, Etapa.TRIAGEM, True),
        # Compliance ajuda na triagem: é quem sofre documento mal triado (D34).
        (Papel.COMPLIANCE, Etapa.TRIAGEM, True),
        (Papel.COMPLIANCE, Etapa.DUE_DILIGENCE, True),
        (Papel.JURIDICO, Etapa.DUE_DILIGENCE, False),
        (Papel.JURIDICO, Etapa.JURIDICO, True),
        (Papel.CLUBE, Etapa.JURIDICO, False),
        (Papel.CLUBE, Etapa.ASSINATURAS, True),
    ],
)
def test_papel_decide_apenas_a_propria_etapa(etapas, papel, etapa, permitido):
    assert pode_decidir(_usuario(papel), etapas[etapa]) is permitido


def test_risco_credito_e_registrado_pelo_crm(etapas):
    """Risco não tem usuário no MVP; o CRM registra em seu nome (D9, D34)."""
    assert pode_decidir(_usuario(Papel.CRM), etapas[Etapa.RISCO_CREDITO])
    assert not pode_decidir(_usuario(Papel.COMPLIANCE), etapas[Etapa.RISCO_CREDITO])


def test_administrador_decide_qualquer_etapa(etapas):
    administrador = _usuario(Papel.ADMINISTRADOR)

    assert all(pode_decidir(administrador, etapa) for etapa in etapas.values())


def test_quem_pode_criar_operacao():
    assert pode_criar_operacao(_usuario(Papel.CRM))
    assert pode_criar_operacao(_usuario(Papel.CLUBE))
    assert not pode_criar_operacao(_usuario(Papel.JURIDICO))
