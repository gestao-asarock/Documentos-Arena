"""
O selo de validação, em SQL, tem de dizer o mesmo que a propriedade.

Mesma dívida assumida da etapa da vez (solicitacoes/consultas.py): a propriedade
monta o selo da tela, a anotação alimenta filtro e ordenação da lista. Se as
duas discordarem, a coluna mostra uma coisa e o filtro devolve outra.
"""

import pytest

from contrapartes.models import Habilitacao, StatusHabilitacao
from solicitacoes.consultas import com_validacao
from solicitacoes.models import VALIDACAO_NAO_SE_APLICA, Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

from .test_solicitacao import criar_perfil, usuario  # noqa: F401

pytestmark = pytest.mark.django_db


def _anotado(perfil):
    return com_validacao(Solicitacao.objects.filter(pk=perfil.pk)).get().validacao_codigo


@pytest.mark.parametrize(
    "status",
    [
        StatusHabilitacao.AGUARDANDO_DOCUMENTOS,
        StatusHabilitacao.EM_COMPLIANCE,
        StatusHabilitacao.HABILITADA,
        StatusHabilitacao.RECUSADA,
    ],
)
def test_anotacao_repete_o_status_da_habilitacao(criar_perfil, status):  # noqa: F811
    perfil = criar_perfil("11144477735")
    perfil.habilitacao = Habilitacao.objects.create(contraparte=perfil.contraparte, status=status)
    perfil.save()

    assert _anotado(perfil) == perfil.situacao_da_validacao["status"] == status


def test_perfil_cancelado_nao_tem_validacao_em_curso(criar_perfil, usuario):  # noqa: F811
    """Cancelado vira o selo cinza nos dois caminhos, não o status da habilitação."""
    perfil = criar_perfil("11144477735")
    perfil.habilitacao = Habilitacao.objects.create(
        contraparte=perfil.contraparte, status=StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    )
    perfil.save()
    perfil.cancelar("Cancelado no teste.", usuario=usuario)
    perfil.save()

    assert perfil.situacao_da_validacao["status"] == VALIDACAO_NAO_SE_APLICA
    assert _anotado(perfil) == VALIDACAO_NAO_SE_APLICA


def test_perfil_sem_habilitacao_fica_vazio(usuario):  # noqa: F811
    contraparte, _ = obter_ou_criar_contraparte(
        documento="11144477735", dados={"nome": "Sem Habilitação"}
    )
    perfil = Solicitacao.objects.create(
        contraparte=contraparte, criada_por=usuario, status=StatusSolicitacao.RASCUNHO
    )

    assert perfil.situacao_da_validacao["status"] == ""
    assert _anotado(perfil) == ""
