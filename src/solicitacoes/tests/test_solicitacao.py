"""
Cadastro e validação do perfil da contraparte (AGENTS.md §4.0, D19, D29).

O perfil não conhece valor nem evento: por isso serve a vários contratos.
"""

from datetime import timedelta

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
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario():
    return Usuario.objects.create_user(username="clube.operador", password="senha-de-teste")


@pytest.fixture
def criar_perfil(usuario):
    def _criar(documento: str, **extra) -> Solicitacao:
        contraparte, _ = obter_ou_criar_contraparte(
            documento=documento,
            dados={"nome": extra.pop("nome", "Contratante Fictício")},
        )
        return Solicitacao.objects.create(contraparte=contraparte, criada_por=usuario, **extra)

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


def test_kit_do_perfil_pf_nao_depende_de_valor(criar_perfil):
    """Comprovação de renda é do contrato, não do perfil (AGENTS.md D29)."""
    perfil = criar_perfil("58974790890")

    nomes = {t.nome for t in perfil.pendencias_cadastrais()}

    assert nomes == {
        "Documento de identificação (RG, CPF e/ou CNH)",
        "Comprovante de residência",
    }
    assert "Holerite" not in nomes
    assert not perfil.kit_completo


def test_kit_do_perfil_pj(criar_perfil):
    perfil = criar_perfil("00000000000191", nome="Fornecedora Fictícia Ltda")

    nomes = {t.nome for t in perfil.pendencias_cadastrais()}

    assert "Contrato Social / Última Alteração Contratual" in nomes
    assert "Procuração" not in nomes  # condicional


def test_abrir_habilitacao(criar_perfil, usuario):
    perfil = criar_perfil("58974790890")

    habilitacao = abrir_habilitacao(perfil, usuario=usuario)
    perfil.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    assert perfil.status == StatusSolicitacao.EM_HABILITACAO


def test_perfil_validado_e_reaproveitado(criar_perfil, usuario):
    """Segundo cadastro da mesma contraparte não refaz a validação (D19)."""
    primeiro = criar_perfil("58974790890")
    habilitacao = abrir_habilitacao(primeiro, usuario=usuario)
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.data_validade = timezone.localdate() + timedelta(days=180)
    habilitacao.save()

    segundo = criar_perfil("58974790890")
    reaproveitada = abrir_habilitacao(segundo, usuario=usuario)
    segundo.refresh_from_db()

    assert reaproveitada == habilitacao
    assert segundo.status == StatusSolicitacao.PRONTA_PARA_CONTRATO
    assert habilitacao.contraparte.habilitacoes.count() == 1


def test_perfil_vencido_nao_e_reaproveitado(criar_perfil, usuario):
    primeiro = criar_perfil("58974790890")
    habilitacao = abrir_habilitacao(primeiro, usuario=usuario)
    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.data_validade = timezone.localdate() - timedelta(days=1)
    habilitacao.save()

    segundo = criar_perfil("58974790890")
    nova = abrir_habilitacao(segundo, usuario=usuario)

    assert nova != habilitacao
    assert nova.status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS


def test_contraparte_so_fica_habilitada_com_status(criar_perfil, usuario):
    perfil = criar_perfil("58974790890")
    habilitacao = abrir_habilitacao(perfil, usuario=usuario)
    contraparte = perfil.contraparte

    assert not contraparte.esta_habilitada

    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.save()

    assert contraparte.habilitacao_vigente == habilitacao


def test_kit_completo_quando_documentos_aprovados(criar_perfil):
    perfil = criar_perfil("58974790890")

    for tipo in perfil.pendencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=perfil.contraparte,
            tipo=tipo,
            status=StatusDocumento.APROVADO,
            data_emissao=timezone.localdate(),
        )
        ArquivoDocumento.objects.create(documento=documento, arquivo="cadastral/ficticio.pdf")

    assert perfil.kit_completo
