from decimal import Decimal

import pytest

from contas.models import Usuario
from contrapartes.models import Contraparte, Habilitacao, StatusHabilitacao, TipoPessoa
from operacoes.models import Operacao, RegraEnquadramento, TipoOperacao


@pytest.fixture
def usuario(db):
    return Usuario.objects.create_user(username="crm.teste", password="senha-de-teste")


@pytest.fixture
def contraparte(db):
    """Contraparte **já habilitada**: a Fase 2 não começa sem isso (AGENTS.md §4.0)."""
    # Dados fictícios: CNPJ inválido de propósito (AGENTS.md §6).
    contraparte = Contraparte.objects.create(
        tipo_pessoa=TipoPessoa.JURIDICA,
        nome="Fornecedora Fictícia Ltda",
        documento="00000000000191",
    )
    Habilitacao.objects.create(contraparte=contraparte, status=StatusHabilitacao.HABILITADA)
    return contraparte


@pytest.fixture
def contraparte_sem_habilitacao(db):
    return Contraparte.objects.create(
        tipo_pessoa=TipoPessoa.JURIDICA,
        nome="Fornecedora Não Habilitada Ltda",
        documento="00000000000272",
    )


@pytest.fixture
def aluguel(db):
    """Tipo isolado para os testes de motor.

    Não reutiliza o "Aluguel de Espaço" vindo da carga inicial: estes testes montam
    faixas próprias, e misturá-las com os dados reais produziria enquadramento
    ambíguo — que é justamente o que um dos testes verifica.
    """
    return TipoOperacao.objects.create(nome="Tipo de teste: motor de enquadramento")


@pytest.fixture
def regra_piloto(aluguel):
    """Fluxo piloto: Aluguel de Espaço — Evento até R$ 5.000,00 (AGENTS.md §4.3)."""
    return RegraEnquadramento.objects.create(
        tipo_operacao=aluguel,
        criterio="Evento até R$ 5.000,00",
        valor_minimo=Decimal("0.01"),
        valor_maximo=Decimal("5000.00"),
        exige_triagem=True,
        exige_due_diligence=True,
        exige_risco_credito=True,
        exige_juridico=True,
        exige_assinaturas=True,
        exige_boletagem=True,
        implementada=True,
    )


@pytest.fixture
def criar_operacao(contraparte, aluguel, usuario):
    def _criar(valor: str) -> Operacao:
        return Operacao.objects.create(
            contraparte=contraparte,
            tipo_operacao=aluguel,
            valor_total=Decimal(valor),
            descricao="Locação de espaço para evento fictício",
            criada_por=usuario,
        )

    return _criar
