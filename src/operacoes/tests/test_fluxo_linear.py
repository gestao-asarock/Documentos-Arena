"""
O fluxo é linear: nada se decide antes dos documentos (AGENTS.md §4.7).

Sem esta regra era possível aprovar a revisão jurídica de um contrato que ainda
não tinha sido enviado.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analise.servicos import aprovar_documento
from contas.models import Papel, Usuario
from contrapartes.models import DocumentoCadastral
from operacoes.estados import Etapa, StatusEtapa, TransicaoInvalida
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def crm():
    return _usuario("crm.linear", Papel.CRM)


@pytest.fixture
def contrato(contraparte, crm):
    """Contrato no enquadramento real, que exige o contrato Fundo/Cessionário."""
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor_total=Decimal("2000.00"),
        criada_por=crm,
    )
    return enquadrar(operacao, usuario=crm)


def _enviar_e_aprovar(client, contrato, crm):
    tipo = contrato.documentos_pendentes()[0]
    client.force_login(crm)
    client.post(
        reverse("operacoes:enviar_documento", args=[contrato.pk]),
        {
            "tipo": tipo.id,
            # O tipo tem subtipos: é preciso dizer qual peça está sendo enviada.
            "subtipo": tipo.subtipos.get(nome="Termo de Adesão (preenchido)").id,
            "arquivos": [SimpleUploadedFile("termo.pdf", PDF)],
        },
    )
    aprovar_documento(DocumentoCadastral.objects.get(tipo=tipo), usuario=crm)
    contrato.refresh_from_db()


def test_nao_decide_etapa_com_documentacao_incompleta(contrato, crm):
    """Aprovar revisão jurídica sem o contrato enviado não faz sentido."""
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    with pytest.raises(TransicaoInvalida, match="Documentação incompleta"):
        decidir_etapa(etapa, aprovada=True, parecer="Sem restrições.", usuario=crm)

    etapa.refresh_from_db()
    assert etapa.status == StatusEtapa.PENDENTE


def test_erro_diz_qual_documento_falta(contrato, crm):
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    with pytest.raises(TransicaoInvalida, match="Contrato entre o Fundo e o Cessionário"):
        decidir_etapa(etapa, aprovada=True, parecer="Sem restrições.", usuario=crm)


def test_decide_normalmente_depois_dos_documentos(client, contrato, crm):
    _enviar_e_aprovar(client, contrato, crm)

    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)
    decidir_etapa(etapa, aprovada=True, parecer="Sem restrições.", usuario=crm)
    etapa.refresh_from_db()

    assert etapa.status == StatusEtapa.APROVADA


def test_tela_nao_oferece_decisao_sem_documentos(client, contrato, crm):
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato.pk]))

    assert resposta.context["documentacao_completa"] is False
    assert resposta.context["pode_decidir"] is False
    assert "O fluxo está parado: faltam documentos" in resposta.content.decode()


def test_tela_avisa_o_que_falta_no_topo(client, contrato, crm):
    client.force_login(crm)

    corpo = client.get(reverse("operacoes:detalhe", args=[contrato.pk])).content.decode()

    assert "para o contrato seguir" in corpo
    assert "Contrato entre o Fundo e o Cessionário" in corpo


def test_post_direto_tambem_e_barrado(client, contrato, crm):
    """Esconder o botão não é controle: a view recusa o POST."""
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)
    client.force_login(crm)

    client.post(
        reverse("operacoes:decidir", args=[contrato.pk, etapa.pk]),
        {"parecer": "Tentando pular a fila.", "acao": "aprovar"},
    )
    etapa.refresh_from_db()

    assert etapa.status == StatusEtapa.PENDENTE
