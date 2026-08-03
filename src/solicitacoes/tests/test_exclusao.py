"""
Exclusão de documento enviado por engano (AGENTS.md §6).

O documento sai, o registro da exclusão fica na auditoria.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import Acao, EventoAuditoria
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def usuario_clube():
    usuario = Usuario.objects.create_user(username="clube.exclusao", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def solicitacao(usuario_clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    return Solicitacao.objects.create(contraparte=contraparte, criada_por=usuario_clube)


@pytest.fixture
def documento(solicitacao, usuario_clube):
    registro = DocumentoCadastral.objects.create(
        contraparte=solicitacao.contraparte,
        tipo=solicitacao.pendencias_cadastrais()[0],
        enviado_por=usuario_clube,
    )
    ArquivoDocumento.objects.create(
        documento=registro,
        arquivo=SimpleUploadedFile("comprovante.pdf", PDF),
        nome_original="comprovante.pdf",
    )
    return registro


def _excluir(client, solicitacao, documento):
    return client.post(
        reverse("solicitacoes:excluir_documento", args=[solicitacao.pk, documento.pk])
    )


def test_exclui_documento_e_seus_arquivos(client, usuario_clube, solicitacao, documento):
    caminho = documento.arquivos.first().arquivo.name
    client.force_login(usuario_clube)

    _excluir(client, solicitacao, documento)

    assert not DocumentoCadastral.objects.filter(pk=documento.pk).exists()
    assert not ArquivoDocumento.objects.exists()
    # Documento de identidade não pode ficar órfão no storage.
    assert not default_storage.exists(caminho)


def test_exclusao_fica_na_auditoria(client, usuario_clube, solicitacao, documento):
    client.force_login(usuario_clube)

    _excluir(client, solicitacao, documento)

    evento = EventoAuditoria.objects.filter(acao=Acao.EXCLUSAO_DOCUMENTO).first()
    assert evento is not None
    assert evento.usuario == usuario_clube


def test_documento_aprovado_nao_e_excluido(client, usuario_clube, solicitacao, documento):
    """Ele já sustentou uma decisão; apagá-lo desfaria a base do parecer."""
    documento.status = StatusDocumento.APROVADO
    documento.save()
    client.force_login(usuario_clube)

    _excluir(client, solicitacao, documento)

    assert DocumentoCadastral.objects.filter(pk=documento.pk).exists()


def test_documento_volta_a_ser_pendencia_apos_exclusao(
    client, usuario_clube, solicitacao, documento
):
    client.force_login(usuario_clube)
    tipo = documento.tipo

    _excluir(client, solicitacao, documento)

    kit = solicitacao.contraparte.situacao_do_kit()
    assert tipo in kit["faltando"]


def test_outro_usuario_do_clube_nao_exclui(client, solicitacao, documento):
    outro = Usuario.objects.create_user(username="clube.terceiro", password="senha-de-teste")
    outro.groups.add(Group.objects.get(name=Papel.CLUBE))
    client.force_login(outro)

    resposta = _excluir(client, solicitacao, documento)

    assert resposta.status_code == 404
    assert DocumentoCadastral.objects.filter(pk=documento.pk).exists()


def test_get_nao_exclui(client, usuario_clube, solicitacao, documento):
    """Exclusão só por POST: link visitado por engano não apaga nada."""
    client.force_login(usuario_clube)

    client.get(reverse("solicitacoes:excluir_documento", args=[solicitacao.pk, documento.pk]))

    assert DocumentoCadastral.objects.filter(pk=documento.pk).exists()


def test_botao_de_exclusao_some_quando_o_documento_e_aprovado(
    client, usuario_clube, solicitacao, documento
):
    url_exclusao = reverse("solicitacoes:excluir_documento", args=[solicitacao.pk, documento.pk])
    client.force_login(usuario_clube)
    detalhe = reverse("solicitacoes:detalhe", args=[solicitacao.pk])

    # Enviado: o botão está lá.
    assert url_exclusao in client.get(detalhe).content.decode()

    documento.status = StatusDocumento.APROVADO
    documento.save()

    assert url_exclusao not in client.get(detalhe).content.decode()
