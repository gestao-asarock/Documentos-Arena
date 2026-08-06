"""
Exclusão de contrato cancelado pelo administrador (AGENTS.md D58).

Apagar contrato **leva as etapas junto** (`EtapaAprovacao` é `CASCADE`), e com
elas o texto do parecer de cada decisão já tomada. Os documentos ficam: eles
pertencem à contraparte e podem estar sustentando outro contrato (D29).
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from auditoria.models import Acao, EventoAuditoria
from contas.models import Papel, Usuario
from contrapartes.models import Contraparte
from operacoes.estados import Etapa, StatusEtapa
from operacoes.models import EtapaAprovacao, Operacao

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def admin(db):
    return _usuario("admin.exclusao", Papel.ADMINISTRADOR)


@pytest.fixture
def crm(db):
    return _usuario("crm.exclusao", Papel.CRM)


@pytest.fixture
def contrato_cancelado(criar_operacao, crm):
    operacao = criar_operacao("1000.00")
    EtapaAprovacao.objects.create(
        operacao=operacao,
        etapa=Etapa.JURIDICO,
        status=StatusEtapa.APROVADA,
        parecer="Termo confere com a operação.",
        decidida_por=crm,
    )
    operacao.cancelar("Evento desmarcado.", usuario=crm)
    operacao.save()
    return operacao


def test_admin_apaga_contrato_cancelado(client, admin, contrato_cancelado):
    numero = contrato_cancelado.pk
    client.force_login(admin)

    resposta = client.post(reverse("operacoes:excluir", args=[numero]))

    assert resposta.status_code == 302
    assert not Operacao.objects.filter(pk=numero).exists()


def test_as_etapas_vao_junto(client, admin, contrato_cancelado):
    """Consequência conhecida e assumida: o parecer daquelas etapas se perde."""
    client.force_login(admin)

    client.post(reverse("operacoes:excluir", args=[contrato_cancelado.pk]))

    assert not EtapaAprovacao.objects.filter(operacao_id=contrato_cancelado.pk).exists()


def test_a_contraparte_e_os_documentos_ficam(client, admin, contrato_cancelado):
    contraparte_id = contrato_cancelado.contraparte_id
    client.force_login(admin)

    client.post(reverse("operacoes:excluir", args=[contrato_cancelado.pk]))

    assert Contraparte.objects.filter(pk=contraparte_id).exists()


def test_contrato_em_andamento_nao_se_apaga(client, admin, criar_operacao):
    operacao = criar_operacao("1000.00")
    client.force_login(admin)

    resposta = client.post(reverse("operacoes:excluir", args=[operacao.pk]))

    assert resposta.status_code == 403
    assert Operacao.objects.filter(pk=operacao.pk).exists()


def test_quem_nao_e_admin_nao_apaga(client, crm, contrato_cancelado):
    client.force_login(crm)

    resposta = client.post(reverse("operacoes:excluir", args=[contrato_cancelado.pk]))

    assert resposta.status_code == 403
    assert Operacao.objects.filter(pk=contrato_cancelado.pk).exists()


def test_a_trilha_conta_o_que_foi_embora(client, admin, contrato_cancelado):
    numero = contrato_cancelado.pk
    client.force_login(admin)

    client.post(reverse("operacoes:excluir", args=[numero]))

    evento = EventoAuditoria.objects.filter(acao=Acao.EXCLUSAO_REGISTRO).first()
    assert evento is not None
    assert f"#{numero}" in evento.descricao
    assert "etapa" in evento.descricao
    assert evento.usuario == admin


def test_get_nao_apaga(client, admin, contrato_cancelado):
    client.force_login(admin)

    client.get(reverse("operacoes:excluir", args=[contrato_cancelado.pk]))

    assert Operacao.objects.filter(pk=contrato_cancelado.pk).exists()
