"""
A lista branca da ordenação (arena/listagem.py).

O `order_by` recebe texto vindo da URL. Sem a lista branca, qualquer campo do
modelo e das tabelas ligadas a ele vira ordenável pela barra de endereço,
inclusive os que não deveriam sequer aparecer na tela.
"""

import pytest

from arena.listagem import Ordem, ordenar
from solicitacoes.models import Solicitacao

COLUNAS = {"nome": ("contraparte__nome",), "criacao": ("data_criacao",)}


@pytest.mark.django_db
def _ordenar(pedido):
    return ordenar(Solicitacao.objects.all(), pedido, colunas=COLUNAS, padrao="-criacao")


@pytest.mark.parametrize(
    "pedido",
    ["", "inexistente", "-inexistente", "contraparte__documento", "senha", "criada_por__password"],
)
@pytest.mark.django_db
def test_pedido_fora_da_lista_cai_no_padrao(pedido):
    _, ordem = _ordenar(pedido)

    assert ordem == Ordem(chave="criacao", descendente=True)


@pytest.mark.django_db
def test_pedido_conhecido_vale_nos_dois_sentidos():
    _, crescente = _ordenar("nome")
    _, decrescente = _ordenar("-nome")

    assert crescente == Ordem(chave="nome", descendente=False)
    assert decrescente == Ordem(chave="nome", descendente=True)


def test_alternar_inverte_a_coluna_que_ja_ordena():
    ordem = Ordem(chave="nome", descendente=False)

    assert ordem.alternar("nome") == "-nome"
    assert Ordem(chave="nome", descendente=True).alternar("nome") == "nome"


def test_alternar_comeca_crescente_em_outra_coluna():
    """Coluna nova começa crescente: é o que se espera de nome e de valor."""
    ordem = Ordem(chave="criacao", descendente=True)

    assert ordem.alternar("nome") == "nome"


def test_direcao_so_marca_a_coluna_em_vigor():
    ordem = Ordem(chave="nome", descendente=True)

    assert ordem.direcao_de("nome") == "desc"
    assert ordem.direcao_de("criacao") == ""


@pytest.mark.django_db
def test_desempate_pelo_id_e_sempre_o_ultimo_criterio():
    """Sem desempate fixo, duas linhas iguais trocam de lugar entre páginas.

    Quando isso acontece, um registro aparece duas vezes e outro nunca aparece:
    é o jeito mais silencioso de a paginação enganar quem lê.
    """
    consulta, _ = _ordenar("nome")
    criterios = consulta.query.order_by

    assert len(criterios) == 2
    assert criterios[-1].expression.name == "pk"
    assert criterios[-1].descending
