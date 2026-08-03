"""
Análise de risco e crédito, por contrato (AGENTS.md §4.8, D9, D30).

O parecer vale para o par contraparte + enquadramento: mesma pessoa, mesmo tipo
e mesma faixa reaproveitam; mudou de faixa, nova análise.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from contas.models import Papel, Usuario
from contrapartes.models import (
    ArquivoDocumento,
    Contraparte,
    DocumentoCadastral,
    Habilitacao,
    StatusHabilitacao,
)
from credito.models import ParecerCredito, StatusParecer, Veredito
from credito.servicos import (
    ParecerIncompleto,
    concluir_parecer,
    fila_de_credito,
    obter_ou_criar_parecer,
    pode_analisar,
    recusar_operacao,
)
from documentos.models import StatusDocumento
from operacoes.estados import Etapa, StatusEtapa, StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import avancar, enquadrar

pytestmark = pytest.mark.django_db


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.credito", Papel.CLUBE)


@pytest.fixture
def crm():
    return _usuario("crm.credito", Papel.CRM)


@pytest.fixture
def contraparte():
    """Perfil já validado: sem isso não há contrato (AGENTS.md D29)."""
    contraparte = Contraparte.objects.create(nome="Contratante Fictício", documento="58974790890")
    Habilitacao.objects.create(contraparte=contraparte, status=StatusHabilitacao.HABILITADA)
    return contraparte


@pytest.fixture
def criar_operacao(contraparte, crm):
    """Contrato com a documentação já satisfeita.

    O fluxo é linear: sem documento aprovado nenhuma etapa é decidida, e aqui o
    assunto é o crédito, não a documentação.
    """

    def _criar(valor: str = "2000.00") -> Operacao:
        operacao = Operacao.objects.create(
            contraparte=contraparte,
            tipo_operacao=TipoOperacao.objects.get(nome="Aluguel de Espaço"),
            descricao="Formatura de balé",
            valor_total=Decimal(valor),
            criada_por=crm,
        )
        enquadrar(operacao, usuario=crm)

        for tipo in operacao.documentos_pendentes():
            documento = DocumentoCadastral.objects.create(
                contraparte=contraparte, tipo=tipo, status=StatusDocumento.APROVADO
            )
            ArquivoDocumento.objects.create(
                documento=documento, arquivo="cadastral/ficticio.pdf"
            )
            operacao.documentos.add(documento)

        avancar(operacao)
        operacao.refresh_from_db()
        return operacao

    return _criar


@pytest.fixture
def operacao(criar_operacao):
    return criar_operacao()


def test_credito_e_por_contrato(operacao):
    """O piloto exige Risco/Crédito, e a etapa nasce pendente no contrato."""
    etapa = operacao.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.PENDENTE


def test_fila_traz_contratos_em_credito(operacao):
    operacao.status = StatusOperacao.EM_CREDITO
    operacao.save()

    assert list(fila_de_credito()) == [operacao]


def test_crm_e_compliance_registram_o_parecer():
    """O time de Risco não é usuário no MVP (D9)."""
    assert pode_analisar(_usuario("crm.perm", Papel.CRM))
    assert pode_analisar(_usuario("compliance.perm", Papel.COMPLIANCE))
    assert not pode_analisar(_usuario("clube.perm", Papel.CLUBE))
    assert not pode_analisar(_usuario("juridico.perm", Papel.JURIDICO))


def test_clube_nao_acessa(client, clube, operacao):
    client.force_login(clube)

    assert client.get(reverse("credito:fila")).status_code == 403
    assert client.get(reverse("credito:parecer", args=[operacao.pk])).status_code == 403


def test_concluir_exige_veredito_e_justificativa(operacao, crm):
    parecer = obter_ou_criar_parecer(operacao, usuario=crm)

    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, operacao, usuario=crm)

    parecer.veredito = Veredito.BAIXO
    with pytest.raises(ParecerIncompleto):
        concluir_parecer(parecer, operacao, usuario=crm)


def test_conclusao_aprova_a_etapa_de_credito(operacao, crm):
    parecer = obter_ou_criar_parecer(operacao, usuario=crm)
    parecer.veredito = Veredito.BAIXO
    parecer.justificativa = "Sem restrições; renda compatível."

    concluir_parecer(parecer, operacao, usuario=crm)
    etapa = operacao.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert parecer.esta_concluido
    assert etapa.status == StatusEtapa.APROVADA


def test_parecer_e_reaproveitado_no_mesmo_enquadramento(criar_operacao, crm):
    """Mesma contraparte, mesmo tipo e mesma faixa: não se refaz o crédito (D30)."""
    primeira = criar_operacao("2000.00")
    parecer = obter_ou_criar_parecer(primeira, usuario=crm)
    parecer.veredito = Veredito.BAIXO
    parecer.justificativa = "Sem restrições."
    concluir_parecer(parecer, primeira, usuario=crm)

    segunda = criar_operacao("3000.00")
    etapa = segunda.etapas.get(etapa=Etapa.RISCO_CREDITO)

    assert etapa.status == StatusEtapa.CUMPRIDA_NA_HABILITACAO
    assert "Crédito já analisado" in etapa.parecer
    assert ParecerCredito.objects.count() == 1


def test_parecer_pertence_ao_par_contraparte_e_enquadramento(operacao, crm):
    parecer = obter_ou_criar_parecer(operacao, usuario=crm)

    assert parecer.contraparte == operacao.contraparte
    assert parecer.regra == operacao.regra


def test_recusa_reprova_o_contrato_sem_derrubar_o_perfil(operacao, crm):
    recusar_operacao(operacao, usuario=crm, motivo="Restrições financeiras graves.")
    operacao.refresh_from_db()

    assert operacao.status == StatusOperacao.REPROVADA
    # O perfil da contraparte continua válido para outros contratos.
    assert operacao.contraparte.esta_habilitada


def test_recusa_exige_motivo(operacao, crm):
    with pytest.raises(ParecerIncompleto):
        recusar_operacao(operacao, usuario=crm, motivo="")


def test_parecer_pela_tela_conclui(client, operacao, crm):
    client.force_login(crm)

    client.post(
        reverse("credito:parecer", args=[operacao.pk]),
        {
            "consulta": "Serasa consultado em 03/08/2026, score 812.",
            "restricoes": "Nada consta.",
            "pendencias": "Nada consta.",
            "capacidade": "Renda compatível com R$ 2.000,00.",
            "balanco": "",
            "veredito": Veredito.BAIXO,
            "justificativa": "Sem restrições.",
            "registrado_em_nome_do_time": "on",
            "acao": "concluir",
        },
    )

    parecer = ParecerCredito.objects.get(contraparte=operacao.contraparte)
    assert parecer.status == StatusParecer.CONCLUIDO


def test_blocos_em_branco_sao_listados(operacao, crm):
    parecer = obter_ou_criar_parecer(operacao, usuario=crm)
    parecer.consulta = "Score 700."
    parecer.save()

    em_branco = parecer.blocos_em_branco()

    assert "Consulta de crédito (Serasa e afins)" not in em_branco
    assert "Balanço, DRE e faturamento" in em_branco
