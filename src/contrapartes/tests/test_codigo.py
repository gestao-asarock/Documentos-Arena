"""
Código público da contraparte (AGENTS.md D59).

O valor do recurso está inteiro em duas propriedades: **determinismo** (o mesmo
CPF/CNPJ sempre dá o mesmo código) e **estabilidade** (ele não muda com o tempo
nem com edição de cadastro). Um código que varia não identifica nada, e como ele
vai para a tela e para conversa de telefone, variar é pior que não existir.
"""

import pytest
from django.conf import settings
from django.test import override_settings

from contrapartes.codigo import (
    ALFABETO,
    CARACTERES,
    formatar_codigo,
    gerar_codigo,
    normalizar_codigo,
)
from contrapartes.models import Contraparte
from documentos.models import TipoPessoa
from operacoes.templatetags.formatacao import codigo_contraparte

CPF = "58974790890"
CNPJ = "00000000000191"


# -- Geração ------------------------------------------------------------------


def test_mesmo_documento_da_sempre_o_mesmo_codigo():
    assert gerar_codigo(CPF) == gerar_codigo(CPF)


def test_pontuacao_nao_muda_o_codigo():
    """Quem cola de outra tela traz o ponto junto; o banco guarda sem."""
    assert gerar_codigo("589.747.908-90") == gerar_codigo(CPF)


def test_documentos_diferentes_dao_codigos_diferentes():
    assert gerar_codigo(CPF) != gerar_codigo(CNPJ)


def test_o_codigo_tem_o_tamanho_e_o_alfabeto_combinados():
    codigo = gerar_codigo(CPF)

    assert len(codigo) == CARACTERES
    assert set(codigo) <= set(ALFABETO)


def test_o_alfabeto_nao_tem_letra_que_se_confunde_com_numero():
    """Crockford: sem I, L, O e U. O código é lido em voz alta e digitado."""
    assert not set("ILOU") & set(ALFABETO)
    assert len(ALFABETO) == 32


def test_documento_vazio_nao_gera_codigo():
    with pytest.raises(ValueError):
        gerar_codigo("")


def test_a_chave_muda_o_codigo():
    """É o que separa isto de um hash puro: sem a chave não há tabela reversa."""
    com_a_nossa = gerar_codigo(CPF)

    with override_settings(HASH_KEY="outra-chave-completamente-diferente"):
        assert gerar_codigo(CPF) != com_a_nossa


def test_a_chave_de_verdade_nao_e_a_do_exemplo():
    """Guarda contra subir com o `.env.example` copiado sem preencher."""
    assert "troque" not in settings.HASH_KEY.lower()


# -- Formatação ---------------------------------------------------------------


def test_formatacao_em_grupos_de_quatro():
    assert formatar_codigo("K7M42QX9BT5R") == "K7M4-2QX9-BT5R"


def test_o_filtro_faz_o_mesmo_que_a_funcao():
    codigo = gerar_codigo(CPF)

    assert codigo_contraparte(codigo) == formatar_codigo(codigo)


def test_codigo_vazio_vira_hifen():
    """Valor vazio é `-`, como em todo o resto da interface (AGENTS.md D49)."""
    assert codigo_contraparte("") == "-"
    assert codigo_contraparte(None) == "-"


# -- Busca --------------------------------------------------------------------


def test_normalizar_aceita_como_a_tela_mostra():
    """Quem copia da tela traz o hífen; quem digita à mão pode usar minúscula."""
    assert normalizar_codigo("K7M4-2QX9-BT5R") == "K7M42QX9BT5R"
    assert normalizar_codigo("k7m4-2qx9-bt5r") == "K7M42QX9BT5R"
    assert normalizar_codigo(" K7M4 2QX9 BT5R ") == "K7M42QX9BT5R"


@pytest.mark.parametrize("termo", ["58974790890", "589.747.908-90", "00000000000191"])
def test_cpf_e_cnpj_nao_passam_por_codigo(termo):
    """O tamanho é o que separa os dois: 11 e 14 dígitos, contra 12 do código."""
    assert normalizar_codigo(termo) == ""


@pytest.mark.parametrize("termo", ["", "Fictícia", "K7M4", "K7M42QX9BT5R9"])
def test_o_que_nao_e_codigo_devolve_vazio(termo):
    assert normalizar_codigo(termo) == ""


@pytest.mark.django_db
def test_a_lista_de_perfis_acha_pelo_codigo():
    from contas.models import Usuario
    from solicitacoes.filtros import FiltroPerfis
    from solicitacoes.models import Solicitacao

    usuario = Usuario.objects.create_user(username="clube.codigo", password="senha-de-teste")
    procurada = Contraparte.objects.create(nome="Fornecedora Fictícia", documento=CNPJ)
    outra = Contraparte.objects.create(nome="Pessoa Fictícia", documento=CPF)
    perfil = Solicitacao.objects.create(contraparte=procurada, criada_por=usuario)
    # Segunda linha de propósito: com uma só, o teste passaria mesmo que a
    # cláusula do código não existisse e nada fosse filtrado.
    Solicitacao.objects.create(contraparte=outra, criada_por=usuario)

    visiveis = Solicitacao.objects.all()
    # Busca pelo código **como a tela o mostra**, com hífen.
    filtro = FiltroPerfis({"busca": formatar_codigo(procurada.codigo)}, visiveis=visiveis)

    assert list(filtro.aplicar(visiveis)) == [perfil]


# -- No modelo ----------------------------------------------------------------


@pytest.mark.django_db
def test_a_contraparte_nasce_com_codigo():
    contraparte = Contraparte.objects.create(
        nome="Fornecedora Fictícia", documento="00.000.000/0001-91"
    )

    assert contraparte.codigo == gerar_codigo(CNPJ)
    assert contraparte.codigo_formatado == formatar_codigo(contraparte.codigo)


@pytest.mark.django_db
def test_editar_o_cadastro_nao_mexe_no_codigo():
    """O código é do documento, e o documento não muda (AGENTS.md D47)."""
    contraparte = Contraparte.objects.create(nome="Antes", documento=CNPJ)
    antes = contraparte.codigo

    contraparte.nome = "Depois"
    contraparte.cidade = "Santos"
    contraparte.save()

    contraparte.refresh_from_db()
    assert contraparte.codigo == antes


@pytest.mark.django_db
def test_recadastro_da_mesma_pessoa_reencontra_o_mesmo_codigo():
    """Determinismo é o que o chefe pediu: o código é proxy da pessoa (D59)."""
    contraparte = Contraparte.objects.create(nome="Fictícia", documento=CNPJ)
    codigo = contraparte.codigo
    contraparte.delete()

    de_novo = Contraparte.objects.create(nome="Fictícia", documento=CNPJ)

    assert de_novo.codigo == codigo


@pytest.mark.django_db
def test_o_codigo_nao_e_editavel_no_formulario():
    """`editable=False`: quem o define é o documento, nunca a tela."""
    campo = Contraparte._meta.get_field("codigo")

    assert not campo.editable
    assert campo.unique


@pytest.mark.django_db
def test_pf_e_pj_convivem_sem_colidir():
    pf = Contraparte.objects.create(
        nome="Pessoa Fictícia", documento=CPF, tipo_pessoa=TipoPessoa.FISICA
    )
    pj = Contraparte.objects.create(
        nome="Empresa Fictícia", documento=CNPJ, tipo_pessoa=TipoPessoa.JURIDICA
    )

    assert pf.codigo != pj.codigo
