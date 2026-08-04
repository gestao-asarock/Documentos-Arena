"""
Situação dos documentos do contrato (AGENTS.md §4.5).

O mesmo documento aparecia como "vinculado" e "faltando" ao mesmo tempo — e,
como o subtipo tem outro nome, parecia ser dois documentos diferentes.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analise.servicos import aprovar_documento, rejeitar_documento
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def crm(db):
    usuario = Usuario.objects.create_user(username="crm.situacao", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def contrato(contraparte, crm):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    return enquadrar(operacao, usuario=crm)


def _enviar(contrato, crm, status=StatusDocumento.ENVIADO):
    tipo = contrato.documentos_exigidos()[0]
    documento = DocumentoCadastral.objects.create(
        contraparte=contrato.contraparte,
        tipo=tipo,
        subtipo=tipo.subtipos.get(nome="Termo de Adesão (preenchido)"),
        status=status,
        enviado_por=crm,
    )
    ArquivoDocumento.objects.create(
        documento=documento, arquivo=SimpleUploadedFile("termo.pdf", PDF)
    )
    contrato.documentos.add(documento)
    return documento


def test_sem_envio_o_tipo_esta_faltando(contrato):
    situacao = contrato.situacao_documental()

    assert [t.nome for t in situacao["faltando"]] == ["Contrato entre o Fundo e o Cessionário"]
    assert situacao["em_analise"] == []


def test_enviado_sai_de_faltando_e_vai_para_analise(contrato, crm):
    """O termo enviado não pode continuar listado como faltando."""
    documento = _enviar(contrato, crm)

    situacao = contrato.situacao_documental()

    assert situacao["faltando"] == []
    assert situacao["em_analise"] == [documento]
    # Mas ainda não conta como completo: enviar não é aprovar.
    assert not contrato.documentacao_completa


def test_aprovado_vai_para_aprovados(contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)
    contrato.refresh_from_db()

    situacao = contrato.situacao_documental()

    assert situacao["aprovados"] == [documento]
    assert situacao["faltando"] == []
    assert contrato.documentacao_completa


def test_rejeitado_volta_a_pedir_envio(contrato, crm):
    documento = _enviar(contrato, crm)
    rejeitar_documento(documento, usuario=crm, motivo="Valor divergente do contrato.")
    contrato.refresh_from_db()

    tipos = [t.nome for t in contrato.tipos_a_enviar()]

    assert "Contrato entre o Fundo e o Cessionário" in tipos


def test_em_analise_nao_pede_novo_envio(contrato, crm):
    """Enquanto está na fila, não se pede o mesmo documento de novo."""
    _enviar(contrato, crm)

    assert contrato.tipos_a_enviar() == []


def test_tela_nao_mostra_o_mesmo_documento_em_dois_lugares(client, contrato, crm):
    _enviar(contrato, crm)
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato.pk]))
    corpo = resposta.content.decode()

    assert resposta.context["situacao"]["faltando"] == []
    assert "Aguardando conferência" in corpo
    assert "Faltando enviar" not in corpo


def test_aviso_do_topo_reflete_a_conferencia(client, contrato, crm):
    _enviar(contrato, crm)
    client.force_login(crm)

    corpo = client.get(reverse("operacoes:detalhe", args=[contrato.pk])).content.decode()

    assert "aguardando conferência" in corpo
    assert "Falta enviar" not in corpo


def test_nao_diz_completa_com_documento_em_analise(client, contrato, crm):
    """Dizia 'aguardando conferência' e '✓ completa' na mesma tela."""
    _enviar(contrato, crm)
    client.force_login(crm)

    corpo = client.get(reverse("operacoes:detalhe", args=[contrato.pk])).content.decode()

    assert "Aguardando conferência" in corpo
    assert "Documentação do contrato completa" not in corpo


def test_diz_completa_apos_aprovacao(client, contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)
    client.force_login(crm)

    corpo = client.get(reverse("operacoes:detalhe", args=[contrato.pk])).content.decode()

    assert "Documentação do contrato completa e aprovada" in corpo
    assert "Aguardando conferência" not in corpo
