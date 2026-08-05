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
from django.urls import reverse
from django.utils import timezone

from analise.servicos import aprovar_documento, rejeitar_documento
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral, Habilitacao
from operacoes.dossie import ATENCAO, CONCLUIDA, EXTERNA, montar
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


def test_documento_enviado_ja_conclui_a_checagem(contrato, crm):
    """Enviar cumpre a parte do Clube; conferir é da revisão jurídica."""
    _enviar(contrato, crm)

    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.situacao == CONCLUIDA
    assert "revisão jurídica" in documentos.detalhe
    assert "não enviado" not in " ".join(documentos.itens)


def test_documento_enviado_mostra_quem_enviou_e_quando(contrato, crm):
    documento = _enviar(contrato, crm)

    documentos = _por_titulo(contrato)["Documentos do contrato"]

    assert documentos.responsavel == str(crm)
    assert documentos.data == documento.data_envio


def test_enviar_nao_libera_a_assinatura(contrato, crm):
    """A checagem fica verde, mas o contrato só sai depois do jurídico (D33)."""
    from operacoes.dossie import pronto_para_assinatura

    _enviar(contrato, crm)

    assert not pronto_para_assinatura(contrato)


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


def _parecer_de_compliance(contrato, crm):
    """Due diligence concluída, com relatório anexado (AGENTS.md D50)."""
    from compliance.models import ParecerCompliance, RelatorioParecer, StatusParecer, Veredito

    parecer = ParecerCompliance.objects.create(
        habilitacao=contrato.contraparte.habilitacao_vigente,
        status=StatusParecer.CONCLUIDO,
        veredito=Veredito.BAIXO,
        justificativa="Nada consta nas fontes consultadas.",
        analista=crm,
        data_conclusao=timezone.now(),
    )
    relatorio = RelatorioParecer.objects.create(
        parecer=parecer,
        arquivo=SimpleUploadedFile("dd.pdf", PDF),
        nome_original="dd.pdf",
        descricao="Consulta às listas restritivas",
    )
    return parecer, relatorio


def test_dossie_traz_a_justificativa_e_o_relatorio_do_compliance(contrato, crm):
    """Quem assina precisa ler o parecer inteiro, não só o veredito."""
    _, relatorio = _parecer_de_compliance(contrato, crm)

    checagem = _por_titulo(contrato)["Due diligence (Compliance)"]

    assert checagem.observacao == "Nada consta nas fontes consultadas."
    assert [a.titulo for a in checagem.anexos] == ["dd.pdf"]
    assert checagem.anexos[0].descricao == "Consulta às listas restritivas"
    assert str(relatorio.pk) in checagem.anexos[0].url


def test_relatorio_do_dossie_e_baixavel(client, contrato, crm):
    _, relatorio = _parecer_de_compliance(contrato, crm)
    client.force_login(crm)

    resposta = client.get(
        reverse("operacoes:baixar_relatorio", args=[contrato.pk, "compliance", relatorio.pk])
    )

    assert resposta.status_code == 200
    assert b"".join(resposta.streaming_content) == PDF


def test_relatorio_de_outra_contraparte_nao_vaza(
    client, contrato, crm, contraparte_sem_habilitacao
):
    """Trocar o id na URL não pode entregar o parecer de outra pessoa."""
    from compliance.models import ParecerCompliance, RelatorioParecer

    outra = Habilitacao.objects.create(contraparte=contraparte_sem_habilitacao)
    alheio = RelatorioParecer.objects.create(
        parecer=ParecerCompliance.objects.create(habilitacao=outra),
        arquivo=SimpleUploadedFile("alheio.pdf", PDF),
    )
    client.force_login(crm)

    resposta = client.get(
        reverse("operacoes:baixar_relatorio", args=[contrato.pk, "compliance", alheio.pk])
    )

    assert resposta.status_code == 404


def test_origem_desconhecida_e_recusada(client, contrato, crm):
    client.force_login(crm)

    resposta = client.get(reverse("operacoes:baixar_relatorio", args=[contrato.pk, "inventada", 1]))

    assert resposta.status_code == 403


def test_juridico_decidido_aparece_concluido(contrato, crm):
    documento = _enviar(contrato, crm)
    aprovar_documento(documento, usuario=crm)
    contrato.refresh_from_db()

    etapa = contrato.etapas.get(etapa=Etapa.JURIDICO)
    decidir_etapa(etapa, aprovada=True, parecer="Termo confere.", usuario=crm)

    juridica = next(c for c in montar(contrato) if "jurídica" in c.titulo.lower())
    assert juridica.situacao == CONCLUIDA
    assert juridica.responsavel == str(crm)
