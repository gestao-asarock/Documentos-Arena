"""
Cancelamento de solicitação e de contrato (AGENTS.md §6).

Cancelar não é apagar: o registro fica, com motivo e autor.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import Habilitacao, StatusHabilitacao
from operacoes.estados import StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.cancelamento", Papel.CLUBE)


@pytest.fixture
def crm():
    return _usuario("crm.cancelamento", Papel.CRM)


@pytest.fixture
def solicitacao(clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    Habilitacao.objects.create(contraparte=contraparte, status=StatusHabilitacao.HABILITADA)
    return Solicitacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor=Decimal("2000.00"),
        criada_por=clube,
        status=StatusSolicitacao.PRONTA_PARA_CONTRATO,
    )


@pytest.fixture
def operacao(solicitacao, crm):
    registro = Operacao.objects.create(
        solicitacao=solicitacao,
        contraparte=solicitacao.contraparte,
        tipo_operacao=solicitacao.tipo_operacao,
        valor_total=solicitacao.valor,
        descricao="Contrato de cessão de espaço",
        criada_por=crm,
    )
    return enquadrar(registro, usuario=crm)


# -- Solicitação -------------------------------------------------------------


def test_cancelar_solicitacao_guarda_motivo_e_autor(client, clube, solicitacao):
    client.force_login(clube)

    client.post(
        reverse("solicitacoes:cancelar", args=[solicitacao.pk]),
        {"motivo": "Evento desmarcado pelo contratante."},
    )
    solicitacao.refresh_from_db()

    assert solicitacao.esta_cancelada
    assert solicitacao.motivo_cancelamento == "Evento desmarcado pelo contratante."
    assert solicitacao.cancelada_por == clube
    assert solicitacao.data_cancelamento is not None


def test_cancelamento_exige_motivo(solicitacao, clube):
    with pytest.raises(ValidationError):
        solicitacao.cancelar("   ", usuario=clube)


def test_nao_cancela_duas_vezes(solicitacao, clube):
    solicitacao.cancelar("Desistência.", usuario=clube)
    solicitacao.save()

    with pytest.raises(ValidationError):
        solicitacao.cancelar("De novo.", usuario=clube)


def test_solicitacao_com_contrato_aberto_nao_cancela(solicitacao, operacao, clube):
    """Cancele o contrato antes: senão sobraria contrato órfão."""
    assert not solicitacao.pode_ser_cancelada

    with pytest.raises(ValidationError):
        solicitacao.cancelar("Desistência.", usuario=clube)


def test_cancelar_o_contrato_libera_a_solicitacao(solicitacao, operacao, crm):
    operacao.cancelar("Contrato refeito.", usuario=crm)
    operacao.save()
    solicitacao.refresh_from_db()

    assert solicitacao.pode_ser_cancelada


def test_outro_usuario_do_clube_nao_cancela(client, solicitacao):
    intruso = _usuario("clube.intruso.cancel", Papel.CLUBE)
    client.force_login(intruso)

    resposta = client.post(
        reverse("solicitacoes:cancelar", args=[solicitacao.pk]), {"motivo": "Qualquer."}
    )
    solicitacao.refresh_from_db()

    assert resposta.status_code == 404
    assert not solicitacao.esta_cancelada


def test_interno_cancela_solicitacao_do_clube(client, crm, solicitacao):
    """A ASAROCK precisa poder encerrar pedido abandonado."""
    client.force_login(crm)

    client.post(
        reverse("solicitacoes:cancelar", args=[solicitacao.pk]), {"motivo": "Pedido abandonado."}
    )
    solicitacao.refresh_from_db()

    assert solicitacao.esta_cancelada
    assert solicitacao.cancelada_por == crm


# -- Contrato ----------------------------------------------------------------


def test_cancelar_operacao(client, crm, operacao):
    client.force_login(crm)

    client.post(
        reverse("operacoes:cancelar", args=[operacao.pk]), {"motivo": "Valor renegociado."}
    )
    operacao.refresh_from_db()

    assert operacao.status == StatusOperacao.CANCELADA
    assert operacao.motivo_cancelamento == "Valor renegociado."
    assert operacao.cancelada_por == crm


def test_operacao_assinada_nao_e_cancelada(operacao, crm):
    """Desfazer contrato assinado é distrato, não cancelamento."""
    operacao.status = StatusOperacao.ASSINADA
    operacao.save()

    assert not operacao.pode_ser_cancelada


def test_get_nao_cancela(client, crm, operacao):
    client.force_login(crm)

    client.get(reverse("operacoes:cancelar", args=[operacao.pk]))
    operacao.refresh_from_db()

    assert operacao.status != StatusOperacao.CANCELADA


def test_solicitacao_cancelada_mostra_o_motivo(client, clube, solicitacao):
    solicitacao.cancelar("Evento desmarcado.", usuario=clube)
    solicitacao.save()
    client.force_login(clube)

    corpo = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk])).content.decode()

    assert "Evento desmarcado." in corpo
    # Sem botão de cancelar de novo.
    assert reverse("solicitacoes:cancelar", args=[solicitacao.pk]) not in corpo
