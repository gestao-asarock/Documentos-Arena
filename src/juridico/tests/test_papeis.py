"""
Cada área tem sua função e sua tela (AGENTS.md §4.2, D34).

O Jurídico revisa contratos — não tria documento, não faz due diligence, não
analisa crédito. E cada papel só vê no menu o que de fato faz.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from analise.servicos import pode_conferir
from compliance.servicos import pode_analisar as pode_compliance
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from credito.servicos import pode_analisar as pode_credito
from documentos.models import StatusDocumento
from juridico.servicos import fila_juridica, pode_revisar
from operacoes.estados import Etapa
from operacoes.models import Operacao, TipoOperacao
from operacoes.permissoes import pode_decidir
from operacoes.servicos import avancar, decidir_etapa, enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def crm():
    return _usuario("crm.papeis", Papel.CRM)


@pytest.fixture
def compliance():
    return _usuario("compliance.papeis", Papel.COMPLIANCE)


@pytest.fixture
def juridico():
    return _usuario("juridico.papeis", Papel.JURIDICO)


@pytest.fixture
def clube():
    return _usuario("clube.papeis", Papel.CLUBE)


# -- Quem faz o quê ----------------------------------------------------------


def test_triagem_e_do_crm_e_do_compliance(crm, compliance, juridico, clube):
    assert pode_conferir(crm)
    assert pode_conferir(compliance)
    assert not pode_conferir(juridico)
    assert not pode_conferir(clube)


def test_credito_e_do_crm(crm, compliance, juridico, clube):
    """Due diligence e crédito são análises distintas, de áreas distintas."""
    assert pode_credito(crm)
    assert not pode_credito(compliance)
    assert not pode_credito(juridico)
    assert not pode_credito(clube)


def test_due_diligence_e_do_compliance(crm, compliance, juridico, clube):
    assert pode_compliance(compliance)
    assert not pode_compliance(crm)
    assert not pode_compliance(juridico)
    assert not pode_compliance(clube)


def test_revisao_juridica_e_do_juridico(crm, compliance, juridico, clube):
    assert pode_revisar(juridico)
    assert not pode_revisar(crm)
    assert not pode_revisar(compliance)
    assert not pode_revisar(clube)


# -- Menu --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("papel", "visiveis", "invisiveis"),
    [
        (Papel.CRM, ["analise:fila", "credito:fila"], ["compliance:fila", "juridico:fila"]),
        (Papel.COMPLIANCE, ["analise:fila", "compliance:fila"], ["credito:fila", "juridico:fila"]),
        (Papel.JURIDICO, ["juridico:fila"], ["analise:fila", "credito:fila", "compliance:fila"]),
        (
            Papel.CLUBE,
            [],
            ["analise:fila", "credito:fila", "compliance:fila", "juridico:fila"],
        ),
    ],
)
def test_menu_mostra_so_o_que_a_area_faz(client, papel, visiveis, invisiveis):
    client.force_login(_usuario(f"menu.{papel}", papel))

    corpo = client.get(reverse("solicitacoes:lista")).content.decode()

    for rota in visiveis:
        assert reverse(rota) in corpo, f"{papel} deveria ver {rota}"
    for rota in invisiveis:
        assert reverse(rota) not in corpo, f"{papel} não deveria ver {rota}"


# -- Fila do Jurídico --------------------------------------------------------


@pytest.fixture
def contrato_pronto(contraparte, crm):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Book fotográfico",
        valor_total=Decimal("1500.00"),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    for tipo in operacao.documentos_pendentes():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=tipo, status=StatusDocumento.APROVADO
        )
        ArquivoDocumento.objects.create(
            documento=documento, arquivo=SimpleUploadedFile("termo.pdf", PDF)
        )
        operacao.documentos.add(documento)
    avancar(operacao)

    credito = operacao.etapas.get(etapa=Etapa.RISCO_CREDITO)
    if not credito.esta_decidida:
        decidir_etapa(credito, aprovada=True, parecer="Sem restrições.", usuario=crm)

    operacao.refresh_from_db()
    return operacao


def test_fila_juridica_traz_o_que_esta_pronto(contrato_pronto):
    assert contrato_pronto in fila_juridica()


def test_fila_juridica_nao_traz_contrato_sem_documento(contraparte, crm):
    """Revisar contrato que ainda não chegou não faz sentido."""
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Sem documentos",
        valor_total=Decimal("1000.00"),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    assert operacao not in fila_juridica()


def test_tela_do_juridico_separa_pronto_de_a_caminho(client, juridico, contraparte, crm):
    aguardando = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Aguardando documento",
        valor_total=Decimal("1000.00"),
        criada_por=crm,
    )
    enquadrar(aguardando, usuario=crm)
    client.force_login(juridico)

    resposta = client.get(reverse("juridico:fila"))

    assert resposta.status_code == 200
    assert aguardando in resposta.context["aguardando"]
    assert aguardando not in resposta.context["prontos"]


def test_clube_nao_acessa_a_fila_do_juridico(client, clube):
    client.force_login(clube)

    assert client.get(reverse("juridico:fila")).status_code == 403


def test_juridico_decide_apenas_a_propria_etapa(contrato_pronto, juridico, crm):
    juridica = contrato_pronto.etapas.get(etapa=Etapa.JURIDICO)
    triagem = contrato_pronto.etapas.get(etapa=Etapa.TRIAGEM)

    assert pode_decidir(juridico, juridica)
    assert not pode_decidir(juridico, triagem)
    assert not pode_decidir(crm, juridica)


def test_documento_aprovado_leva_o_contrato_ao_juridico(contrato_pronto, juridico):
    """Depois da triagem e do crédito, é a vez do Jurídico."""
    assert contrato_pronto.etapa_atual.etapa == Etapa.JURIDICO
    assert pode_decidir(juridico, contrato_pronto.etapa_atual)


def test_juridico_nao_entra_na_triagem_nem_no_credito(client, juridico):
    """As telas das outras áreas são recusadas, não só escondidas do menu."""
    client.force_login(juridico)

    assert client.get(reverse("analise:fila")).status_code == 403
    assert client.get(reverse("credito:fila")).status_code == 403
    assert client.get(reverse("compliance:fila")).status_code == 403


def test_compliance_nao_entra_no_credito(client, compliance):
    client.force_login(compliance)

    assert client.get(reverse("credito:fila")).status_code == 403
    assert client.get(reverse("compliance:fila")).status_code == 200
