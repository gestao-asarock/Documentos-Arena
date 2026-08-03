"""
Dossiê cadastral: dedução de PF/PJ, vigência e completude (AGENTS.md §4.5, D10, D20).

O kit exigido depende do tipo de pessoa e, para PF, também do valor.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from contrapartes.models import (
    ArquivoDocumento,
    Contraparte,
    DocumentoCadastral,
    deduzir_tipo_pessoa,
)
from documentos.models import StatusDocumento, TipoDocumento, TipoPessoa

pytestmark = pytest.mark.django_db


@pytest.fixture
def comprovante_pj():
    """Único documento do guia com prazo explícito: 90 dias."""
    return TipoDocumento.objects.get(nome="Comprovante de endereço")


@pytest.fixture
def contrato_social():
    return TipoDocumento.objects.get(nome="Contrato Social / Última Alteração Contratual")


@pytest.fixture
def contraparte_pj():
    # CNPJ fictício, inválido de propósito (AGENTS.md §6).
    return Contraparte.objects.create(nome="Fornecedora Fictícia Ltda", documento="00000000000191")


@pytest.fixture
def contraparte_pf():
    return Contraparte.objects.create(nome="Contratante Fictício", documento="00000000000")


def _enviar(contraparte, tipo, *, dias_atras=0, status=StatusDocumento.APROVADO):
    documento = DocumentoCadastral.objects.create(
        contraparte=contraparte,
        tipo=tipo,
        status=status,
        data_emissao=timezone.localdate() - timedelta(days=dias_atras),
    )
    ArquivoDocumento.objects.create(
        documento=documento, arquivo="cadastral/ficticio.pdf", nome_original="ficticio.pdf"
    )
    return documento


def _completar(contraparte, valor=None):
    for tipo in contraparte.pendencias_cadastrais(valor):
        _enviar(contraparte, tipo)


# -- Dedução de PF/PJ --------------------------------------------------------


@pytest.mark.parametrize(
    ("documento", "esperado"),
    [
        ("00000000000", TipoPessoa.FISICA),
        ("589.747.908-90", TipoPessoa.FISICA),
        ("00000000000191", TipoPessoa.JURIDICA),
        ("00.000.000/0001-91", TipoPessoa.JURIDICA),
    ],
)
def test_tipo_de_pessoa_vem_do_documento(documento, esperado):
    """O usuário não escolhe PF ou PJ — o CPF/CNPJ decide (AGENTS.md §4.5)."""
    assert deduzir_tipo_pessoa(documento) == esperado


@pytest.mark.parametrize("documento", ["", "123", "0000000000000", "abc"])
def test_documento_invalido_e_recusado(documento):
    with pytest.raises(ValueError):
        deduzir_tipo_pessoa(documento)


def test_contraparte_guarda_apenas_digitos():
    contraparte = Contraparte.objects.create(nome="Teste", documento="589.747.908-90")

    assert contraparte.documento == "58974790890"
    assert contraparte.tipo_pessoa == TipoPessoa.FISICA


# -- Vigência ----------------------------------------------------------------


def test_documento_sem_prazo_nao_vence(contraparte_pj, contrato_social):
    documento = _enviar(contraparte_pj, contrato_social, dias_atras=3650)

    assert documento.data_vencimento is None
    assert documento.esta_vigente


@pytest.mark.parametrize(
    ("dias_atras", "vencido"),
    [(0, False), (89, False), (90, False), (91, True)],
    ids=["hoje", "vespera", "no_limite", "um_dia_depois"],
)
def test_fronteira_dos_90_dias(contraparte_pj, comprovante_pj, dias_atras, vencido):
    """No 90º dia ainda vale; a partir do 91º, não."""
    documento = _enviar(contraparte_pj, comprovante_pj, dias_atras=dias_atras)

    assert documento.esta_vencido is vencido


def test_documento_apenas_enviado_nao_esta_vigente(contraparte_pj, contrato_social):
    """Estar completo não é estar aprovado — são estados distintos (AGENTS.md §4.5)."""
    documento = _enviar(contraparte_pj, contrato_social, status=StatusDocumento.ENVIADO)

    assert not documento.esta_vigente


# -- Kit de pessoa jurídica --------------------------------------------------


def test_kit_pj_ignora_documento_condicional(contraparte_pj):
    """A procuração é exigida 'quando houver' e não conta como pendência."""
    pendencias = {t.nome for t in contraparte_pj.pendencias_cadastrais()}

    assert "Procuração" not in pendencias
    assert len(pendencias) == 4


def test_kit_pj_completo(contraparte_pj):
    _completar(contraparte_pj)

    assert contraparte_pj.kit_completo()


def test_documento_vencido_volta_a_ser_pendencia(contraparte_pj, comprovante_pj):
    _completar(contraparte_pj)
    comprovante = contraparte_pj.documentos_cadastrais.get(tipo=comprovante_pj)
    comprovante.data_emissao = timezone.localdate() - timedelta(days=200)
    comprovante.save()

    pendencias = {t.nome for t in contraparte_pj.pendencias_cadastrais()}

    assert pendencias == {"Comprovante de endereço"}


# -- Kit de pessoa física e comprovação de renda (D20) -----------------------


def test_kit_pf_basico(contraparte_pf):
    pendencias = {t.nome for t in contraparte_pf.pendencias_cadastrais(Decimal("1000.00"))}

    assert pendencias == {
        "Documento de identificação (RG, CPF e/ou CNH)",
        "Comprovante de residência",
    }


@pytest.mark.parametrize(
    ("valor", "exige_renda"),
    [
        (Decimal("3999.99"), False),
        (Decimal("4000.00"), False),
        (Decimal("4000.01"), True),
        (Decimal("10000.00"), True),
    ],
    ids=["abaixo", "exatamente_no_limite", "um_centavo_acima", "bem_acima"],
)
def test_fronteira_da_comprovacao_de_renda(contraparte_pf, valor, exige_renda):
    """'Acima de R$ 4.000,00': o próprio limite não exige comprovação."""
    nomes = {t.nome for t in contraparte_pf.pendencias_cadastrais(valor)}
    pediu_renda = {"Holerite", "Declaração de Imposto de Renda"} & nomes

    assert bool(pediu_renda) is exige_renda


def test_holerite_ou_declaracao_de_ir_satisfaz_a_exigencia(contraparte_pf):
    """Documentos alternativos se substituem: basta um deles (AGENTS.md §4.5)."""
    valor = Decimal("5000.00")
    _enviar(contraparte_pf, TipoDocumento.objects.get(nome="Holerite"))

    nomes = {t.nome for t in contraparte_pf.pendencias_cadastrais(valor)}

    assert "Holerite" not in nomes
    assert "Declaração de Imposto de Renda" not in nomes


def test_pf_nao_recebe_exigencias_de_pj(contraparte_pf):
    nomes = {t.nome for t in contraparte_pf.pendencias_cadastrais(Decimal("10000.00"))}

    assert "Contrato Social / Última Alteração Contratual" not in nomes
