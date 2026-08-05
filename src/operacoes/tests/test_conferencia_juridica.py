"""
Conferência jurídica do contrato (AGENTS.md §4.9).

No piloto a análise é objetiva: o Termo de Adesão, gerado pelo Clube, precisa
repetir o que foi registrado na operação.
"""

from datetime import date, time
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento, TipoDocumento
from operacoes.conferencia import campos_do_contrato
from operacoes.estados import Etapa
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import avancar, decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def juridico():
    return _usuario("juridico.conferencia", Papel.JURIDICO)


@pytest.fixture
def crm():
    return _usuario("crm.conferencia", Papel.CRM)


@pytest.fixture
def contrato(contraparte, crm):
    contraparte.rg = "42.410.563-9"
    contraparte.email = "ficticio@exemplo.com.br"
    contraparte.save()

    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        data_evento=date(2026, 4, 10),
        horario_evento=time(15, 0),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    # Satisfaz a documentação e leva o contrato até a revisão jurídica.
    for tipo in operacao.documentos_pendentes():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=tipo, status=StatusDocumento.APROVADO
        )
        ArquivoDocumento.objects.create(documento=documento, arquivo="cadastral/termo.pdf")
        operacao.documentos.add(documento)
    avancar(operacao)

    credito = operacao.etapas.get(etapa=Etapa.RISCO_CREDITO)
    if not credito.esta_decidida:
        decidir_etapa(credito, aprovada=True, parecer="Sem restrições.", usuario=crm)

    operacao.refresh_from_db()
    return operacao


@pytest.fixture
def contrato_com_termo_apenas_enviado(contraparte, crm):
    """O caso real: o Clube enviou o termo e ninguém o aprovou ainda."""
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Termo recém-enviado",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    for tipo in operacao.documentos_pendentes():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=tipo, status=StatusDocumento.ENVIADO, enviado_por=crm
        )
        ArquivoDocumento.objects.create(documento=documento, arquivo="cadastral/termo.pdf")
        operacao.documentos.add(documento)
    avancar(operacao)
    operacao.refresh_from_db()
    return operacao


def test_juridico_decide_com_o_termo_apenas_enviado(contrato_com_termo_apenas_enviado, juridico):
    """A regressão: o contrato travava esperando uma triagem que ninguém fazia.

    O jurídico via "aguardando conferência" e não tinha como conferir, nem ele
    nem o administrador.
    """
    contrato = contrato_com_termo_apenas_enviado
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    decidir_etapa(etapa, aprovada=True, parecer="Termo confere.", usuario=juridico)
    etapa.refresh_from_db()

    assert etapa.esta_decidida


def test_aprovar_a_revisao_aprova_o_termo(contrato_com_termo_apenas_enviado, juridico):
    """Sem isto o documento ficava "enviado" para sempre e a assinatura nunca abria."""
    contrato = contrato_com_termo_apenas_enviado
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    decidir_etapa(etapa, aprovada=True, parecer="Termo confere.", usuario=juridico)
    contrato.refresh_from_db()

    assert contrato.documentacao_completa
    assert all(d.status == StatusDocumento.APROVADO for d in contrato.documentos.all())


def test_operacao_manda_o_juridico_para_a_tela_dele(
    client, contrato_com_termo_apenas_enviado, juridico
):
    """A decisão saiu daqui (D52): esta tela é painel, não posto de trabalho."""
    client.force_login(juridico)

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato_com_termo_apenas_enviado.pk]))
    corpo = resposta.content.decode()

    assert resposta.context["pode_revisar"]
    assert not resposta.context["pode_decidir"]
    assert reverse("juridico:revisar", args=[contrato_com_termo_apenas_enviado.pk]) in corpo


def test_o_contrato_exige_o_termo_de_adesao():
    """O tipo do guia se desdobra em termo preenchido e modelo base."""
    tipo = TipoDocumento.objects.get(nome="Contrato entre o Fundo e o Cessionário")
    subtipos = {s.nome for s in tipo.subtipos.all()}

    assert "Termo de Adesão (preenchido)" in subtipos
    assert "Contrato de cessão (modelo base)" in subtipos


def test_campos_conferidos_incluem_o_que_muda_o_negocio(contrato):
    rotulos = [campo.rotulo for campo in campos_do_contrato(contrato)]

    assert "Nome do contratante" in rotulos
    assert "CPF/CNPJ" in rotulos
    assert "Valor" in rotulos
    assert "Data do evento" in rotulos
    assert "Horário" in rotulos


def test_campos_vazios_nao_entram_na_conferencia(contraparte, crm):
    """Sem data marcada não há data a conferir — nada de linha em branco."""
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Sem data definida",
        valor_total=Decimal("1000.00"),
        criada_por=crm,
    )

    rotulos = [campo.rotulo for campo in campos_do_contrato(operacao)]

    assert "Data do evento" not in rotulos
    assert "Valor" in rotulos


def test_alerta_da_multa_aparece_na_data(contrato):
    """A cláusula do contrato-mãe prevê multa de 50% por alteração de data."""
    data = next(c for c in campos_do_contrato(contrato) if c.rotulo == "Data do evento")

    assert "50%" in data.observacao


def test_tela_juridica_mostra_a_conferencia(client, contrato, juridico):
    assert contrato.etapa_atual.etapa == Etapa.JURIDICO
    client.force_login(juridico)

    resposta = client.get(reverse("juridico:revisar", args=[contrato.pk]))
    corpo = resposta.content.decode()

    assert resposta.context["conferencia"]
    assert "Termo de Adesão" in corpo
    assert "R$ 1.500,00" in corpo or "1500,00" in corpo
    assert "10/04/2026" in corpo
