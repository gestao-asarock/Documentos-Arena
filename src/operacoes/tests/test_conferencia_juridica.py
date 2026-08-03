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


def test_o_contrato_exige_o_termo_de_adesao():
    """O tipo do guia se desdobra em termo preenchido e modelo base."""
    tipo = TipoDocumento.objects.get(nome="Contrato entre o Fundo e o Cessionário")
    subtipos = {s.nome for s in tipo.subtipos.all()}

    assert "Termo de Adesão (preenchido)" in subtipos
    assert "Contrato de cessão — modelo base" in subtipos


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

    resposta = client.get(reverse("operacoes:detalhe", args=[contrato.pk]))
    corpo = resposta.content.decode()

    assert resposta.context["conferencia"] is not None
    assert "Termo de Adesão" in corpo
    assert "R$ 1.500,00" in corpo or "1500,00" in corpo
    assert "10/04/2026" in corpo


def test_conferencia_nao_aparece_em_outras_etapas(client, contraparte, crm):
    """Só a revisão jurídica confere o termo."""
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Ainda sem documentos",
        valor_total=Decimal("1000.00"),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:detalhe", args=[operacao.pk]))

    assert resposta.context["conferencia"] is None
