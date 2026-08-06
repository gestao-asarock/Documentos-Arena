"""
Sugestões de contraparte na busca das listas (AGENTS.md §4.2, D35).

O autocomplete é uma consulta a mais sobre a base de contrapartes, e por isso
precisa das mesmas amarras das listas: sugerir só o que o usuário já pode ver, e
não aceitar destino vindo da URL.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from contas.models import Papel, Usuario
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

URL = reverse("solicitacoes:buscar_contrapartes")

CPF = "11144477735"
CNPJ = "00000000000191"


@pytest.fixture
def dono(db):
    usuario = Usuario.objects.create_user(username="clube.sugestao", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CLUBE))
    return usuario


@pytest.fixture
def perfil(dono):
    contraparte, _ = obter_ou_criar_contraparte(
        documento=CNPJ, dados={"nome": "Fornecedora Fictícia Ltda"}
    )
    return Solicitacao.objects.create(contraparte=contraparte, criada_por=dono)


def sugerir(client, **parametros):
    resposta = client.get(URL, parametros)
    assert resposta.status_code == 200
    return resposta


def nomes(resposta):
    return [item["contraparte"].nome for item in resposta.context["sugestoes"]]


def test_exige_autenticacao(client):
    resposta = client.get(URL, {"busca": "For"})

    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_sugere_pelo_nome_e_pelo_documento(client, dono, perfil):
    client.force_login(dono)

    assert nomes(sugerir(client, busca="Forne")) == ["Fornecedora Fictícia Ltda"]
    assert nomes(sugerir(client, busca="00000000000191")) == ["Fornecedora Fictícia Ltda"]


def test_uma_letra_nao_sugere_nada(client, dono, perfil):
    """Uma letra casa com quase tudo: a lista de sugestões viraria a lista inteira."""
    client.force_login(dono)

    resposta = sugerir(client, busca="F")

    assert nomes(resposta) == []
    assert not resposta.context["buscou"]


def test_nao_sugere_contraparte_que_o_usuario_nao_ve(client, perfil):
    """Sugerir o nome já vazaria que a contraparte existe (AGENTS.md §6)."""
    de_fora = Usuario.objects.create_user(username="clube.outro", password="senha-de-teste")
    client.force_login(de_fora)

    assert nomes(sugerir(client, busca="Forne")) == []


def test_sugestao_leva_para_a_lista_pedida(client, dono, perfil):
    client.force_login(dono)

    para_contratos = sugerir(client, busca="Forne", origem="contratos")
    para_perfis = sugerir(client, busca="Forne", origem="perfis")

    assert para_contratos.context["sugestoes"][0]["url"].startswith(reverse("operacoes:lista"))
    assert para_perfis.context["sugestoes"][0]["url"].startswith(reverse("solicitacoes:lista"))


def test_origem_desconhecida_nao_vira_link(client, dono, perfil):
    """A rota sai de um mapa fixo: sem isso, `origem` viraria link para onde quem
    chamasse quisesse, dentro de uma página nossa."""
    client.force_login(dono)

    resposta = sugerir(client, busca="Forne", origem="https://exemplo.invalido/")

    assert resposta.context["sugestoes"][0]["url"].startswith(reverse("solicitacoes:lista"))


def test_sugestao_preserva_os_filtros_em_vigor(client, dono, perfil):
    """Escolher a contraparte é um recorte a mais, não um recomeço."""
    client.force_login(dono)

    url = sugerir(client, busca="Forne", origem="perfis", situacao="rascunho", pagina="3").context[
        "sugestoes"
    ][0]["url"]

    assert "situacao=rascunho" in url
    assert f"contraparte={perfil.contraparte.pk}" in url
    # A página some: com outro recorte, a página 3 pode nem existir.
    assert "pagina=" not in url
