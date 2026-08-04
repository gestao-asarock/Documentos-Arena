"""
Controle de acesso por papel (AGENTS.md §4.2 e §6).

O usuário do Clube é externo: assuma que ele vai trocar o ID na URL.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from contas.models import Papel, Usuario
from operacoes.models import Operacao

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario_clube(db):
    usuario = Usuario.objects.create_user(username="clube.teste", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def usuario_compliance(db):
    usuario = Usuario.objects.create_user(username="compliance.teste", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.COMPLIANCE))
    return usuario


@pytest.fixture
def operacao_de_outro(contraparte, aluguel, usuario):
    return Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=aluguel,
        valor_total=Decimal("1000.00"),
        descricao="Operação criada por outro usuário",
        criada_por=usuario,
    )


def test_lista_exige_autenticacao(client):
    resposta = client.get(reverse("operacoes:lista"))

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_clube_ve_contrato_aberto_pela_asarock(client, usuario_clube, contraparte, aluguel):
    """A esteira é do time (AGENTS.md D35).

    O contrato que a ASAROCK abriu em nome do Clube — ou que o administrador
    cadastrou para corrigir alguma coisa — precisa aparecer para ele. Antes
    sumia da tela, e o Clube não tinha como saber que existia.
    """
    admin = Usuario.objects.create_superuser(username="admin.teste", password="senha-de-teste")
    da_asarock = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=aluguel,
        valor_total=Decimal("1000.00"),
        descricao="Contrato aberto pelo administrador",
        criada_por=admin,
    )
    client.force_login(usuario_clube)

    lista = client.get(reverse("operacoes:lista"))

    assert list(lista.context["operacoes"]) == [da_asarock]
    assert client.get(reverse("operacoes:detalhe", args=[da_asarock.pk])).status_code == 200


def test_clube_nao_ve_registro_de_quem_nao_e_da_casa(client, usuario_clube, operacao_de_outro):
    """O filtro falha fechado: sem papel reconhecido, o registro não aparece."""
    client.force_login(usuario_clube)

    resposta = client.get(reverse("operacoes:lista"))

    assert list(resposta.context["operacoes"]) == []


def test_clube_recebe_404_ao_trocar_o_id_na_url(client, usuario_clube, operacao_de_outro):
    """Acesso direto ao objeto, não só o link na tela."""
    client.force_login(usuario_clube)

    resposta = client.get(reverse("operacoes:detalhe", args=[operacao_de_outro.pk]))

    assert resposta.status_code == 404


def test_usuario_interno_ve_todas_as_operacoes(client, usuario_compliance, operacao_de_outro):
    client.force_login(usuario_compliance)

    resposta = client.get(reverse("operacoes:detalhe", args=[operacao_de_outro.pk]))

    assert resposta.status_code == 200


def test_cabecalho_marca_a_aba_atual(client, usuario_clube):
    """A aba da seção aberta se identifica sozinha, pelo app da URL resolvida."""
    client.force_login(usuario_clube)

    pagina = client.get(reverse("operacoes:lista")).content.decode()

    assert f'href="{reverse("operacoes:lista")}" aria-current="page"' in pagina
    # E só ela: a aba de perfis, na mesma barra, não fica marcada.
    assert f'href="{reverse("solicitacoes:lista")}" aria-current="page"' not in pagina


def test_clube_ve_a_propria_operacao(client, usuario_clube, contraparte, aluguel):
    propria = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=aluguel,
        valor_total=Decimal("500.00"),
        descricao="Operação do próprio usuário do Clube",
        criada_por=usuario_clube,
    )
    client.force_login(usuario_clube)

    resposta = client.get(reverse("operacoes:detalhe", args=[propria.pk]))

    assert resposta.status_code == 200
