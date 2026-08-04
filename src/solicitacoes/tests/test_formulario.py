"""
Obrigatoriedade do cadastro do perfil (CLAUDE.md — fluxo antes de integração).

Regra: tudo é obrigatório, menos o complemento do endereço e — para CNPJ — os
campos que só existem para pessoa física.
"""

import pytest
from django.template.loader import render_to_string

from solicitacoes.forms import AJUDA_PF, AVISO_PJ, SolicitacaoForm

CPF = "589.747.908-90"
CNPJ = "00.000.000/0001-91"

DADOS_PF = {
    "nome": "Gabriel Fictício",
    "documento": CPF,
    "data_nascimento": "31/07/1990",
    "rg": "12.345.678-9",
    "email": "ficticio@exemplo.com.br",
    "telefone": "(11) 99999-0000",
    "cep": "01310-100",
    "logradouro": "Avenida Fictícia",
    "numero": "1000",
    "complemento": "Conjunto 12",
    "bairro": "Bairro Fictício",
    "cidade": "São Paulo",
    "uf": "sp",
}

DADOS_PJ = {**DADOS_PF, "documento": CNPJ, "data_nascimento": "", "rg": ""}


def test_perfil_pf_completo_e_valido():
    assert SolicitacaoForm(DADOS_PF).is_valid()


def test_perfil_pj_nao_exige_nascimento_nem_rg():
    form = SolicitacaoForm(DADOS_PJ)

    assert form.is_valid(), form.errors


def test_perfil_pj_descarta_nascimento_e_rg_digitados():
    """Se o CPF virou CNPJ no meio do preenchimento, o que sobrou não fica."""
    form = SolicitacaoForm({**DADOS_PF, "documento": CNPJ})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["data_nascimento"] is None
    assert form.cleaned_data["rg"] == ""


@pytest.mark.parametrize("campo", ["data_nascimento", "rg"])
def test_perfil_pf_exige_nascimento_e_rg(campo):
    form = SolicitacaoForm({**DADOS_PF, campo: ""})

    assert not form.is_valid()
    assert campo in form.errors


@pytest.mark.parametrize(
    "campo",
    [
        "nome",
        "documento",
        "email",
        "telefone",
        "cep",
        "logradouro",
        "numero",
        "bairro",
        "cidade",
        "uf",
    ],
)
def test_campo_vazio_invalida_o_cadastro(campo):
    form = SolicitacaoForm({**DADOS_PF, campo: ""})

    assert not form.is_valid()
    assert campo in form.errors


def test_complemento_e_o_unico_opcional():
    form = SolicitacaoForm({**DADOS_PF, "complemento": ""})

    assert form.is_valid(), form.errors


def test_formulario_vazio_acusa_tudo_que_falta():
    """Um envio em branco não pode passar calado por nenhum campo."""
    form = SolicitacaoForm({})

    assert not form.is_valid()
    # Sem documento não dá para saber se é PF ou PJ: nascimento e RG ficam de fora.
    assert set(form.errors) == {
        "nome",
        "documento",
        "email",
        "telefone",
        "cep",
        "logradouro",
        "numero",
        "bairro",
        "cidade",
        "uf",
    }


def test_uf_sobe_para_maiuscula():
    form = SolicitacaoForm(DADOS_PF)

    assert form.is_valid()
    assert form.cleaned_data["uf"] == "SP"


def test_documento_fora_de_cpf_ou_cnpj_e_recusado():
    form = SolicitacaoForm({**DADOS_PF, "documento": "123"})

    assert not form.is_valid()
    assert "documento" in form.errors


def test_endereco_comeca_escondido_e_reaparece_com_erro():
    """A tela esconde o endereço até a busca — mas não esconde erro do usuário."""
    assert not SolicitacaoForm().endereco_preenchido
    assert SolicitacaoForm({**DADOS_PF, "numero": ""}).endereco_preenchido


@pytest.mark.parametrize("campo", ["data_nascimento", "rg"])
def test_campo_de_pf_diz_na_tela_que_e_so_de_pf(campo):
    """A regra tem que estar no campo, não só no `clean` (AGENTS.md D43)."""
    form = SolicitacaoForm()

    assert form.fields[campo].help_text == AJUDA_PF


def test_tela_marca_nascimento_e_rg_como_obrigatorios_e_explica_a_excecao():
    html = render_to_string("solicitacoes/nova.html", {"form": SolicitacaoForm()})

    # Obrigatórios na tela, ainda que `required=False` no campo — quem exige é o
    # `clean`, e o asterisco precisa contar isso a quem preenche.
    assert html.count(AJUDA_PF) == 2
    assert html.count('<span class="obrigatorio">*</span>') == len(SolicitacaoForm().fields) - 1
    # O aviso existe escondido; o JS o revela quando o documento é um CNPJ.
    assert AVISO_PJ in html
    assert "data-aviso-pj hidden" in html


def test_blocos_do_formulario_cobrem_todos_os_campos():
    """Campo novo não pode sumir da tela por esquecimento no template."""
    form = SolicitacaoForm()
    renderizados = [campo.name for campo in form.campos_da_pessoa]
    renderizados += ["cep"] + [campo.name for campo in form.campos_do_endereco]

    assert set(renderizados) == set(form.fields)
