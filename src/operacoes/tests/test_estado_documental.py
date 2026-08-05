"""
O estado do contrato distingue "falta enviar" de "enviado, pronto para revisão".

Dizer "Aguardando documentos" com o documento já enviado é informação errada —
e foi o que apareceu para o Jurídico na fila (AGENTS.md §4.7). Enviado destrava
a revisão jurídica: é ela quem confere o documento (§4.9).
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from analise.servicos import aprovar_documento, rejeitar_documento
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento
from juridico.servicos import aguardando_documentacao, fila_juridica
from operacoes.estados import StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def crm(db):
    usuario = Usuario.objects.create_user(username="crm.estado", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def contrato(contraparte, crm):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    return enquadrar(operacao, usuario=crm)


def _enviar(contrato, crm):
    tipo = contrato.documentos_exigidos()[0]
    documento = DocumentoCadastral.objects.create(
        contraparte=contrato.contraparte,
        tipo=tipo,
        subtipo=tipo.subtipos.get(nome="Termo de Adesão (preenchido)"),
        enviado_por=crm,
    )
    ArquivoDocumento.objects.create(
        documento=documento, arquivo=SimpleUploadedFile("termo.pdf", PDF)
    )
    contrato.documentos.add(documento)
    from operacoes.servicos import avancar

    avancar(contrato)
    contrato.refresh_from_db()
    return documento


def test_sem_envio_fica_aguardando_documentos(contrato):
    assert contrato.status == StatusOperacao.AGUARDANDO_DOCUMENTOS


def test_enviado_libera_a_etapa(contrato, crm):
    """O documento chegou: há o que revisar, então o contrato entra em aprovação.

    Quem confere o Termo é a revisão jurídica; não existe triagem antes dela.
    """
    _enviar(contrato, crm)

    assert contrato.status == StatusOperacao.EM_APROVACAO


def test_rejeitado_volta_para_aguardando_documentos(contrato, crm):
    documento = _enviar(contrato, crm)

    rejeitar_documento(documento, usuario=crm, motivo="Valor divergente.")
    contrato.refresh_from_db()

    assert contrato.status == StatusOperacao.AGUARDANDO_DOCUMENTOS


def test_aprovado_segue_o_fluxo(contrato, crm):
    documento = _enviar(contrato, crm)

    aprovar_documento(documento, usuario=crm)
    contrato.refresh_from_db()

    assert contrato.status == StatusOperacao.EM_APROVACAO


def test_fila_do_juridico_diz_o_motivo_da_espera(contrato, crm):
    """ "Falta enviar" e "documento recusado" são situações diferentes."""
    esperando = aguardando_documentacao()
    assert esperando[0].motivo_da_espera == "Aguardando o Clube enviar os documentos"

    documento = _enviar(contrato, crm)
    rejeitar_documento(documento, usuario=crm, motivo="Valor divergente.")

    esperando = aguardando_documentacao()
    assert esperando[0].motivo_da_espera == "Documento recusado, aguardando reenvio"


def test_documento_enviado_entra_na_fila_do_juridico(contrato, crm):
    """A regressão: o contrato sumia esperando uma triagem que ninguém fazia."""
    _enviar(contrato, crm)

    assert contrato in fila_juridica()
    assert aguardando_documentacao() == []


def test_documento_aprovado_nao_aparece_mais_como_esperando(contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)

    assert aguardando_documentacao() == []


def test_status_enviado_nao_conta_como_completo(contrato, crm):
    _enviar(contrato, crm)

    assert not contrato.documentacao_completa
    assert contrato.documentos.first().status == StatusDocumento.ENVIADO
