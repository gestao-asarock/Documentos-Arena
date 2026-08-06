"""
A etapa da vez, em SQL, tem de dizer o mesmo que a propriedade.

A regra existe em dois lugares de propósito (operacoes/consultas.py): a
propriedade serve a tela de uma operação; a anotação serve o filtro e a ordem de
uma lista paginada. Duas cópias divergem com o tempo, e o jeito de isso não
acontecer calado é comparar as duas aqui.
"""

from decimal import Decimal

import pytest

from operacoes.consultas import com_etapa_atual
from operacoes.estados import ORDEM_ETAPAS, Etapa, StatusEtapa
from operacoes.models import EtapaAprovacao, Operacao
from operacoes.servicos import decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db


@pytest.fixture
def contrato(contraparte, aluguel, regra_piloto, usuario):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=aluguel,
        valor_total=Decimal("1000.00"),
        descricao="Contrato para conferir a etapa da vez",
        criada_por=usuario,
    )
    enquadrar(operacao, usuario=usuario)
    return operacao


def _anotada(operacao):
    return com_etapa_atual(Operacao.objects.filter(pk=operacao.pk)).get()


def test_anotacao_concorda_com_a_propriedade(contrato):
    anotada = _anotada(contrato)
    esperado = contrato.etapa_atual

    assert anotada.etapa_atual_codigo == esperado.etapa
    assert anotada.etapa_atual_ordem == ORDEM_ETAPAS.index(Etapa(esperado.etapa))


def test_anotacao_acompanha_as_decisoes(contrato, usuario):
    """A cada etapa decidida, as duas leituras andam juntas."""
    for _ in range(len(ORDEM_ETAPAS)):
        etapa = contrato.etapa_atual
        if etapa is None:
            break

        anotada = _anotada(contrato)
        assert anotada.etapa_atual_codigo == etapa.etapa

        etapa.status = StatusEtapa.APROVADA
        etapa.parecer = "Conferido para o teste."
        etapa.save()
        contrato.refresh_from_db()

    assert contrato.etapa_atual is None
    assert _anotada(contrato).etapa_atual_codigo is None


def test_ordem_e_a_do_fluxo_e_nao_a_do_id(contrato):
    """A etapa da vez é a primeira do fluxo, mesmo criada depois das outras.

    O `id` cresce na ordem de inserção; a ordem do trabalho é a de
    `ORDEM_ETAPAS`. Confundir as duas faria a lista apontar a etapa errada.
    """
    triagem = contrato.etapas.get(etapa=Etapa.TRIAGEM)
    triagem.delete()
    # Recriada por último: agora é a de maior id, e ainda assim é a primeira.
    EtapaAprovacao.objects.create(operacao=contrato, etapa=Etapa.TRIAGEM)

    contrato.refresh_from_db()
    anotada = _anotada(contrato)

    assert anotada.etapa_atual_codigo == Etapa.TRIAGEM
    assert anotada.etapa_atual_codigo == contrato.etapa_atual.etapa


def test_etapa_reprovada_nao_e_mais_a_da_vez(contrato, usuario):
    """Só `pendente` e `em análise` contam como em aberto, nos dois caminhos."""
    etapa = contrato.etapa_atual
    decidir_etapa(etapa, aprovada=False, parecer="Reprovada no teste.", usuario=usuario)

    contrato.refresh_from_db()
    anotada = _anotada(contrato)
    esperado = contrato.etapa_atual

    assert anotada.etapa_atual_codigo == (esperado.etapa if esperado else None)
