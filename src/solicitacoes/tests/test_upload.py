"""
Envio de documentos e validação de arquivo (AGENTS.md §5.4, D18).

Extensão é sugestão do usuário; o que vale é a assinatura dos primeiros bytes.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import DocumentoCadastral
from documentos.validadores import TAMANHO_MAXIMO_BYTES, validar_documento
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"
JPG = b"\xff\xd8\xff\xe0 conteudo ficticio"
PNG = b"\x89PNG\r\n\x1a\n conteudo ficticio"


def _arquivo(nome: str, conteudo: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(nome, conteudo)


@pytest.fixture
def usuario_clube():
    usuario = Usuario.objects.create_user(username="clube.upload", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def solicitacao(usuario_clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    return Solicitacao.objects.create(contraparte=contraparte, criada_por=usuario_clube)


# -- Telas -------------------------------------------------------------------


def test_detalhe_renderiza_com_data_de_nascimento(client, usuario_clube, solicitacao):
    """`data_nascimento` é um `date`; os filtros de data precisam aceitá-lo."""
    from datetime import date

    contraparte = solicitacao.contraparte
    contraparte.data_nascimento = date(2007, 11, 30)
    contraparte.save()
    client.force_login(usuario_clube)

    resposta = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk]))

    assert resposta.status_code == 200
    assert "30/11/2007" in resposta.content.decode()


def test_detalhe_mostra_o_kit_pendente(client, usuario_clube, solicitacao):
    client.force_login(usuario_clube)

    resposta = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk]))
    corpo = resposta.content.decode()

    assert "Comprovante de residência" in corpo
    assert "Kit cadastral" in corpo


def test_campos_condicionais_nascem_escondidos(client, usuario_clube, solicitacao):
    """Sem tipo escolhido, "qual documento" e "data de emissão" não aparecem."""
    client.force_login(usuario_clube)

    corpo = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk])).content.decode()

    # Dois blocos escondidos: subtipo e data de emissão.
    assert corpo.count('<div class="campo" hidden>') == 2


def test_configuracao_dos_campos_vai_para_a_tela(client, usuario_clube, solicitacao):
    """O JS precisa saber quais tipos pedem subtipo e quais pedem emissão."""
    client.force_login(usuario_clube)

    resposta = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk]))
    config = resposta.context["config_campos"]
    identificacao = _tipo_identificacao(solicitacao)
    comprovante = _tipo_simples(solicitacao)

    assert identificacao.id in config["subtipo"]
    assert comprovante.id not in config["subtipo"]
    assert comprovante.id in config["emissao"]
    assert identificacao.id not in config["emissao"]


def test_linha_da_lista_leva_ao_detalhe(client, usuario_clube, solicitacao):
    client.force_login(usuario_clube)

    corpo = client.get(reverse("solicitacoes:lista")).content.decode()

    assert f'data-href="{reverse("solicitacoes:detalhe", args=[solicitacao.pk])}"' in corpo


def test_lista_renderiza(client, usuario_clube, solicitacao):
    client.force_login(usuario_clube)

    resposta = client.get(reverse("solicitacoes:lista"))

    assert resposta.status_code == 200
    assert "Contratante Fictício" in resposta.content.decode()


# -- Validadores -------------------------------------------------------------


@pytest.mark.parametrize(
    ("nome", "conteudo", "formato"),
    [("doc.pdf", PDF, "pdf"), ("foto.jpg", JPG, "jpg"), ("scan.png", PNG, "png")],
)
def test_formatos_aceitos(nome, conteudo, formato):
    assert validar_documento(_arquivo(nome, conteudo)) == formato


@pytest.mark.parametrize("nome", ["contrato.docx", "planilha.xlsx", "arquivo.txt", "script.exe"])
def test_extensao_recusada(nome):
    """DOCX e XLSX ficaram fora do MVP (D18)."""
    with pytest.raises(ValidationError):
        validar_documento(_arquivo(nome, PDF))


def test_arquivo_disfarcado_e_recusado():
    """Renomear .exe para .pdf não engana: o conteúdo é lido."""
    with pytest.raises(ValidationError):
        validar_documento(_arquivo("malicioso.pdf", b"MZ\x90\x00 executavel"))


def test_arquivo_vazio_e_recusado():
    with pytest.raises(ValidationError):
        validar_documento(_arquivo("vazio.pdf", b""))


def test_tamanho_acima_do_limite_e_recusado():
    grande = _arquivo("grande.pdf", PDF + b"x" * TAMANHO_MAXIMO_BYTES)

    with pytest.raises(ValidationError, match="excede o limite"):
        validar_documento(grande)


# -- Envio pela tela ---------------------------------------------------------


def _tipo_simples(solicitacao):
    """Comprovante de residência: sem subtipos, com data de emissão."""
    return next(t for t in solicitacao.pendencias_cadastrais() if not t.subtipos.exists())


def _tipo_identificacao(solicitacao):
    return next(t for t in solicitacao.pendencias_cadastrais() if t.subtipos.exists())


def test_envio_cria_documento_e_reduz_pendencias(client, usuario_clube, solicitacao):
    client.force_login(usuario_clube)
    tipo = _tipo_simples(solicitacao)
    antes = len(solicitacao.pendencias_cadastrais())

    resposta = client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"tipo": tipo.id, "arquivos": [_arquivo("documento.pdf", PDF)], "data_emissao": ""},
    )

    assert resposta.status_code == 302
    documento = DocumentoCadastral.objects.get(contraparte=solicitacao.contraparte)
    assert documento.tipo == tipo
    assert documento.enviado_por == usuario_clube
    # Enviado não é aprovado: a pendência só sai quando o documento for aprovado.
    assert len(solicitacao.pendencias_cadastrais()) == antes


def test_envio_aceita_varios_arquivos_de_uma_vez(client, usuario_clube, solicitacao):
    """Frente e verso são o mesmo documento — não dois envios."""
    client.force_login(usuario_clube)
    tipo = _tipo_identificacao(solicitacao)
    subtipo = tipo.subtipos.get(nome="RG")

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {
            "tipo": tipo.id,
            "subtipo": subtipo.id,
            "arquivos": [_arquivo("frente.jpg", JPG), _arquivo("verso.jpg", JPG)],
        },
    )

    documento = DocumentoCadastral.objects.get(contraparte=solicitacao.contraparte)
    assert documento.arquivos.count() == 2
    assert [a.nome_original for a in documento.arquivos.all()] == ["frente.jpg", "verso.jpg"]
    assert documento.subtipo == subtipo
    assert documento.rotulo == "RG"


def test_identificacao_exige_subtipo(client, usuario_clube, solicitacao):
    """Saber se é RG ou CNH torna a extração por IA mais precisa."""
    client.force_login(usuario_clube)
    tipo = _tipo_identificacao(solicitacao)

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"tipo": tipo.id, "arquivos": [_arquivo("documento.jpg", JPG)]},
    )

    assert not DocumentoCadastral.objects.exists()


def test_identificacao_ignora_data_de_emissao(client, usuario_clube, solicitacao):
    """A emissão do RG não define validade; o campo não se aplica."""
    client.force_login(usuario_clube)
    tipo = _tipo_identificacao(solicitacao)

    assert not tipo.exige_data_emissao

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {
            "tipo": tipo.id,
            "subtipo": tipo.subtipos.get(nome="RG").id,
            "arquivos": [_arquivo("rg.jpg", JPG)],
            "data_emissao": "10/01/2020",
        },
    )

    documento = DocumentoCadastral.objects.get(contraparte=solicitacao.contraparte)
    assert documento.data_emissao is None


def test_data_em_formato_brasileiro(client, usuario_clube, solicitacao):
    """O campo aceita texto colado no formato dd/mm/aaaa."""
    client.force_login(usuario_clube)
    tipo = _tipo_simples(solicitacao)

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {
            "tipo": tipo.id,
            "arquivos": [_arquivo("comprovante.pdf", PDF)],
            "data_emissao": "24/08/2026",
        },
    )

    documento = DocumentoCadastral.objects.get(contraparte=solicitacao.contraparte)
    assert documento.data_emissao.isoformat() == "2026-08-24"


def test_um_arquivo_invalido_barra_o_envio_inteiro(client, usuario_clube, solicitacao):
    """Validação é por arquivo, não só no primeiro da seleção."""
    client.force_login(usuario_clube)
    tipo = _tipo_simples(solicitacao)

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {
            "tipo": tipo.id,
            "arquivos": [_arquivo("bom.pdf", PDF), _arquivo("ruim.txt", b"texto solto")],
        },
    )

    assert not DocumentoCadastral.objects.exists()


def test_envio_de_arquivo_invalido_nao_cria_documento(client, usuario_clube, solicitacao):
    client.force_login(usuario_clube)
    tipo = _tipo_simples(solicitacao)

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"tipo": tipo.id, "arquivos": [_arquivo("nota.txt", b"texto solto")], "data_emissao": ""},
    )

    assert not DocumentoCadastral.objects.exists()


def test_documento_enviado_sai_de_faltando_e_entra_em_analise(client, usuario_clube, solicitacao):
    """Quem enviou precisa ver que o envio chegou (AGENTS.md §4.10)."""
    client.force_login(usuario_clube)
    tipo = _tipo_simples(solicitacao)

    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"tipo": tipo.id, "arquivos": [_arquivo("comprovante.pdf", PDF)]},
    )

    kit = solicitacao.contraparte.situacao_do_kit()

    assert tipo not in kit["faltando"]
    assert [d.tipo for d in kit["em_analise"]] == [tipo]


def test_envio_exige_autenticacao(client, solicitacao):
    resposta = client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"arquivo": _arquivo("documento.pdf", PDF)},
    )

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_colega_do_clube_envia_para_perfil_do_time(client, solicitacao):
    """Enviar é a função do Clube, e o perfil é do time — inclusive o que a
    ASAROCK cadastrou em nome dele (AGENTS.md D35)."""
    colega = Usuario.objects.create_user(username="clube.outro", password="senha-de-teste")
    colega.groups.add(Group.objects.get(name=Papel.CLUBE))
    client.force_login(colega)

    tipo = solicitacao.pendencias_cadastrais()[0]
    client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"tipo": tipo.id, "arquivos": [_arquivo("documento.pdf", PDF)]},
    )

    assert DocumentoCadastral.objects.filter(enviado_por=colega).exists()


def test_usuario_sem_papel_nao_envia(client, solicitacao):
    estranho = Usuario.objects.create_user(username="sem.papel.upload", password="senha-de-teste")
    client.force_login(estranho)

    resposta = client.post(
        reverse("solicitacoes:enviar_documento", args=[solicitacao.pk]),
        {"arquivo": _arquivo("documento.pdf", PDF)},
    )

    assert resposta.status_code == 404
    assert not DocumentoCadastral.objects.exists()
