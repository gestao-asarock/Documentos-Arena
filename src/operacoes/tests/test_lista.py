"""
A lista de contratos: abas, filtros, ordenação e paginação (CLAUDE.md).

A tabela sem recorte funcionava com trinta contratos. O que estes testes
protegem é o que quebra com trezentos: filtro que não bate com a coluna, ordem
que muda de página para página, e recorte que deixa passar registro de outro
time.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from contas.models import Papel, Usuario
from operacoes.estados import Etapa, StatusOperacao
from operacoes.models import Operacao, TipoOperacao
from operacoes.servicos import enquadrar

pytestmark = pytest.mark.django_db

URL = reverse("operacoes:lista")


@pytest.fixture
def interno(db):
    usuario = Usuario.objects.create_user(username="crm.lista", password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=Papel.CRM))
    return usuario


@pytest.fixture
def criar(contraparte, aluguel, interno):
    def _criar(valor="1000.00", **extra):
        return Operacao.objects.create(
            contraparte=contraparte,
            tipo_operacao=extra.pop("tipo_operacao", aluguel),
            valor_total=Decimal(valor),
            descricao=extra.pop("descricao", "Contrato de teste"),
            criada_por=extra.pop("criada_por", interno),
            **extra,
        )

    return _criar


def listar(client, **parametros):
    resposta = client.get(URL, parametros)
    assert resposta.status_code == 200
    return resposta


def pks(resposta):
    return [operacao.pk for operacao in resposta.context["operacoes"]]


# -- Busca -----------------------------------------------------------------


def test_busca_pelo_numero_do_contrato(client, interno, criar):
    alvo, outro = criar(), criar()
    client.force_login(interno)

    assert pks(listar(client, busca=f"#{alvo.pk}")) == [alvo.pk]
    assert outro.pk not in pks(listar(client, busca=str(alvo.pk)))


def test_busca_por_documento_ignora_a_pontuacao(client, interno, criar, contraparte):
    """Quem cola o CNPJ de outra tela traz os pontos junto; o banco guarda sem eles."""
    contrato = criar()
    client.force_login(interno)

    assert pks(listar(client, busca="00.000.000/0001-91")) == [contrato.pk]


def test_busca_por_parte_do_nome(client, interno, criar):
    contrato = criar()
    client.force_login(interno)

    assert pks(listar(client, busca="Fictícia")) == [contrato.pk]
    assert pks(listar(client, busca="Nome Que Não Existe")) == []


# -- Faixas ----------------------------------------------------------------


def test_faixa_de_valor_inclui_as_duas_pontas(client, interno, criar):
    """Fronteira de valor é onde o dinheiro erra (AGENTS.md §3)."""
    abaixo, no_piso, no_teto, acima = (
        criar("999.99"),
        criar("1000.00"),
        criar("5000.00"),
        criar("5000.01"),
    )
    client.force_login(interno)

    encontrados = pks(listar(client, valor_de="1.000,00", valor_ate="5.000,00"))

    assert set(encontrados) == {no_piso.pk, no_teto.pk}
    assert abaixo.pk not in encontrados
    assert acima.pk not in encontrados


def test_faixa_de_data_do_evento(client, interno, criar):
    hoje = date.today()
    dentro = criar(data_evento=hoje)
    fora = criar(data_evento=hoje + timedelta(days=10))
    client.force_login(interno)

    encontrados = pks(listar(client, evento_de=hoje.strftime("%d/%m/%Y")))

    assert dentro.pk in encontrados
    assert fora.pk in encontrados

    so_hoje = pks(
        listar(
            client,
            evento_de=hoje.strftime("%d/%m/%Y"),
            evento_ate=hoje.strftime("%d/%m/%Y"),
        )
    )
    assert so_hoje == [dentro.pk]


def test_parado_ha_mais_de_n_dias(client, interno, criar):
    """O filtro que revela o que travou: registro parado não muda de status sozinho."""
    parado = criar()
    criar()  # recém-criado: nunca aparece nos filtros de "sem movimento".
    Operacao.objects.filter(pk=parado.pk).update(
        data_atualizacao=timezone.now() - timedelta(days=20)
    )
    client.force_login(interno)

    assert pks(listar(client, parado="15")) == [parado.pk]
    assert pks(listar(client, parado="30")) == []


def test_data_invalida_nao_esvazia_a_lista(client, interno, criar):
    """Erro de digitação mostra o aviso no campo, mas a lista continua de pé."""
    contrato = criar()
    client.force_login(interno)

    resposta = listar(client, criado_de="31/31/2026")

    assert pks(resposta) == [contrato.pk]
    assert resposta.context["filtro"].errors


# -- Situação e etapa ------------------------------------------------------


def test_filtra_por_situacao(client, interno, criar):
    rascunho = criar()
    cancelado = criar()
    cancelado.cancelar("Cancelado no teste.", usuario=interno)
    cancelado.save()
    client.force_login(interno)

    assert pks(listar(client, situacao=StatusOperacao.CANCELADA)) == [cancelado.pk]
    assert pks(listar(client, situacao=StatusOperacao.RASCUNHO)) == [rascunho.pk]


def test_filtra_pela_etapa_da_vez(client, interno, criar, regra_piloto):
    """A etapa vem da anotação, e ela precisa casar com o que a coluna mostra.

    A etapa da vez de um contrato recém-enquadrado é a **revisão jurídica**, e
    não a triagem: com a contraparte já habilitada, as três primeiras chegam
    cumpridas da Fase 1 (AGENTS.md §4.0, D29). O teste pergunta ao próprio
    contrato qual é, para não codificar aqui uma regra que é de outro lugar.
    """
    contrato = criar()
    enquadrar(contrato, usuario=interno)
    sem_etapas = criar()
    client.force_login(interno)

    da_vez = contrato.etapa_atual.etapa
    assert da_vez == Etapa.JURIDICO

    encontrados = pks(listar(client, etapa=da_vez))

    assert encontrados == [contrato.pk]
    assert sem_etapas.pk not in encontrados
    assert pks(listar(client, etapa=Etapa.TRIAGEM)) == []


# -- Ordenação -------------------------------------------------------------


def test_ordena_por_valor_nos_dois_sentidos(client, interno, criar):
    barato, caro = criar("100.00"), criar("900.00")
    client.force_login(interno)

    assert pks(listar(client, ordem="valor")) == [barato.pk, caro.pk]
    assert pks(listar(client, ordem="-valor")) == [caro.pk, barato.pk]


def test_ordem_desconhecida_cai_no_padrao(client, interno, criar):
    """URL editada à mão não pode ordenar por campo que a tela não expôs."""
    antigo, novo = criar(), criar()
    client.force_login(interno)

    padrao = pks(listar(client))

    assert pks(listar(client, ordem="contraparte__documento")) == padrao
    assert padrao == [novo.pk, antigo.pk]


# -- Paginação -------------------------------------------------------------


def test_pagina_tem_no_maximo_vinte_e_cinco(client, interno, criar):
    for _ in range(26):
        criar()
    client.force_login(interno)

    primeira = listar(client)
    segunda = listar(client, pagina="2")

    assert len(pks(primeira)) == 25
    assert len(pks(segunda)) == 1
    assert primeira.context["total"] == 26


def test_contagem_descreve_a_lista_e_nao_a_pagina(client, interno, criar):
    """ "30 registros" com 25 na tela: a contagem responde ao filtro, não à página."""
    for _ in range(30):
        criar()
    client.force_login(interno)

    resposta = listar(client)

    assert resposta.context["total"] == 30
    assert len(pks(resposta)) == 25


def test_pagina_fora_do_intervalo_nao_quebra(client, interno, criar):
    criar()
    client.force_login(interno)

    assert listar(client, pagina="999").status_code == 200


# -- Abas ------------------------------------------------------------------


def test_abas_contam_respeitando_os_outros_filtros(client, interno, criar, aluguel):
    """A soma das abas precisa bater com o que está na tela (operacoes/filtros.py)."""
    outro_tipo = TipoOperacao.objects.create(nome="Tipo de teste: compras")
    criar("100.00")
    criar("900.00")
    criar("900.00", tipo_operacao=outro_tipo)
    client.force_login(interno)

    abas = {
        aba["rotulo"]: aba["total"] for aba in listar(client, valor_de="500,00").context["abas"]
    }

    assert abas["Todos"] == 2
    assert abas[aluguel.nome] == 1
    assert abas[outro_tipo.nome] == 1


def test_aba_recorta_por_tipo(client, interno, criar):
    outro_tipo = TipoOperacao.objects.create(nome="Tipo de teste: compras")
    do_aluguel = criar()
    de_compras = criar(tipo_operacao=outro_tipo)
    client.force_login(interno)

    assert pks(listar(client, tipo=str(outro_tipo.pk))) == [de_compras.pk]
    assert do_aluguel.pk not in pks(listar(client, tipo=str(outro_tipo.pk)))


def test_aba_nao_conta_como_filtro_aplicado(client, interno, criar, aluguel):
    """A aba é navegação: acender "há filtros" nela confundiria com recorte."""
    criar()
    client.force_login(interno)

    assert not listar(client, tipo=str(aluguel.pk)).context["filtro"].tem_filtro
    assert listar(client, busca="qualquer").context["filtro"].tem_filtro


# -- Visibilidade ----------------------------------------------------------


def test_filtro_nao_alcanca_contrato_invisivel(client, contraparte, aluguel):
    """Filtrar não é uma porta lateral: o recorte parte do que o usuário já vê."""
    dono = Usuario.objects.create_user(username="clube.dono", password="senha-de-teste")
    dono.groups.add(Group.objects.get(name=Papel.CLUBE))
    de_fora = Usuario.objects.create_user(username="clube.fora", password="senha-de-teste")

    contrato = Operacao.objects.create(
        contraparte=contraparte,
        tipo_operacao=aluguel,
        valor_total=Decimal("1000.00"),
        descricao="Contrato de outro time",
        criada_por=dono,
    )

    client.force_login(de_fora)

    assert pks(listar(client, busca=str(contrato.pk))) == []
    assert pks(listar(client)) == []


# -- Painéis do formulário de filtro ---------------------------------------


def test_tipo_de_contrato_nao_aparece_no_painel(client, interno, criar, aluguel):
    """O tipo é aba, e só aba.

    Como campo, ele apareceria três vezes na mesma página com o mesmo `name`:
    aba, campo escondido e select do painel. O escondido guarda a aba entre um
    filtro e outro; um select ao lado dele sobrescreveria a escolha.
    """
    criar()
    client.force_login(interno)

    filtro = listar(client, tipo=str(aluguel.pk)).context["filtro"]
    nomes = [campo.name for campo in filtro.campos_avancados]

    assert "tipo" not in nomes
    assert "busca" not in nomes
    assert "contraparte" not in nomes


def test_datas_ficam_num_painel_separado(client, interno, criar):
    """Oito campos de tempo no meio dos outros escondiam o que se usa toda hora."""
    criar()
    client.force_login(interno)

    filtro = listar(client).context["filtro"]
    de_data = [campo.name for campo in filtro.campos_de_data]
    gerais = [campo.name for campo in filtro.campos_gerais]

    assert set(de_data) == {
        "evento_de",
        "evento_ate",
        "criado_de",
        "criado_ate",
        "movimentado_de",
        "movimentado_ate",
        "parado",
    }
    assert "situacao" in gerais
    assert "valor_de" in gerais
    # Nenhum campo em dois painéis, e nenhum de fora dos dois.
    assert set(de_data).isdisjoint(gerais)
    assert set(de_data) | set(gerais) == {campo.name for campo in filtro.campos_avancados}


def test_contagem_por_painel_diz_de_onde_veio_o_recorte(client, interno, criar):
    """Cada painel abre sozinho quando tem filtro, e o número diz quantos."""
    criar()
    client.force_login(interno)

    filtro = listar(client, situacao=StatusOperacao.RASCUNHO, parado="7").context["filtro"]

    assert filtro.filtros_gerais == 1
    assert filtro.filtros_de_data == 1

    limpo = listar(client).context["filtro"]

    assert limpo.filtros_gerais == 0
    assert limpo.filtros_de_data == 0
