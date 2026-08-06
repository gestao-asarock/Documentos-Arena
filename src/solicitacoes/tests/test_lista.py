"""
A lista de perfis: filtros, ordenação e paginação (CLAUDE.md).

O perfil é reaproveitável e não se encerra com o contrato: a lista só cresce.
Estes testes protegem o que quebra quando ela ficar longa.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from contas.models import Papel, Usuario
from contrapartes.models import Habilitacao, StatusHabilitacao, TipoPessoa
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

URL = reverse("solicitacoes:lista")

#: Documentos fictícios, de propósito inválidos (AGENTS.md §6).
CPF = "11144477735"
CNPJ = "00000000000191"


@pytest.fixture
def interno(db):
    usuario = Usuario.objects.create_user(username="crm.perfis", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def criar(interno):
    def _criar(documento=CPF, nome="Contratante Fictício", **extra):
        contraparte, _ = obter_ou_criar_contraparte(
            documento=documento, dados={"nome": nome, **extra.pop("dados", {})}
        )
        return Solicitacao.objects.create(
            contraparte=contraparte,
            criada_por=extra.pop("criada_por", interno),
            **extra,
        )

    return _criar


def listar(client, **parametros):
    resposta = client.get(URL, parametros)
    assert resposta.status_code == 200
    return resposta


def pks(resposta):
    return [perfil.pk for perfil in resposta.context["solicitacoes"]]


def test_busca_por_nome_e_por_documento(client, interno, criar):
    empresa = criar(CNPJ, "Fornecedora Fictícia Ltda")
    pessoa = criar(CPF, "Prestador Fictício")
    client.force_login(interno)

    assert pks(listar(client, busca="Fornecedora")) == [empresa.pk]
    assert pks(listar(client, busca="00.000.000/0001-91")) == [empresa.pk]
    assert pks(listar(client, busca=f"#{pessoa.pk}")) == [pessoa.pk]


def test_filtra_por_tipo_de_pessoa(client, interno, criar):
    empresa = criar(CNPJ, "Fornecedora Fictícia Ltda")
    pessoa = criar(CPF, "Prestador Fictício")
    client.force_login(interno)

    assert pks(listar(client, tipo_pessoa=TipoPessoa.JURIDICA)) == [empresa.pk]
    assert pks(listar(client, tipo_pessoa=TipoPessoa.FISICA)) == [pessoa.pk]


def test_filtra_pela_validacao(client, interno, criar):
    """O filtro usa a anotação, e ela precisa casar com o selo da coluna."""
    validado = criar(CNPJ, "Fornecedora Fictícia Ltda")
    validado.habilitacao = Habilitacao.objects.create(
        contraparte=validado.contraparte, status=StatusHabilitacao.HABILITADA
    )
    validado.save()

    esperando = criar(CPF, "Prestador Fictício")
    esperando.habilitacao = Habilitacao.objects.create(
        contraparte=esperando.contraparte, status=StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    )
    esperando.save()

    client.force_login(interno)

    assert pks(listar(client, validacao=StatusHabilitacao.HABILITADA)) == [validado.pk]
    assert pks(listar(client, validacao=StatusHabilitacao.AGUARDANDO_DOCUMENTOS)) == [esperando.pk]


def test_perfil_cancelado_sai_pelo_selo_cinza(client, interno, criar):
    """Cancelado é filtrável pelo mesmo valor que a coluna mostra."""
    from solicitacoes.models import VALIDACAO_NAO_SE_APLICA

    cancelado = criar()
    cancelado.cancelar("Cancelado no teste.", usuario=interno)
    cancelado.save()
    client.force_login(interno)

    assert pks(listar(client, validacao=VALIDACAO_NAO_SE_APLICA)) == [cancelado.pk]
    assert pks(listar(client, situacao=StatusSolicitacao.CANCELADA)) == [cancelado.pk]


def test_parado_ha_mais_de_n_dias(client, interno, criar):
    parado = criar(CNPJ, "Fornecedora Fictícia Ltda")
    criar(CPF, "Prestador Fictício")
    Solicitacao.objects.filter(pk=parado.pk).update(
        data_atualizacao=timezone.now() - timedelta(days=40)
    )
    client.force_login(interno)

    assert pks(listar(client, parado="30")) == [parado.pk]


def test_ordena_pelo_nome_da_contraparte(client, interno, criar):
    z = criar(CNPJ, "Zeladoria Fictícia")
    a = criar(CPF, "Alimentação Fictícia")
    client.force_login(interno)

    assert pks(listar(client, ordem="contraparte")) == [a.pk, z.pk]
    assert pks(listar(client, ordem="-contraparte")) == [z.pk, a.pk]


def test_pagina_tem_no_maximo_vinte_e_cinco(client, interno, criar):
    for numero in range(26):
        criar(f"111444777{numero:02d}", f"Perfil Fictício {numero}")
    client.force_login(interno)

    assert len(pks(listar(client))) == 25
    assert listar(client).context["total"] == 26
    assert len(pks(listar(client, pagina="2"))) == 1


def test_filtro_nao_alcanca_perfil_invisivel(client, criar):
    """O recorte parte do que o usuário já vê, nunca da tabela inteira."""
    dono = Usuario.objects.create_user(username="clube.dono.perfil", password="senha-de-teste")
    dono.groups.add(Group.objects.get(name=Papel.CLUBE))
    de_fora = Usuario.objects.create_user(username="clube.fora.perfil", password="senha-de-teste")

    perfil = criar(criada_por=dono)
    client.force_login(de_fora)

    assert pks(listar(client)) == []
    assert pks(listar(client, busca=f"#{perfil.pk}")) == []
