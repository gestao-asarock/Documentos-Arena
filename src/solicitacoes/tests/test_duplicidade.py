"""
Um perfil por CPF/CNPJ (AGENTS.md D57).

Antes disso, cadastrar de novo a mesma contraparte abria uma segunda esteira
para a mesma pessoa, e o perfil novo já nascia validado: a habilitação é da
contraparte e era reaproveitada inteira (D19, D29). Pior, o cadastro novo
sobrescrevia nome e endereço de uma contraparte **já validada**, sem
confirmação e sem auditoria, contornando o D47.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import Contraparte, Habilitacao, StatusHabilitacao
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte, perfil_ativo_de

pytestmark = pytest.mark.django_db

CNPJ = "00.000.000/0001-91"
DIGITOS = "00000000000191"

DADOS_PJ = {
    "nome": "Contratante Fictício",
    "documento": CNPJ,
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


def _usuario(nome: str, papel: str = Papel.CLUBE) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.duplicidade")


@pytest.fixture
def perfil(clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento=DIGITOS, dados={"nome": "Contratante Fictício"}
    )
    return Solicitacao.objects.create(
        contraparte=contraparte, criada_por=clube, status=StatusSolicitacao.EM_HABILITACAO
    )


def _cadastrar(client, dados=None):
    return client.post(reverse("solicitacoes:nova"), dados or DADOS_PJ)


# -- Bloqueio na entrada ------------------------------------------------------


def test_cadastro_barrado_quando_a_contraparte_ja_tem_perfil(client, clube, perfil):
    client.force_login(clube)

    resposta = _cadastrar(client)

    assert resposta.status_code == 200
    assert Solicitacao.objects.count() == 1
    assert "documento" in resposta.context["form"].errors
    assert resposta.context["perfil_existente"] == perfil


def test_a_tela_oferece_o_perfil_que_ja_existe(client, clube, perfil):
    """Bloquear sem dizer para onde ir deixa quem cadastra sem saída."""
    client.force_login(clube)

    conteudo = _cadastrar(client).content.decode()

    assert f"Perfil #{perfil.pk}" in conteudo
    assert reverse("solicitacoes:detalhe", args=[perfil.pk]) in conteudo


def test_perfil_cancelado_nao_barra_um_cadastro_novo(client, clube, perfil):
    """Perfil cancelado não se edita: bloquear nele travaria o CNPJ para sempre."""
    perfil.cancelar("Cadastro refeito.", usuario=clube)
    perfil.save()
    client.force_login(clube)

    resposta = _cadastrar(client)

    assert resposta.status_code == 302
    assert Solicitacao.objects.filter(status=StatusSolicitacao.CANCELADA).count() == 1
    assert Solicitacao.objects.exclude(status=StatusSolicitacao.CANCELADA).count() == 1
    # A contraparte continua sendo uma só: o dossiê não se duplica.
    assert Contraparte.objects.count() == 1


def test_cnpj_livre_ainda_cadastra(client, clube):
    client.force_login(clube)

    resposta = _cadastrar(client)

    assert resposta.status_code == 302
    assert Solicitacao.objects.count() == 1


def test_bloqueio_vale_para_perfil_que_o_usuario_nao_enxerga(client, clube):
    """O bloqueio é da base inteira; a tela, só do que a pessoa pode ver (D35).

    Hoje `criado_dentro_da_casa` deixa todo usuário da casa ver o que a casa
    cadastrou, então esta situação só aparece com registro de autor sem papel.
    O caminho existe assim mesmo: barrar é uma decisão, mostrar é outra, e
    apontar para um perfil invisível vazaria a existência dele e daria 404.
    """
    sem_papel = Usuario.objects.create_user(username="sem.papel", password="senha-de-teste")
    contraparte, _ = obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Fictícia"})
    invisivel = Solicitacao.objects.create(
        contraparte=contraparte, criada_por=sem_papel, status=StatusSolicitacao.EM_HABILITACAO
    )
    client.force_login(clube)

    resposta = _cadastrar(client)

    assert Solicitacao.objects.count() == 1
    assert resposta.context["bloqueado_por_duplicidade"]
    assert resposta.context["perfil_existente"] is None
    conteudo = resposta.content.decode()
    assert f"Perfil #{invisivel.pk}" not in conteudo
    assert "outra equipe" in conteudo


def test_perfil_ativo_de_ignora_pontuacao(perfil):
    assert perfil_ativo_de(CNPJ) == perfil
    assert perfil_ativo_de(DIGITOS) == perfil
    assert perfil_ativo_de("") is None


# -- A porta lateral do D47 ---------------------------------------------------


def test_cadastro_novo_nao_reescreve_contraparte_validada(clube):
    """O que os documentos comprovam só muda pela edição, que confirma e revalida."""
    contraparte, _ = obter_ou_criar_contraparte(
        documento=DIGITOS,
        dados={"nome": "Contratante Fictício", "cidade": "São Paulo"},
    )
    Habilitacao.objects.create(contraparte=contraparte, status=StatusHabilitacao.HABILITADA)

    obter_ou_criar_contraparte(
        documento=DIGITOS,
        dados={"nome": "Outro Nome", "cidade": "Santos", "email": "novo@exemplo.com.br"},
    )

    contraparte.refresh_from_db()
    assert contraparte.nome == "Contratante Fictício"
    assert contraparte.cidade == "São Paulo"
    # Contato nenhum documento atesta: esse continua atualizando.
    assert contraparte.email == "novo@exemplo.com.br"


def test_campo_em_branco_ainda_e_preenchido(clube):
    """Não reescrever não é congelar: o que faltava continua entrando."""
    contraparte, _ = obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Fictícia"})

    obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Outro", "cidade": "Santos"})

    contraparte.refresh_from_db()
    assert contraparte.nome == "Fictícia"
    assert contraparte.cidade == "Santos"


# -- Limpeza da base ----------------------------------------------------------


def _duplicados(clube, quantos: int, **extra) -> list[Solicitacao]:
    contraparte, _ = obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Fictícia"})
    return [
        Solicitacao.objects.create(
            contraparte=contraparte,
            criada_por=clube,
            status=extra.get("status", StatusSolicitacao.EM_HABILITACAO),
        )
        for _ in range(quantos)
    ]


def _rodar(*argumentos) -> str:
    saida = StringIO()
    call_command("perfis_duplicados", *argumentos, stdout=saida)
    return saida.getvalue()


def test_comando_so_relata_por_padrao(clube):
    _duplicados(clube, 3)

    saida = _rodar()

    assert Solicitacao.objects.filter(status=StatusSolicitacao.CANCELADA).count() == 0
    assert "Nada foi gravado" in saida


def test_comando_cancela_e_mantem_um(clube):
    perfis = _duplicados(clube, 3)

    _rodar("--aplicar")

    ativos = Solicitacao.objects.exclude(status=StatusSolicitacao.CANCELADA)
    assert ativos.count() == 1
    assert ativos.first() == perfis[0]
    assert str(perfis[0].pk) in Solicitacao.objects.get(pk=perfis[1].pk).motivo_cancelamento


def test_comando_mantem_o_perfil_mais_avancado(clube):
    """Cancelar o validado e manter o rascunho jogaria a análise fora."""
    contraparte, _ = obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Fictícia"})
    rascunho = Solicitacao.objects.create(
        contraparte=contraparte, criada_por=clube, status=StatusSolicitacao.RASCUNHO
    )
    validado = Solicitacao.objects.create(
        contraparte=contraparte, criada_por=clube, status=StatusSolicitacao.PRONTA_PARA_CONTRATO
    )

    _rodar("--aplicar")

    rascunho.refresh_from_db()
    validado.refresh_from_db()
    assert validado.status == StatusSolicitacao.PRONTA_PARA_CONTRATO
    assert rascunho.status == StatusSolicitacao.CANCELADA


def test_comando_nao_mexe_em_quem_nao_tem_duplicata(clube, perfil):
    saida = _rodar("--aplicar")

    perfil.refresh_from_db()
    assert perfil.status == StatusSolicitacao.EM_HABILITACAO
    assert "Nenhuma contraparte com mais de um perfil ativo" in saida


def test_comando_avisa_sobre_habilitacao_que_fica_na_fila(clube):
    """Fila de compliance lê a habilitação, não o perfil: cancelar não a tira de lá."""
    contraparte, _ = obter_ou_criar_contraparte(documento=DIGITOS, dados={"nome": "Fictícia"})
    validado = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.HABILITADA
    )
    Solicitacao.objects.create(
        contraparte=contraparte,
        criada_por=clube,
        status=StatusSolicitacao.PRONTA_PARA_CONTRATO,
        habilitacao=validado,
    )
    # O duplicado abriu uma segunda habilitação, que ficou parada no compliance.
    orfa = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.EM_COMPLIANCE
    )
    descartado = Solicitacao.objects.create(
        contraparte=contraparte,
        criada_por=clube,
        status=StatusSolicitacao.EM_HABILITACAO,
        habilitacao=orfa,
    )

    saida = _rodar("--aplicar")

    descartado.refresh_from_db()
    assert descartado.status == StatusSolicitacao.CANCELADA
    assert f"habilitação #{orfa.pk}" in saida
    # Cancelar o perfil não mexe na habilitação: isso seria inventar um parecer.
    orfa.refresh_from_db()
    assert orfa.status == StatusHabilitacao.EM_COMPLIANCE


def test_a_base_limpa_volta_a_aceitar_a_regra_nova(client, clube):
    """A limpeza é o que faz o bloqueio parar de apontar para o perfil errado."""
    _duplicados(clube, 3)
    _rodar("--aplicar")
    client.force_login(clube)

    resposta = _cadastrar(client)

    assert resposta.status_code == 200
    assert resposta.context["perfil_existente"] == perfil_ativo_de(DIGITOS)
