"""
Guarda e entrega de arquivos (AGENTS.md §5.4, §6).

Documento de identidade não pode ser baixável por quem tem a URL: o acesso passa
por permissão e é auditado.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import Acao, EventoAuditoria
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from operacoes.models import TipoOperacao
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def usuario_clube():
    usuario = Usuario.objects.create_user(username="clube.arquivos", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def solicitacao(usuario_clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    return Solicitacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor=Decimal("2000.00"),
        criada_por=usuario_clube,
    )


@pytest.fixture
def arquivo(solicitacao, usuario_clube):
    documento = DocumentoCadastral.objects.create(
        contraparte=solicitacao.contraparte,
        tipo=solicitacao.pendencias_cadastrais()[0],
        enviado_por=usuario_clube,
    )
    return ArquivoDocumento.objects.create(
        documento=documento,
        arquivo=SimpleUploadedFile("rg-joao-silva.pdf", PDF),
        nome_original="rg-joao-silva.pdf",
    )


def test_nome_no_disco_nao_revela_o_titular(arquivo):
    """O nome enviado fica só no banco; no disco vai um identificador aleatório."""
    assert "joao-silva" not in arquivo.arquivo.name
    assert arquivo.arquivo.name.endswith(".pdf")
    assert arquivo.nome_original == "rg-joao-silva.pdf"


def test_download_exige_autenticacao(client, solicitacao, arquivo):
    resposta = client.get(reverse("solicitacoes:baixar_arquivo", args=[solicitacao.pk, arquivo.pk]))

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_dono_baixa_o_proprio_arquivo(client, usuario_clube, solicitacao, arquivo):
    client.force_login(usuario_clube)

    resposta = client.get(reverse("solicitacoes:baixar_arquivo", args=[solicitacao.pk, arquivo.pk]))

    assert resposta.status_code == 200
    assert b"".join(resposta.streaming_content) == PDF


def test_outro_usuario_do_clube_nao_baixa(client, solicitacao, arquivo):
    """Trocar o ID na URL não dá acesso a documento alheio."""
    outro = Usuario.objects.create_user(username="clube.intruso", password="senha-de-teste")
    outro.groups.add(Group.objects.get(name=Papel.CLUBE))
    client.force_login(outro)

    resposta = client.get(reverse("solicitacoes:baixar_arquivo", args=[solicitacao.pk, arquivo.pk]))

    assert resposta.status_code == 404


def test_download_fica_registrado_na_auditoria(client, usuario_clube, solicitacao, arquivo):
    client.force_login(usuario_clube)

    client.get(reverse("solicitacoes:baixar_arquivo", args=[solicitacao.pk, arquivo.pk]))

    evento = EventoAuditoria.objects.filter(acao=Acao.DOWNLOAD).first()
    assert evento is not None
    assert evento.usuario == usuario_clube


def test_pasta_de_uploads_nao_e_servida_como_estatico(client, usuario_clube, arquivo):
    """Sem rota pública para os documentos, nem em desenvolvimento."""
    client.force_login(usuario_clube)

    resposta = client.get(f"/uploads/{arquivo.arquivo.name}")

    assert resposta.status_code == 404
