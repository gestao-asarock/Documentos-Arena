"""
Tela de revisão jurídica (AGENTS.md §4.9, D52).

A revisão tem posto de trabalho próprio, como a triagem do CRM: o documento
baixável, os campos a conferir e o parecer no mesmo lugar. A tela da operação
deixou de decidir por uma área.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from documentos.models import StatusDocumento
from operacoes.conferencia import campos_do_contrato
from operacoes.estados import Etapa, StatusEtapa, StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import avancar, enquadrar

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def juridico():
    return _usuario("juridico.revisao", Papel.JURIDICO)


@pytest.fixture
def crm():
    return _usuario("crm.revisao", Papel.CRM)


@pytest.fixture
def clube():
    return _usuario("clube.revisao", Papel.CLUBE)


@pytest.fixture
def contrato(contraparte, crm):
    operacao = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
        descricao="Formatura de balé",
        valor_total=Decimal("1500.00"),
        data_evento=date(2026, 4, 10),
        criada_por=crm,
    )
    enquadrar(operacao, usuario=crm)

    for tipo in operacao.documentos_pendentes():
        documento = DocumentoCadastral.objects.create(
            contraparte=contraparte, tipo=tipo, status=StatusDocumento.ENVIADO, enviado_por=crm
        )
        ArquivoDocumento.objects.create(
            documento=documento,
            arquivo=SimpleUploadedFile("termo.pdf", PDF),
            nome_original="termo.pdf",
        )
        operacao.documentos.add(documento)
    avancar(operacao)
    operacao.refresh_from_db()
    return operacao


def _tudo_conferido(contrato) -> list[str]:
    """Todas as caixas marcadas: é o que a aprovação exige (D53)."""
    return [campo.chave for campo in campos_do_contrato(contrato)]


def test_tela_traz_documento_campos_e_decisao(client, contrato, juridico):
    client.force_login(juridico)

    resposta = client.get(reverse("juridico:revisar", args=[contrato.pk]))
    corpo = resposta.content.decode()

    assert resposta.context["pode_decidir"]
    assert "termo.pdf" in corpo
    assert "R$ 1.500,00" in corpo
    assert reverse("juridico:decidir", args=[contrato.pk]) in corpo


def test_clube_nao_entra_na_revisao(client, contrato, clube):
    client.force_login(clube)

    assert client.get(reverse("juridico:revisar", args=[contrato.pk])).status_code == 403
    assert client.post(reverse("juridico:decidir", args=[contrato.pk])).status_code == 403


def test_aprovar_conclui_a_etapa_e_o_documento(client, contrato, juridico):
    client.force_login(juridico)

    client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {
            "acao": "aprovar",
            "parecer": "Termo confere com o registrado.",
            "confere": _tudo_conferido(contrato),
        },
    )
    contrato.refresh_from_db()
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    assert etapa.status == StatusEtapa.APROVADA
    assert etapa.decidida_por == juridico
    assert contrato.documentacao_completa


def test_aprovar_exige_todos_os_campos_conferidos(client, contrato, juridico):
    """Aprovar afirma que o termo confere campo a campo; não dá para pular."""
    client.force_login(juridico)
    parciais = _tudo_conferido(contrato)[:-1]

    resposta = client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {"acao": "aprovar", "parecer": "Confere.", "confere": parciais},
        follow=True,
    )
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    assert not etapa.esta_decidida
    assert "Falta marcar" in resposta.content.decode()


def test_aprovar_sem_marcar_nada_nao_passa(client, contrato, juridico):
    """O caso relatado: aprovação saía com as caixas vazias."""
    client.force_login(juridico)

    client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {"acao": "aprovar", "parecer": "Confere."},
    )
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    assert not etapa.esta_decidida


def test_reprovar_nao_exige_as_marcacoes(client, contrato, juridico):
    """Reprova-se justamente porque algum campo não confere."""
    client.force_login(juridico)

    client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {"acao": "reprovar", "parecer": "Valor do termo diverge do registrado."},
    )
    contrato.refresh_from_db()

    assert contrato.status == StatusOperacao.REPROVADA
    assert "diverge" in contrato.motivo_reprovacao


def test_parecer_e_obrigatorio(client, contrato, juridico):
    """Decisão sem parecer não vai para a auditoria (AGENTS.md §5.1)."""
    client.force_login(juridico)

    client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {"acao": "aprovar", "parecer": " ", "confere": _tudo_conferido(contrato)},
    )
    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)

    assert not etapa.esta_decidida


def test_arquivo_do_contrato_e_baixavel(client, contrato, juridico):
    client.force_login(juridico)
    arquivo = ArquivoDocumento.objects.get(documento__operacoes=contrato)

    resposta = client.get(reverse("juridico:baixar_arquivo", args=[contrato.pk, arquivo.pk]))

    assert resposta.status_code == 200
    assert b"".join(resposta.streaming_content) == PDF


def test_arquivo_de_outro_contrato_nao_vaza(client, contrato, juridico, crm, contraparte):
    """Trocar o id na URL não pode entregar documento de outro contrato."""
    alheio = DocumentoCadastral.objects.create(
        contraparte=contraparte, tipo=contrato.documentos_exigidos()[0], enviado_por=crm
    )
    arquivo = ArquivoDocumento.objects.create(
        documento=alheio, arquivo=SimpleUploadedFile("alheio.pdf", PDF)
    )
    client.force_login(juridico)

    resposta = client.get(reverse("juridico:baixar_arquivo", args=[contrato.pk, arquivo.pk]))

    assert resposta.status_code == 404


def test_contrato_ja_decidido_mostra_o_parecer_sem_reabrir(client, contrato, juridico):
    client.force_login(juridico)
    client.post(
        reverse("juridico:decidir", args=[contrato.pk]),
        {
            "acao": "aprovar",
            "parecer": "Termo confere com o registrado.",
            "confere": _tudo_conferido(contrato),
        },
    )

    resposta = client.get(reverse("juridico:revisar", args=[contrato.pk]))

    assert not resposta.context["pode_decidir"]
    assert "Termo confere com o registrado." in resposta.content.decode()
