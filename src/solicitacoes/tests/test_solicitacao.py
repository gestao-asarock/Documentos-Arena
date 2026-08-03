"""
Fase 1: solicitação, dedução de PF/PJ e abertura da habilitação (AGENTS.md §4.0).

A habilitação é da contraparte e é reaproveitada entre contratos (D19).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from contas.models import Usuario
from contrapartes.models import (
    ArquivoDocumento,
    Contraparte,
    DocumentoCadastral,
    StatusHabilitacao,
)
from documentos.models import StatusDocumento, TipoPessoa
from operacoes.models import TipoOperacao
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return Usuario.objects.create_user(username="clube.operador", password="senha-de-teste")


@pytest.fixture
def aluguel():
    return TipoOperacao.objects.get(nome="Aluguel de Espaço")


@pytest.fixture
def criar_solicitacao(usuario, aluguel):
    def _criar(documento: str, valor: str, **extra) -> Solicitacao:
        contraparte, _ = obter_ou_criar_contraparte(
            documento=documento,
            dados={"nome": extra.pop("nome", "Contratante Fictício")},
        )
        return Solicitacao.objects.create(
            contraparte=contraparte,
            tipo_operacao=aluguel,
            descricao="Formatura de balé",
            data_evento=timezone.localdate() + timedelta(days=30),
            valor=Decimal(valor),
            criada_por=usuario,
            **extra,
        )

    return _criar


def test_contraparte_e_criada_com_tipo_deduzido():
    contraparte, criada = obter_ou_criar_contraparte(
        documento="589.747.908-90", dados={"nome": "Gabriel Fictício"}
    )

    assert criada
    assert contraparte.tipo_pessoa == TipoPessoa.FISICA
    assert contraparte.documento == "58974790890"


def test_contraparte_existente_e_reaproveitada():
    """Mesmo CPF/CNPJ não vira cadastro duplicado."""
    obter_ou_criar_contraparte(documento="58974790890", dados={"nome": "Gabriel Fictício"})

    contraparte, criada = obter_ou_criar_contraparte(
        documento="589.747.908-90", dados={"email": "ficticio@exemplo.com.br"}
    )

    assert not criada
    assert Contraparte.objects.count() == 1
    assert contraparte.email == "ficticio@exemplo.com.br"
    assert contraparte.nome == "Gabriel Fictício"


def test_solicitacao_pf_pede_o_kit_de_pessoa_fisica(criar_solicitacao):
    solicitacao = criar_solicitacao("58974790890", "2000.00")

    nomes = {t.nome for t in solicitacao.pendencias_cadastrais()}

    assert nomes == {
        "Documento de identificação (RG, CPF e/ou CNH)",
        "Comprovante de residência",
    }
    assert not solicitacao.kit_completo


def test_solicitacao_pf_acima_de_4000_pede_comprovacao_de_renda(criar_solicitacao):
    """Regra do responsável, não do guia (AGENTS.md D20)."""
    solicitacao = criar_solicitacao("58974790890", "4000.01")

    nomes = {t.nome for t in solicitacao.pendencias_cadastrais()}

    assert {"Holerite", "Declaração de Imposto de Renda"} <= nomes


def test_abrir_habilitacao_marca_credito_conforme_a_matriz(criar_solicitacao, usuario):
    """O piloto exige Risco/Crédito; a habilitação nasce sabendo disso."""
    solicitacao = criar_solicitacao("58974790890", "2000.00")

    habilitacao = abrir_habilitacao(solicitacao, usuario=usuario)
    solicitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    assert habilitacao.exige_credito
    assert solicitacao.status == StatusSolicitacao.EM_HABILITACAO


def test_habilitacao_vigente_e_reaproveitada(criar_solicitacao, usuario):
    """Segundo pedido com a mesma contraparte entra direto na Fase 2 (D19)."""
    primeira = criar_solicitacao("58974790890", "2000.00")
    habilitacao = abrir_habilitacao(primeira, usuario=usuario)
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.data_validade = timezone.localdate() + timedelta(days=180)
    habilitacao.save()

    segunda = criar_solicitacao("58974790890", "3000.00")
    reaproveitada = abrir_habilitacao(segunda, usuario=usuario)
    segunda.refresh_from_db()

    assert reaproveitada == habilitacao
    assert segunda.status == StatusSolicitacao.PRONTA_PARA_CONTRATO
    assert habilitacao.contraparte.habilitacoes.count() == 1


def test_habilitacao_vencida_nao_e_reaproveitada(criar_solicitacao, usuario):
    primeira = criar_solicitacao("58974790890", "2000.00")
    habilitacao = abrir_habilitacao(primeira, usuario=usuario)
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.data_validade = timezone.localdate() - timedelta(days=1)
    habilitacao.save()

    segunda = criar_solicitacao("58974790890", "3000.00")
    nova = abrir_habilitacao(segunda, usuario=usuario)

    assert nova != habilitacao
    assert nova.status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS


def test_contraparte_so_fica_habilitada_com_status_e_prazo(criar_solicitacao, usuario):
    solicitacao = criar_solicitacao("58974790890", "2000.00")
    habilitacao = abrir_habilitacao(solicitacao, usuario=usuario)
    contraparte = solicitacao.contraparte

    assert not contraparte.esta_habilitada

    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.save()

    assert contraparte.habilitacao_vigente == habilitacao


def test_kit_completo_quando_documentos_aprovados(criar_solicitacao):
    solicitacao = criar_solicitacao("58974790890", "2000.00")

    for tipo in solicitacao.pendencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=solicitacao.contraparte,
            tipo=tipo,
            status=StatusDocumento.APROVADO,
            data_emissao=timezone.localdate(),
        )
        ArquivoDocumento.objects.create(documento=documento, arquivo="cadastral/ficticio.pdf")

    assert solicitacao.kit_completo
