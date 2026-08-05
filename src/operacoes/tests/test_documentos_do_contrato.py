"""
Documentos complementares do contrato (AGENTS.md D29, D30).

Ficam no perfil da contraparte, então um contrato futuro do mesmo tipo os
reaproveita — é esse o ponto da separação entre perfil e contrato.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analise.servicos import aprovar_documento
from contas.models import Papel, Usuario
from contrapartes.models import DocumentoCadastral
from operacoes.estados import Etapa, StatusOperacao
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


@pytest.fixture
def crm(db):
    usuario = Usuario.objects.create_user(username="crm.contrato", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def criar_contrato(contraparte, usuario):
    """Usa o enquadramento **real** da carga, com suas exigências documentais.

    A fixture `regra_piloto` do conftest é sintética e não tem exigências — aqui
    interessa justamente o documento que o guia manda pedir.
    """
    from decimal import Decimal

    from operacoes.models import Operacao, TipoOperacao

    def _criar(valor: str = "2000.00") -> Operacao:
        operacao = Operacao.objects.create(
            contraparte=contraparte,
            tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
            descricao="Formatura de balé",
            valor_total=Decimal(valor),
            criada_por=usuario,
        )
        return enquadrar(operacao, usuario=usuario)

    return _criar


def _enviar(client, operacao, tipo):
    return client.post(
        reverse("operacoes:enviar_documento", args=[operacao.pk]),
        {
            "tipo": tipo.id,
            # O tipo tem subtipos: é preciso dizer qual peça está sendo enviada.
            "subtipo": tipo.subtipos.get(nome="Termo de Adesão (preenchido)").id,
            "arquivos": [SimpleUploadedFile("termo.pdf", PDF)],
        },
    )


def test_envio_do_contrato_nao_pede_data_de_emissao(client, criar_contrato, crm):
    """Documento de contrato nasce agora: a emissão não alimenta cálculo nenhum.

    Diferente do kit cadastral (D48), onde a data define a vigência do dossiê.
    """
    client.force_login(crm)
    operacao = criar_contrato("2000.00")
    tipo = operacao.documentos_exigidos()[0]

    resposta = client.get(reverse("operacoes:detalhe", args=[operacao.pk]))
    _enviar(client, operacao, tipo)
    documento = operacao.contraparte.documentos_cadastrais.get(tipo=tipo)

    assert "data_emissao" not in resposta.content.decode()
    assert documento.data_emissao is None


def test_contrato_nasce_aguardando_os_documentos_do_enquadramento(criar_contrato):
    """O piloto exige o contrato entre Fundo e Cessionário."""
    operacao = criar_contrato("2000.00")

    exigidos = {t.nome for t in operacao.documentos_exigidos()}

    assert exigidos == {"Contrato entre o Fundo e o Cessionário"}
    assert not operacao.documentacao_completa
    assert operacao.status == StatusOperacao.AGUARDANDO_DOCUMENTOS


def test_documentacao_completa_leva_o_contrato_ao_juridico(client, criar_contrato, crm):
    """Sem isto o contrato ficava parado e nunca chegava à revisão jurídica."""
    operacao = criar_contrato("2000.00")
    tipo = operacao.documentos_pendentes()[0]
    client.force_login(crm)

    _enviar(client, operacao, tipo)
    documento = DocumentoCadastral.objects.get(tipo=tipo)
    aprovar_documento(documento, usuario=crm)

    operacao.refresh_from_db()
    assert operacao.documentacao_completa
    assert operacao.status == StatusOperacao.EM_APROVACAO
    assert operacao.etapa_atual.etapa == Etapa.JURIDICO


def test_documento_do_contrato_fica_no_perfil(client, criar_contrato, crm):
    operacao = criar_contrato("2000.00")
    tipo = operacao.documentos_pendentes()[0]
    client.force_login(crm)

    _enviar(client, operacao, tipo)

    documento = DocumentoCadastral.objects.get(tipo=tipo)
    assert documento.contraparte == operacao.contraparte
    assert documento in operacao.documentos.all()


def test_documento_validado_e_reaproveitado_em_outro_contrato(client, criar_contrato, crm):
    """Segundo contrato do mesmo tipo aproveita o que já foi conferido (D29)."""
    primeiro = criar_contrato("2000.00")
    tipo = primeiro.documentos_pendentes()[0]
    client.force_login(crm)
    _enviar(client, primeiro, tipo)
    aprovar_documento(DocumentoCadastral.objects.get(tipo=tipo), usuario=crm)

    segundo = criar_contrato("3000.00")
    disponiveis = segundo.contraparte.documentos_validos_de(segundo.documentos_exigidos())

    assert tipo.id in disponiveis
    # Ainda não vinculado: quem opera escolhe reaproveitar.
    assert not segundo.documentacao_completa


def test_vincular_documento_ja_validado(client, criar_contrato, crm):
    primeiro = criar_contrato("2000.00")
    tipo = primeiro.documentos_pendentes()[0]
    client.force_login(crm)
    _enviar(client, primeiro, tipo)
    documento = DocumentoCadastral.objects.get(tipo=tipo)
    aprovar_documento(documento, usuario=crm)

    segundo = criar_contrato("3000.00")
    client.post(
        reverse("operacoes:vincular_documentos", args=[segundo.pk]),
        {f"tipo_{tipo.id}": [documento.id]},
    )
    segundo.refresh_from_db()

    assert segundo.documentacao_completa
    assert segundo.status == StatusOperacao.EM_APROVACAO
