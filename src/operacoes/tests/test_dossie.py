"""
Dossiê de checagens (AGENTS.md §4.10).

Cada checagem aparece **uma única vez**, com a situação real. Antes, o crédito
saía duplicado — como parecer e como etapa —, os documentos diziam "falta" com o
termo já enviado, e as etapas da Genial apareciam como concluídas.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile

from analise.servicos import aprovar_documento, rejeitar_documento
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from operacoes.dossie import ATENCAO, CONCLUIDA, EXTERNA, PENDENTE, montar
from operacoes.estados import Etapa
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def crm(db):
    usuario = Usuario.objects.create_user(username="crm.dossie", password="senha-de-teste")
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
    contrato.refresh_from_db()
    return documento


def _por_titulo(contrato):
    return {c.titulo: c for c in montar(contrato)}


def test_credito_aparece_uma_vez_so_e_no_perfil(contrato, crm):
    """Crédito é do perfil: aparece lá, e uma vez só (AGENTS.md D30)."""
    titulos = [c.titulo for c in montar(contrato)]

    assert sum("crédito" in t.lower() for t in titulos) == 1
    assert "Risco e crédito (perfil)" in titulos


def test_triagem_e_due_diligence_nao_se_repetem(contrato):
    """Vieram do perfil: não aparecem de novo como etapa do contrato."""
    titulos = [c.titulo for c in montar(contrato)]

    assert sum("riagem" in t for t in titulos) == 0
    assert sum("Due diligence" in t for t in titulos) == 1


def test_etapas_da_genial_nao_sao_concluidas(contrato):
    """Boletagem e liquidação acontecem fora — dizer 'concluída' seria mentira."""
    checagens = _por_titulo(contrato)

    for titulo, checagem in checagens.items():
        if "Boletagem" in titulo or "Liquidação" in titulo or "Envio de NFs" in titulo:
            assert checagem.situacao == EXTERNA


def test_documento_enviado_nao_diz_que_falta(contrato, crm):
    _enviar(contrato, crm)

    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.situacao == PENDENTE
    assert documentos.detalhe == "Enviado, aguardando conferência."
    assert "não enviado" not in " ".join(documentos.itens)


def test_documento_faltando_diz_que_falta(contrato):
    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.detalhe == "Falta enviar documento exigido."


def test_documento_recusado_pede_atencao(contrato, crm):
    documento = _enviar(contrato, crm)
    rejeitar_documento(documento, usuario=crm, motivo="Valor divergente.")
    contrato.refresh_from_db()

    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.situacao == ATENCAO
    assert "reenvio" in documentos.detalhe


def test_documento_aprovado_conclui_a_checagem(contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)
    contrato.refresh_from_db()

    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.situacao == CONCLUIDA


def test_juridico_decidido_aparece_concluido(contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)
    contrato.refresh_from_db()

    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)
    decidir_etapa(etapa, aprovada=True, parecer="Termo confere.", usuario=crm)

    juridica = next(c for c in montar(contrato) if "jurídica" in c.titulo.lower())
    assert juridica.situacao == CONCLUIDA
    assert juridica.responsavel == str(crm)
