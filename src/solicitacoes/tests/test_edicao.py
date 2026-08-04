"""
Edição do cadastro do perfil (AGENTS.md D47).

Alterar o que os documentos comprovam invalida a conferência já feita: o perfil
volta ao começo da esteira. Alterar contato, não. Perfil validado não se altera.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from compliance.models import ParecerCompliance, StatusParecer, Veredito
from contas.models import Papel, Usuario
from contrapartes.models import (
    ArquivoDocumento,
    DocumentoCadastral,
    Habilitacao,
    StatusHabilitacao,
)
from contrapartes.servicos import alterar_dados_cadastrais, reiniciar_validacao
from documentos.models import StatusDocumento
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

#: O cadastro como está no banco, antes da edição.
CADASTRO_ATUAL = {
    "nome": "Gabriel Fictício",
    "data_nascimento": date(1990, 7, 31),
    "rg": "12.345.678-9",
    "email": "ficticio@exemplo.com.br",
    "telefone": "(11) 99999-0000",
    "cep": "01310-100",
    "logradouro": "Avenida Fictícia",
    "numero": "1000",
    "bairro": "Bairro Fictício",
    "cidade": "São Paulo",
    "uf": "SP",
}


@pytest.fixture
def clube():
    usuario = Usuario.objects.create_user(username="clube.edicao", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def perfil(clube):
    """Perfil com o cadastro **completo** e o kit aprovado, esperando o compliance.

    Completo de propósito: com campos vazios, qualquer envio do formulário
    mudaria meia dúzia deles de uma vez, e o teste do telefone passaria a
    testar outra coisa. Aqui, só muda o que o teste mudar.
    """
    contraparte, _ = obter_ou_criar_contraparte(documento="58974790890", dados=CADASTRO_ATUAL)
    for tipo in contraparte.pendencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=tipo, status=StatusDocumento.APROVADO
        )
        ArquivoDocumento.objects.create(documento=documento, arquivo="cadastral/ficticio.pdf")

    habilitacao = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.EM_COMPLIANCE
    )
    return Solicitacao.objects.create(
        contraparte=contraparte,
        criada_por=clube,
        habilitacao=habilitacao,
        status=StatusSolicitacao.EM_HABILITACAO,
    )


def dados_do_formulario(**mudancas) -> dict:
    """O formulário inteiro, como a tela o envia: igual ao que está no banco.

    O CPF/CNPJ vai junto porque o campo é renderizado, mas está `disabled` e o
    Django descarta o que vier nele.
    """
    dados = {
        "documento": "58974790890",
        "complemento": "",
        **CADASTRO_ATUAL,
        "data_nascimento": "31/07/1990",
    }
    dados.update(mudancas)
    return dados


# -- Serviço -----------------------------------------------------------------


def test_alterar_contato_nao_reinicia_a_validacao(perfil, clube):
    alteracao = alterar_dados_cadastrais(
        perfil.contraparte, {"email": "outro@exemplo.com.br"}, usuario=clube
    )

    assert alteracao.rotulos == ["e-mail"]
    assert not alteracao.exige_revalidacao
    # Sem revalidação não há marca: a marca existe para explicar documento que voltou.
    assert perfil.contraparte.data_alteracao_cadastral is None


def test_alterar_dado_provado_marca_o_cadastro(perfil, clube):
    alteracao = alterar_dados_cadastrais(
        perfil.contraparte, {"logradouro": "Rua Nova Fictícia"}, usuario=clube
    )
    perfil.contraparte.refresh_from_db()

    assert alteracao.exige_revalidacao
    assert perfil.contraparte.data_alteracao_cadastral is not None
    assert perfil.contraparte.alterada_por == clube
    assert perfil.contraparte.campos_alterados == "logradouro"


def test_alteracao_sem_mudanca_nao_grava_nada(perfil, clube):
    alteracao = alterar_dados_cadastrais(
        perfil.contraparte, {"nome": "  Gabriel Fictício  "}, usuario=clube
    )

    assert not alteracao
    assert perfil.contraparte.data_alteracao_cadastral is None


def test_reiniciar_devolve_documentos_a_triagem_sem_apagar_arquivos(perfil, clube):
    arquivos_antes = ArquivoDocumento.objects.count()
    ParecerCompliance.objects.create(
        habilitacao=perfil.habilitacao,
        status=StatusParecer.CONCLUIDO,
        veredito=Veredito.BAIXO,
        justificativa="Nada consta.",
    )

    reiniciar_validacao(perfil.habilitacao, usuario=clube, motivo="teste")
    perfil.refresh_from_db()

    documentos = perfil.contraparte.documentos_cadastrais.all()
    assert all(d.status == StatusDocumento.ENVIADO for d in documentos)
    assert ArquivoDocumento.objects.count() == arquivos_antes
    # Parecer volta a rascunho com o texto de pé: quem revisar corrige, não redigita.
    parecer = ParecerCompliance.objects.get(habilitacao=perfil.habilitacao)
    assert parecer.status == StatusParecer.RASCUNHO
    assert parecer.justificativa == "Nada consta."
    # Estado derivado do dossiê: há documento na fila, então é análise documental.
    perfil.habilitacao.refresh_from_db()
    assert perfil.habilitacao.status == StatusHabilitacao.EM_ANALISE_DOCUMENTAL


# -- Tela --------------------------------------------------------------------


def test_editar_endereco_pede_confirmacao_antes_de_gravar(client, clube, perfil):
    """O efeito é grande demais para um aviso lido depois do fato (AGENTS.md D47)."""
    client.force_login(clube)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia"),
    )
    corpo = resposta.content.decode()

    # Não redirecionou: parou na confirmação.
    assert resposta.status_code == 200
    assert "O que isso desfaz" in corpo
    # Mostra o de e o para, e conta o estrago em número.
    assert "Avenida Fictícia" in corpo
    assert "Rua Nova Fictícia" in corpo
    assert "2 documentos" in corpo

    # E nada foi gravado.
    perfil.contraparte.refresh_from_db()
    perfil.habilitacao.refresh_from_db()
    assert perfil.contraparte.logradouro == "Avenida Fictícia"
    assert perfil.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE
    assert (
        perfil.contraparte.documentos_cadastrais.filter(status=StatusDocumento.APROVADO).count()
        == 2
    )


def test_confirmacao_sem_marcar_ciencia_nao_grava(client, clube, perfil):
    client.force_login(clube)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia", confirmado="1"),
    )
    perfil.contraparte.refresh_from_db()

    assert resposta.status_code == 200
    assert "Nada foi alterado" in resposta.content.decode()
    assert perfil.contraparte.logradouro == "Avenida Fictícia"


def test_voltar_da_confirmacao_preserva_o_que_foi_digitado(client, clube, perfil):
    client.force_login(clube)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia", confirmado="1", voltar="1"),
    )
    perfil.contraparte.refresh_from_db()

    assert "Rua Nova Fictícia" in resposta.content.decode()
    assert perfil.contraparte.logradouro == "Avenida Fictícia"


def test_editar_endereco_reinicia_a_validacao_apos_confirmar(client, clube, perfil):
    client.force_login(clube)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia", confirmado="1", ciente="1"),
    )

    assert resposta.status_code == 302
    perfil.contraparte.refresh_from_db()
    perfil.habilitacao.refresh_from_db()
    assert perfil.contraparte.logradouro == "Rua Nova Fictícia"
    assert perfil.habilitacao.status == StatusHabilitacao.EM_ANALISE_DOCUMENTAL
    assert not perfil.contraparte.documentos_cadastrais.filter(
        status=StatusDocumento.APROVADO
    ).exists()


def test_editar_so_o_telefone_preserva_as_aprovacoes(client, clube, perfil):
    client.force_login(clube)

    client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(telefone="(11) 98888-7777"),
    )

    perfil.habilitacao.refresh_from_db()
    assert perfil.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE
    assert (
        perfil.contraparte.documentos_cadastrais.filter(status=StatusDocumento.APROVADO).count()
        == 2
    )


def test_cpf_nao_muda_nem_forcando_no_post(client, clube, perfil):
    client.force_login(clube)

    client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(documento="00000000000191"),
    )
    perfil.contraparte.refresh_from_db()

    assert perfil.contraparte.documento == "58974790890"


def test_perfil_validado_nao_pode_ser_editado(client, clube, perfil):
    perfil.habilitacao.status = StatusHabilitacao.HABILITADA
    perfil.habilitacao.save()
    client.force_login(clube)

    assert not perfil.pode_ser_editada

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia", confirmado="1", ciente="1"),
        follow=True,
    )
    perfil.contraparte.refresh_from_db()

    assert perfil.contraparte.logradouro != "Rua Nova Fictícia"
    assert "não pode ter os dados alterados" in resposta.content.decode()


def test_perfil_cancelado_nao_pode_ser_editado(perfil, clube):
    perfil.cancelar("Desistência.", usuario=clube)
    perfil.save()

    assert not perfil.pode_ser_editada


def test_outro_usuario_do_clube_nao_edita(client, perfil):
    outro = Usuario.objects.create_user(username="clube.outro", password="senha-de-teste")
    outro.groups.add(Group.objects.get(name=Papel.CLUBE))
    client.force_login(outro)

    resposta = client.post(
        reverse("solicitacoes:editar", args=[perfil.pk]),
        dados_do_formulario(logradouro="Rua Nova Fictícia"),
    )

    assert resposta.status_code == 403
