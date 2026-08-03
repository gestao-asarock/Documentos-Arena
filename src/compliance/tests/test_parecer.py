"""
Due diligence do perfil (AGENTS.md §4.7, D22, D29).

O veredito é humano e obrigatório. Concluir aqui valida o perfil — crédito é por
contrato, porque depende do valor (D30).
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from compliance.models import ParecerCompliance, StatusParecer, Veredito
from compliance.servicos import (
    ParecerIncompleto,
    concluir_parecer,
    fila_de_compliance,
    obter_ou_criar_parecer,
    recusar_contraparte,
)
from contas.models import Papel, Usuario
from contrapartes.models import StatusHabilitacao
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def compliance():
    return _usuario("compliance.dd", Papel.COMPLIANCE)


@pytest.fixture
def clube():
    return _usuario("clube.dd", Papel.CLUBE)


@pytest.fixture
def habilitacao(clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    solicitacao = Solicitacao.objects.create(contraparte=contraparte, criada_por=clube)
    registro = abrir_habilitacao(solicitacao, usuario=clube)
    registro.status = StatusHabilitacao.EM_COMPLIANCE
    registro.save()
    return registro


def test_fila_traz_quem_esta_em_compliance(habilitacao):
    assert list(fila_de_compliance()) == [habilitacao]


def test_clube_nao_acessa_a_due_diligence(client, clube, habilitacao):
    client.force_login(clube)

    assert client.get(reverse("compliance:fila")).status_code == 403
    assert client.get(reverse("compliance:parecer", args=[habilitacao.pk])).status_code == 403


def test_parecer_nasce_em_rascunho(habilitacao, compliance):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)

    assert parecer.status == StatusParecer.RASCUNHO
    assert not parecer.esta_concluido


def test_concluir_exige_veredito(habilitacao, compliance):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.justificativa = "Sem apontamentos."

    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, usuario=compliance)


def test_concluir_exige_justificativa(habilitacao, compliance):
    """Veredito sem porquê não é parecer."""
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.veredito = Veredito.BAIXO

    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, usuario=compliance)


def test_conclusao_manda_o_perfil_para_o_credito(habilitacao, compliance):
    """O perfil só é validado depois do crédito (AGENTS.md D30)."""
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.veredito = Veredito.BAIXO
    parecer.justificativa = "Nada consta nas fontes consultadas."

    concluir_parecer(parecer, usuario=compliance)
    habilitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.EM_CREDITO
    # Ainda não pode contratar: falta o crédito.
    assert not habilitacao.contraparte.esta_habilitada


def test_compliance_sozinho_nao_libera_o_contrato(habilitacao, compliance):
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.veredito = Veredito.MODERADO
    parecer.justificativa = "Processos cíveis antigos, sem relação com o objeto."

    concluir_parecer(parecer, usuario=compliance)
    perfil = habilitacao.solicitacoes.first()
    perfil.refresh_from_db()

    assert perfil.status != "pronta_para_contrato"


def test_risco_alto_nao_bloqueia_sozinho(habilitacao, compliance):
    """Escalar é decisão de governança, ainda em aberto (P6 no CLAUDE.md)."""
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.veredito = Veredito.ALTO
    parecer.justificativa = "Sócio com processo criminal em andamento."

    concluir_parecer(parecer, usuario=compliance)
    habilitacao.refresh_from_db()

    assert parecer.eh_risco_alto
    assert habilitacao.status == StatusHabilitacao.EM_CREDITO


def test_recusa_encerra_a_habilitacao(habilitacao, compliance):
    recusar_contraparte(habilitacao, usuario=compliance, motivo="Consta em lista restritiva.")
    habilitacao.refresh_from_db()

    assert habilitacao.status == StatusHabilitacao.RECUSADA
    assert not habilitacao.contraparte.esta_habilitada


def test_recusa_exige_motivo(habilitacao, compliance):
    with pytest.raises(ParecerIncompleto):
        recusar_contraparte(habilitacao, usuario=compliance, motivo="  ")


def test_blocos_em_branco_sao_listados(habilitacao, compliance):
    """Aviso ao analista, não impedimento: nem todo bloco se aplica."""
    parecer = obter_ou_criar_parecer(habilitacao, usuario=compliance)
    parecer.processos = "Nada consta."
    parecer.save()

    em_branco = parecer.blocos_em_branco()

    assert "Processos judiciais e administrativos" not in em_branco
    assert "Sanções e listas restritivas" in em_branco


def test_parecer_pela_tela_salva_e_conclui(client, habilitacao, compliance):
    client.force_login(compliance)

    client.post(
        reverse("compliance:parecer", args=[habilitacao.pk]),
        {
            "situacao_cadastral": "CPF regular.",
            "processos": "Nada consta.",
            "sancoes": "Nada consta.",
            "pep": "Não é PEP.",
            "bloqueios": "",
            "midia_adversa": "Sem notícias negativas.",
            "termos_pesquisados": "nome + fraude; nome + processo",
            "beneficiario_final": "",
            "socios": "",
            "parte_relacionada": "Sem vínculo.",
            "veredito": Veredito.BAIXO,
            "justificativa": "Nada consta nas fontes consultadas.",
            "acao": "concluir",
        },
    )

    parecer = ParecerCompliance.objects.get(habilitacao=habilitacao)
    assert parecer.esta_concluido
    assert parecer.analista == compliance
    assert parecer.termos_pesquisados == "nome + fraude; nome + processo"
