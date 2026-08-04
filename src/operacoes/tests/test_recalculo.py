"""
Estado gravado × situação real (AGENTS.md §4.7).

O status fica no banco e só muda quando algo acontece. Mudança de regra deixa
registros parados com o estado antigo — e a tela passa a mostrar duas
informações que se contradizem, como aconteceu na fila do Jurídico.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from juridico.servicos import aguardando_documentacao
from operacoes.estados import StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def crm(db):
    usuario = Usuario.objects.create_user(username="crm.recalculo", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def contrato_desatualizado(contraparte, crm):
    """Documento enviado, mas status congelado no valor antigo.

    Reproduz o que acontece com registros criados antes de uma mudança de regra.
    """
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    tipo = operacao.documentos_exigidos()[0]
    documento = DocumentoCadastral.objects.create(
        contraparte=contraparte,
        tipo=tipo,
        subtipo=tipo.subtipos.get(nome="Termo de Adesão (preenchido)"),
        enviado_por=crm,
    )
    ArquivoDocumento.objects.create(
        documento=documento, arquivo=SimpleUploadedFile("termo.pdf", PDF)
    )
    operacao.documentos.add(documento)

    # Grava o estado antigo direto, sem passar pelo serviço.
    Operacao.objects.filter(pk=operacao.pk).update(
        status=StatusOperacao.AGUARDANDO_DOCUMENTOS
    )
    operacao.refresh_from_db()
    return operacao


def test_estado_desatualizado_e_corrigido_ao_abrir(client, contrato_desatualizado, crm):
    """Abrir o contrato reaplica as regras: nada de tela contraditória."""
    assert contrato_desatualizado.status == StatusOperacao.AGUARDANDO_DOCUMENTOS
    client.force_login(crm)

    client.get(reverse("operacoes:detalhe", args=[contrato_desatualizado.pk]))
    contrato_desatualizado.refresh_from_db()

    assert contrato_desatualizado.status == StatusOperacao.EM_ANALISE_DOCUMENTAL


def test_fila_do_juridico_nao_mostra_estado_velho(contrato_desatualizado):
    esperando = aguardando_documentacao()

    assert esperando[0].status == StatusOperacao.EM_ANALISE_DOCUMENTAL
    assert esperando[0].motivo_da_espera == "Documento enviado, em conferência"


def test_comando_recalcula_sem_decidir_nada(contrato_desatualizado):
    """O comando reaplica as regras; não aprova nem reprova coisa alguma."""
    etapas_antes = {e.etapa: e.status for e in contrato_desatualizado.etapas.all()}

    call_command("recalcular_estados")
    contrato_desatualizado.refresh_from_db()

    assert contrato_desatualizado.status == StatusOperacao.EM_ANALISE_DOCUMENTAL
    assert {e.etapa: e.status for e in contrato_desatualizado.etapas.all()} == etapas_antes


def test_simulacao_nao_grava(contrato_desatualizado):
    call_command("recalcular_estados", simular=True)
    contrato_desatualizado.refresh_from_db()

    assert contrato_desatualizado.status == StatusOperacao.AGUARDANDO_DOCUMENTOS
