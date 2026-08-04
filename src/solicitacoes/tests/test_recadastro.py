"""
Segundo cadastro da mesma contraparte (AGENTS.md §4.6, D19, D29).

O documento cadastral é da **contraparte**, não do cadastro que o enviou. Logo um
perfil novo da mesma pessoa pode nascer com o kit inteiro já aprovado — e aí não
existe aprovação nenhuma para acontecer. Enquanto o estado da habilitação só era
recalculado ao aprovar documento, esse perfil ficava preso em "aguardando
documentos": nada para o Clube enviar, nada na triagem, fluxo parado.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from analise.servicos import aprovar_documento
from compliance.servicos import fila_de_compliance
from contas.models import Papel, Usuario
from contrapartes.models import (
    ArquivoDocumento,
    DocumentoCadastral,
    Habilitacao,
    StatusHabilitacao,
)
from contrapartes.servicos import avancar_habilitacao
from documentos.models import StatusDocumento
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.recadastro", Papel.CLUBE)


@pytest.fixture
def crm():
    return _usuario("crm.recadastro", Papel.CRM)


@pytest.fixture
def contraparte():
    registro, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    return registro


def _kit_aprovado(contraparte, usuario):
    """Deixa o kit cadastral inteiro aprovado e vigente, como num perfil já validado."""
    for exigencia in contraparte.exigencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte,
            tipo=exigencia.tipo_documento,
            enviado_por=usuario,
            status=StatusDocumento.APROVADO,
        )
        ArquivoDocumento.objects.create(
            documento=documento,
            arquivo=SimpleUploadedFile("documento.pdf", PDF),
            nome_original="documento.pdf",
        )
    assert contraparte.kit_completo()


def _novo_perfil(contraparte, usuario):
    perfil = Solicitacao.objects.create(contraparte=contraparte, criada_por=usuario)
    abrir_habilitacao(perfil, usuario=usuario)
    perfil.refresh_from_db()
    return perfil


def test_perfil_novo_com_kit_aprovado_segue_para_compliance(contraparte, clube):
    """O caso do recadastro: sem isto o perfil nascia travado na etapa 1."""
    _kit_aprovado(contraparte, clube)
    # Habilitação anterior vencida: não é reaproveitada, mas os documentos valem.
    Habilitacao.objects.create(
        contraparte=contraparte,
        status=StatusHabilitacao.HABILITADA,
        data_validade=timezone.localdate() - timedelta(days=1),
    )

    perfil = _novo_perfil(contraparte, clube)

    assert perfil.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE
    assert perfil.habilitacao in fila_de_compliance()


def test_perfil_travado_se_corrige_ao_abrir_a_tela(client, contraparte, clube):
    """Registro que já ficou preso volta ao trilho sozinho, sem mexer no banco."""
    perfil = _novo_perfil(contraparte, clube)
    _kit_aprovado(contraparte, clube)
    # Estado antigo, gravado direto: é como o registro parado está hoje no banco.
    Habilitacao.objects.filter(pk=perfil.habilitacao_id).update(
        status=StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    )
    client.force_login(clube)

    client.get(reverse("solicitacoes:detalhe", args=[perfil.pk]))

    perfil.refresh_from_db()
    assert perfil.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE


def test_habilitacao_vigente_e_reaproveitada(contraparte, clube):
    """Perfil validado e no prazo não refaz nada: o segundo cadastro já nasce pronto."""
    _kit_aprovado(contraparte, clube)
    vigente = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.HABILITADA
    )

    perfil = _novo_perfil(contraparte, clube)

    assert perfil.habilitacao == vigente
    assert perfil.status == StatusSolicitacao.PRONTA_PARA_CONTRATO


def test_reavaliacao_nao_puxa_o_perfil_de_volta_do_credito(contraparte, clube):
    """Depois do compliance quem manda é o parecer, não o dossiê."""
    _kit_aprovado(contraparte, clube)
    habilitacao = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.EM_CREDITO
    )

    avancar_habilitacao(habilitacao)

    assert habilitacao.status == StatusHabilitacao.EM_CREDITO


def test_decisao_nao_cai_no_perfil_cancelado(contraparte, clube, crm):
    """O perfil mais recente pode ser o cancelado; a decisão é do perfil em uso."""
    em_uso = _novo_perfil(contraparte, clube)
    cancelado = _novo_perfil(contraparte, clube)
    cancelado.cancelar("Cadastro refeito.", usuario=clube)
    cancelado.save()

    enviados = []
    for exigencia in contraparte.exigencias_cadastrais():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=exigencia.tipo_documento, enviado_por=clube
        )
        ArquivoDocumento.objects.create(
            documento=documento,
            arquivo=SimpleUploadedFile("documento.pdf", PDF),
            nome_original="documento.pdf",
        )
        enviados.append(documento)

    for documento in enviados:
        aprovar_documento(documento, usuario=crm)

    em_uso.refresh_from_db()
    cancelado.refresh_from_db()
    assert em_uso.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE
    # O perfil cancelado é outro registro e não se move junto.
    assert cancelado.habilitacao.status == StatusHabilitacao.AGUARDANDO_DOCUMENTOS
