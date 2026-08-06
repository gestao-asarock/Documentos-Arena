"""
Poderes de correção do administrador (AGENTS.md D58).

Apagar registro cancelado e editar cadastro que o fluxo normal já travou. Os
dois existem porque fluxo real tem engano: sem uma saída, o engano vira
intervenção no banco, que não passa por auditoria nenhuma. E porque o D57 fechou
a gambiarra que servia de saída até aqui.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import Acao, EventoAuditoria
from contas.models import Papel, Usuario
from contrapartes.models import (
    ArquivoDocumento,
    Contraparte,
    DocumentoCadastral,
    Habilitacao,
    StatusHabilitacao,
)
from documentos.models import StatusDocumento
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

DIGITOS = "00000000000191"
PDF = b"%PDF-1.4 conteudo ficticio"

DADOS = {
    "nome": "Contratante Fictício",
    "documento": "00.000.000/0001-91",
    "data_nascimento": "",
    "rg": "",
    "email": "ficticio@exemplo.com.br",
    "telefone": "(11) 99999-0000",
    "cep": "01310-100",
    "logradouro": "Avenida Fictícia",
    "numero": "1000",
    "complemento": "",
    "bairro": "Bairro Fictício",
    "cidade": "São Paulo",
    "uf": "SP",
}


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def admin():
    return _usuario("admin.poderes", Papel.ADMINISTRADOR)


@pytest.fixture
def clube():
    return _usuario("clube.poderes", Papel.CLUBE)


@pytest.fixture
def contraparte():
    registro, _ = obter_ou_criar_contraparte(
        documento=DIGITOS, dados={"nome": "Contratante Fictício", "cidade": "São Paulo"}
    )
    return registro


@pytest.fixture
def perfil(contraparte, clube):
    return Solicitacao.objects.create(
        contraparte=contraparte, criada_por=clube, status=StatusSolicitacao.EM_HABILITACAO
    )


def _validar(contraparte, usuario) -> Habilitacao:
    """Deixa a contraparte habilitada, com o kit aprovado, como um perfil pronto."""
    for exigencia in contraparte.exigencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte,
            tipo=exigencia.tipo_documento,
            enviado_por=usuario,
            status=StatusDocumento.APROVADO,
        )
        ArquivoDocumento.objects.create(
            documento=documento,
            arquivo=SimpleUploadedFile("documento.pdf", PDF),
            nome_original="documento.pdf",
        )
    return Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.HABILITADA
    )


# -- Exclusão -----------------------------------------------------------------


def test_admin_apaga_perfil_cancelado(client, admin, perfil, clube):
    perfil.cancelar("Aberto por engano.", usuario=clube)
    perfil.save()
    numero = perfil.pk
    client.force_login(admin)

    resposta = client.post(reverse("solicitacoes:excluir", args=[numero]))

    assert resposta.status_code == 302
    assert not Solicitacao.objects.filter(pk=numero).exists()


def test_excluir_perfil_nao_leva_a_contraparte_nem_o_dossie(client, admin, perfil, clube):
    """O dossiê é da contraparte, não do cadastro que o enviou (D29)."""
    habilitacao = _validar(perfil.contraparte, clube)
    perfil.cancelar("Aberto por engano.", usuario=clube)
    perfil.save()
    client.force_login(admin)

    client.post(reverse("solicitacoes:excluir", args=[perfil.pk]))

    assert Contraparte.objects.filter(pk=perfil.contraparte_id).exists()
    assert Habilitacao.objects.filter(pk=habilitacao.pk).exists()
    assert DocumentoCadastral.objects.filter(contraparte_id=perfil.contraparte_id).exists()


def test_perfil_ativo_nao_se_apaga(client, admin, perfil):
    """Cancelar primeiro obriga a passar pelas guardas do cancelamento."""
    client.force_login(admin)

    resposta = client.post(reverse("solicitacoes:excluir", args=[perfil.pk]))

    assert resposta.status_code == 403
    assert Solicitacao.objects.filter(pk=perfil.pk).exists()


def test_quem_nao_e_admin_nao_apaga(client, clube, perfil):
    perfil.cancelar("Aberto por engano.", usuario=clube)
    perfil.save()
    client.force_login(clube)

    resposta = client.post(reverse("solicitacoes:excluir", args=[perfil.pk]))

    assert resposta.status_code == 403
    assert Solicitacao.objects.filter(pk=perfil.pk).exists()


def test_exclusao_fica_na_auditoria(client, admin, perfil, clube):
    """O registro some; este evento é o que sobra dele (AGENTS.md §6)."""
    perfil.cancelar("Aberto por engano.", usuario=clube)
    perfil.save()
    numero = perfil.pk
    client.force_login(admin)

    client.post(reverse("solicitacoes:excluir", args=[numero]))

    evento = EventoAuditoria.objects.filter(acao=Acao.EXCLUSAO_REGISTRO).first()
    assert evento is not None
    assert f"#{numero}" in evento.descricao
    assert evento.usuario == admin


def test_get_nao_apaga(client, admin, perfil, clube):
    """Exclusão é POST: link em e-mail ou pré-carregamento não pode apagar nada."""
    perfil.cancelar("Aberto por engano.", usuario=clube)
    perfil.save()
    client.force_login(admin)

    client.get(reverse("solicitacoes:excluir", args=[perfil.pk]))

    assert Solicitacao.objects.filter(pk=perfil.pk).exists()


# -- Edição -------------------------------------------------------------------


def test_admin_edita_perfil_validado(client, admin, perfil, clube):
    _validar(perfil.contraparte, clube)
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(admin)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]), {**DADOS, "cidade": "Santos"}
    )

    assert resposta.status_code == 302
    perfil.contraparte.refresh_from_db()
    assert perfil.contraparte.cidade == "Santos"


def test_edicao_do_admin_nao_reinicia_a_validacao(client, admin, perfil, clube):
    """O padrão é corrigir engano de digitação, não invalidar análise feita."""
    habilitacao = _validar(perfil.contraparte, clube)
    perfil.habilitacao = habilitacao
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(admin)

    client.post(reverse("solicitacoes:editar", args=[perfil.pk]), {**DADOS, "cidade": "Santos"})

    habilitacao.refresh_from_db()
    assert habilitacao.status == StatusHabilitacao.HABILITADA
    aprovados = perfil.contraparte.documentos_cadastrais.filter(status=StatusDocumento.APROVADO)
    assert aprovados.exists()


def test_edicao_sem_revalidar_fica_na_auditoria(client, admin, perfil, clube):
    """Documento aprovado passa a atestar outro dado. Isso não pode ser silencioso."""
    _validar(perfil.contraparte, clube)
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(admin)

    client.post(reverse("solicitacoes:editar", args=[perfil.pk]), {**DADOS, "cidade": "Santos"})

    eventos = EventoAuditoria.objects.filter(acao=Acao.ALTERACAO_CADASTRAL)
    assert any("sem reiniciar a validação" in e.descricao for e in eventos)


def test_admin_pode_pedir_a_revalidacao(client, admin, perfil, clube):
    """Marcar a caixa passa pela confirmação e só então desfaz."""
    habilitacao = _validar(perfil.contraparte, clube)
    perfil.habilitacao = habilitacao
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(admin)
    dados = {**DADOS, "cidade": "Santos", "revalidar": "1"}

    # Primeiro POST cai na confirmação, sem gravar.
    confirmacao = client.post(reverse("solicitacoes:editar", args=[perfil.pk]), dados)
    assert "editar_confirmar.html" in [t.name for t in confirmacao.templates]
    perfil.contraparte.refresh_from_db()
    assert perfil.contraparte.cidade == "São Paulo"

    client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        {**dados, "confirmado": "1", "ciente": "1"},
    )

    habilitacao.refresh_from_db()
    perfil.contraparte.refresh_from_db()
    assert perfil.contraparte.cidade == "Santos"
    assert habilitacao.status != StatusHabilitacao.HABILITADA
    assert not perfil.contraparte.documentos_cadastrais.filter(
        status=StatusDocumento.APROVADO
    ).exists()


def test_a_confirmacao_carrega_a_escolha_adiante(client, admin, perfil, clube):
    """Sem o hidden, o segundo POST gravaria sem revalidar: o oposto do pedido."""
    _validar(perfil.contraparte, clube)
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(admin)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        {**DADOS, "cidade": "Santos", "revalidar": "1"},
    )

    assert 'name="revalidar"' in resposta.content.decode()


def test_clube_continua_barrado_em_perfil_validado(client, clube, perfil):
    _validar(perfil.contraparte, clube)
    perfil.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
    perfil.save()
    client.force_login(clube)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]), {**DADOS, "cidade": "Santos"}
    )

    assert resposta.status_code == 302
    perfil.contraparte.refresh_from_db()
    assert perfil.contraparte.cidade == "São Paulo"


def test_edicao_comum_ainda_reinicia_a_validacao(client, clube, perfil):
    """O poder é do administrador; para o resto o D47 continua valendo."""
    habilitacao = Habilitacao.objects.create(
        contraparte=perfil.contraparte, status=StatusHabilitacao.EM_COMPLIANCE
    )
    perfil.habilitacao = habilitacao
    perfil.save()
    DocumentoCadastral.objects.create(
        contraparte=perfil.contraparte,
        tipo=perfil.contraparte.exigencias_cadastrais()[0].tipo_documento,
        enviado_por=clube,
        status=StatusDocumento.APROVADO,
    )
    client.force_login(clube)

    client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        {**DADOS, "cidade": "Santos", "confirmado": "1", "ciente": "1"},
    )

    assert not perfil.contraparte.documentos_cadastrais.filter(
        status=StatusDocumento.APROVADO
    ).exists()
