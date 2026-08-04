"""
Dossiê de checagens e liberação para assinatura (AGENTS.md §4.10, D32, D33).

O Clube só baixa o contrato quando tudo o que antecede a assinatura passou.
"""

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento
from documentos.validadores import validar_documento
from operacoes.dossie import montar, pronto_para_assinatura
from operacoes.estados import Etapa, StatusEtapa, StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import avancar, decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _docx(nome="termo.docx") -> SimpleUploadedFile:
    """DOCX mínimo de verdade: zip com word/document.xml."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("[Content_Types].xml", "<Types/>")
        pacote.writestr("word/document.xml", "<w:document><w:body/></w:document>")
    return SimpleUploadedFile(nome, buffer.getvalue())


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def crm():
    return _usuario("crm.assinatura", Papel.CRM)


@pytest.fixture
def juridico():
    return _usuario("juridico.assinatura", Papel.JURIDICO)


@pytest.fixture
def contrato(contraparte, crm):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        data_evento=date(2026, 4, 10),
        criada_por=crm,
    )
    return enquadrar(operacao, usuario=crm)


def _completar_documentacao(contrato, crm, *, docx=False):
    for tipo in contrato.documentos_pendentes():
        documento = DocumentoCadastral.objects.create(
            contraparte=contrato.contraparte, tipo=tipo, status=StatusDocumento.APROVADO
        )
        ArquivoDocumento.objects.create(
            documento=documento,
            arquivo=_docx() if docx else SimpleUploadedFile("termo.pdf", PDF),
            nome_original="termo.docx" if docx else "termo.pdf",
        )
        contrato.documentos.add(documento)
    avancar(contrato)
    contrato.refresh_from_db()


def _decidir_tudo(contrato, crm):
    while (etapa := contrato.etapa_atual) is not None and etapa.etapa != Etapa.ASSINATURAS:
        decidir_etapa(etapa, aprovada=True, parecer="Confere.", usuario=crm)
        contrato.refresh_from_db()


# -- DOCX aceito no contrato (D32) -------------------------------------------


def test_contrato_aceita_docx():
    assert validar_documento(_docx(), aceitar_docx=True) == "docx"


def test_kit_cadastral_nao_aceita_docx():
    """Ninguém tem RG em Word."""
    with pytest.raises(ValidationError):
        validar_documento(_docx())


def test_zip_qualquer_nao_passa_por_docx():
    """Todo zip começa com PK: só é DOCX se tiver o documento do Word."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        pacote.writestr("qualquer.txt", "conteudo")
    falso = SimpleUploadedFile("disfarcado.docx", buffer.getvalue())

    with pytest.raises(ValidationError):
        validar_documento(falso, aceitar_docx=True)


def test_envio_de_docx_pela_tela(client, contrato, crm):
    tipo = contrato.documentos_pendentes()[0]
    client.force_login(crm)

    client.post(
        reverse("operacoes:enviar_documento", args=[contrato.pk]),
        {
            "tipo": tipo.id,
            "subtipo": tipo.subtipos.get(nome="Termo de Adesão (preenchido)").id,
            "arquivos": [_docx()],
        },
    )

    arquivo = ArquivoDocumento.objects.get()
    assert arquivo.eh_docx
    assert arquivo.precisa_converter


# -- Dossiê ------------------------------------------------------------------


def test_dossie_reune_perfil_e_contrato(contrato):
    titulos = [c.titulo for c in montar(contrato)]

    assert "Documentos base do perfil" in titulos
    assert "Due diligence (Compliance)" in titulos
    assert "Documentos do contrato" in titulos
    # O crédito entra como etapa do contrato, não como item separado.
    assert any("crédito" in titulo.lower() for titulo in titulos)


def test_nao_libera_assinatura_com_etapa_pendente(contrato):
    assert not pronto_para_assinatura(contrato)


def test_libera_assinatura_quando_tudo_passou(contrato, crm):
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)

    assert pronto_para_assinatura(contrato)
    # A assinatura em si continua pendente: é ela que o Clube cumpre.
    assert contrato.etapa_atual.etapa == Etapa.ASSINATURAS


def test_tela_de_assinatura_bloqueia_download(client, contrato, crm):
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:assinatura", args=[contrato.pk]))

    assert resposta.context["liberado"] is False
    assert "ainda não passou por todas as checagens" in resposta.content.decode()


def test_download_recusado_antes_das_checagens(client, contrato, crm):
    _completar_documentacao(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)

    resposta = client.get(
        reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk])
    )

    assert resposta.status_code == 302  # volta para a tela, sem entregar nada


def test_download_liberado_apos_as_checagens(client, contrato, crm):
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)

    resposta = client.get(
        reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk])
    )

    assert resposta.status_code == 200


def test_download_cumpre_a_etapa_de_assinatura(client, contrato, crm):
    """Etapa 5 não se aprova por parecer: baixar o contrato é que a cumpre."""
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)

    client.get(reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk]))

    etapa = contrato.etapas.get(etapa=Etapa.ASSINATURAS)
    assert etapa.status == StatusEtapa.APROVADA
    assert etapa.decidida_por == crm
    assert etapa.data_decisao is not None

    # No piloto a assinatura é a última etapa: cumprida, o contrato se encerra.
    contrato.refresh_from_db()
    assert contrato.status == StatusOperacao.CONCLUIDA


def test_rebaixar_nao_reescreve_a_data_do_primeiro_download(client, contrato, crm):
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)
    url = reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk])

    client.get(url)
    primeira = contrato.etapas.get(etapa=Etapa.ASSINATURAS).data_decisao
    client.get(url)

    assert contrato.etapas.get(etapa=Etapa.ASSINATURAS).data_decisao == primeira


def test_download_recusado_nao_cumpre_a_etapa(client, contrato, crm):
    _completar_documentacao(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)

    client.get(reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk]))

    assert contrato.etapas.get(etapa=Etapa.ASSINATURAS).status == StatusEtapa.PENDENTE


def test_tela_do_contrato_nao_oferece_parecer_na_assinatura(client, contrato, crm):
    """Na etapa 5 a tela manda baixar o contrato, não aprovar/reprovar."""
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato.pk]))

    assert resposta.context["na_assinatura"] is True
    assert resposta.context["pode_decidir"] is False


def test_clube_ve_o_botao_de_download_na_etapa_de_assinatura(client, contrato, crm):
    _completar_documentacao(contrato, crm)
    _decidir_tudo(contrato, crm)
    clube = _usuario("clube.assinatura", Papel.CLUBE)
    contrato.criada_por = clube
    contrato.save()
    client.force_login(clube)

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato.pk]))

    assert resposta.context["pode_baixar_contrato"] is True
    assert "Baixar contrato para assinatura" in resposta.content.decode()


def test_docx_sem_libreoffice_avisa_em_vez_de_entregar_word(client, contrato, crm):
    """Nunca entregue um .docx dizendo que é PDF: melhor recusar com aviso."""
    from integracoes import conversao

    _completar_documentacao(contrato, crm, docx=True)
    _decidir_tudo(contrato, crm)
    arquivo = ArquivoDocumento.objects.first()
    client.force_login(crm)

    if conversao.executavel_disponivel():
        pytest.skip("LibreOffice instalado: a conversão acontece de verdade.")

    resposta = client.get(
        reverse("operacoes:baixar_para_assinatura", args=[contrato.pk, arquivo.pk]),
        follow=True,
    )

    assert "LibreOffice não está instalado" in resposta.content.decode()
    arquivo.refresh_from_db()
    assert not arquivo.pdf_convertido
