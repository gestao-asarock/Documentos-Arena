"""
Cores de situação (AGENTS.md §8).

O mapa é único para todo o sistema: foi a falta dele que fez "Perfil validado" e
"Cancelado" aparecerem com a mesma cor de "em andamento".
"""

import pytest

from contrapartes.models import StatusHabilitacao
from documentos.models import StatusDocumento
from operacoes.estados import StatusEtapa, StatusOperacao
from operacoes.templatetags.situacao import FAMILIAS, familia, simbolo
from solicitacoes.models import StatusSolicitacao


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        # Terminou bem
        (StatusOperacao.CONCLUIDA, "sucesso"),
        (StatusOperacao.ASSINADA, "sucesso"),
        (StatusHabilitacao.HABILITADA, "sucesso"),
        (StatusSolicitacao.PRONTA_PARA_CONTRATO, "sucesso"),
        (StatusDocumento.APROVADO, "sucesso"),
        (StatusEtapa.CUMPRIDA_NA_HABILITACAO, "sucesso"),
        # Terminou mal
        (StatusOperacao.CANCELADA, "erro"),
        (StatusOperacao.REPROVADA, "erro"),
        (StatusHabilitacao.RECUSADA, "erro"),
        (StatusSolicitacao.CANCELADA, "erro"),
        (StatusDocumento.REJEITADO, "erro"),
        (StatusDocumento.FALHA_ANALISE, "erro"),
        # Travado
        (StatusHabilitacao.COM_PENDENCIA, "atencao"),
        # Em curso
        (StatusOperacao.EM_CREDITO, "andamento"),
        (StatusHabilitacao.EM_COMPLIANCE, "andamento"),
        (StatusSolicitacao.EM_HABILITACAO, "andamento"),
        (StatusDocumento.ENVIADO, "andamento"),
        (StatusEtapa.PENDENTE, "andamento"),
        # Não se aplica
        (StatusOperacao.DISPENSADA, "neutro"),
        (StatusEtapa.REGISTRADA_EXTERNAMENTE, "neutro"),
    ],
)
def test_familia_de_cada_situacao(status, esperado):
    assert familia(status) == esperado


def test_status_desconhecido_nao_some_da_tela():
    assert familia("status_que_nao_existe") == "andamento"
    assert simbolo("status_que_nao_existe") == "●"


def test_todo_status_do_sistema_esta_mapeado():
    """Status novo sem cor definida cai no genérico e passa despercebido."""
    todos = set()
    for classe in (
        StatusOperacao,
        StatusHabilitacao,
        StatusSolicitacao,
        StatusDocumento,
        StatusEtapa,
    ):
        todos.update(classe.values)

    faltando = todos - set(FAMILIAS)

    assert not faltando, f"Sem cor definida: {sorted(faltando)}"


def test_cada_familia_tem_simbolo_proprio():
    """Cor sozinha não informa: o símbolo distingue sem depender de enxergá-la."""
    simbolos = {simbolo(status) for status in FAMILIAS}

    assert len(simbolos) == len(set(FAMILIAS.values()))
