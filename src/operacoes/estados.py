"""
Estados e etapas do fluxo (AGENTS.md §4.1 e §4.7).

Nenhuma transição acontece fora dos métodos de modelo/serviço. Transição inválida
levanta `TransicaoInvalida`, nunca falha em silêncio.
"""

from django.db import models


class TransicaoInvalida(Exception):
    """Tentativa de mudar de estado por um caminho que o fluxo não permite."""


class StatusOperacao(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    AGUARDANDO_DOCUMENTOS = "aguardando_documentos", "Aguardando documentos"
    EM_ANALISE_DOCUMENTAL = "em_analise_documental", "Em análise documental"
    EM_CREDITO = "em_credito", "Em análise de crédito"
    EM_APROVACAO = "em_aprovacao", "Em aprovação"
    AGUARDANDO_ASSINATURA = "aguardando_assinatura", "Aguardando assinatura"
    ASSINADA = "assinada", "Assinada"
    CONCLUIDA = "concluida", "Concluída"
    REPROVADA = "reprovada", "Reprovada"
    DISPENSADA = "dispensada", "Dispensada (waiver)"
    CANCELADA = "cancelada", "Cancelada"


#: Estados a partir dos quais nada mais acontece.
ESTADOS_TERMINAIS = frozenset(
    {
        StatusOperacao.CONCLUIDA,
        StatusOperacao.REPROVADA,
        StatusOperacao.DISPENSADA,
        StatusOperacao.CANCELADA,
    }
)

#: Depois de assinado, o contrato existe no mundo real: desfazer não é cancelar,
#: é distrato — assunto do Jurídico, fora do sistema (AGENTS.md §4.7).
ESTADOS_QUE_NAO_CANCELAM = ESTADOS_TERMINAIS | {StatusOperacao.ASSINADA}

#: Transições permitidas. Reprovação é tratada à parte: pode partir de qualquer
#: estado não terminal.
TRANSICOES = {
    StatusOperacao.RASCUNHO: {StatusOperacao.AGUARDANDO_DOCUMENTOS, StatusOperacao.DISPENSADA},
    # As etapas de triagem, DD e crédito chegam cumpridas da habilitação, então o
    # contrato pode saltar direto para a assinatura — ou até para concluído, nos
    # enquadramentos em que só restam etapas da Genial (AGENTS.md §4.0).
    StatusOperacao.AGUARDANDO_DOCUMENTOS: {
        StatusOperacao.EM_ANALISE_DOCUMENTAL,
        StatusOperacao.EM_CREDITO,
        StatusOperacao.EM_APROVACAO,
        StatusOperacao.AGUARDANDO_ASSINATURA,
        StatusOperacao.CONCLUIDA,
    },
    StatusOperacao.EM_ANALISE_DOCUMENTAL: {
        StatusOperacao.EM_CREDITO,
        StatusOperacao.EM_APROVACAO,
        # Documento rejeitado devolve o contrato para o envio.
        StatusOperacao.AGUARDANDO_DOCUMENTOS,
        StatusOperacao.AGUARDANDO_ASSINATURA,
        StatusOperacao.CONCLUIDA,
    },
    StatusOperacao.EM_CREDITO: {
        StatusOperacao.EM_APROVACAO,
        StatusOperacao.AGUARDANDO_ASSINATURA,
        StatusOperacao.CONCLUIDA,
    },
    StatusOperacao.EM_APROVACAO: {
        StatusOperacao.AGUARDANDO_ASSINATURA,
        StatusOperacao.CONCLUIDA,
    },
    StatusOperacao.AGUARDANDO_ASSINATURA: {StatusOperacao.ASSINADA},
    StatusOperacao.ASSINADA: {StatusOperacao.CONCLUIDA},
    StatusOperacao.CONCLUIDA: set(),
    StatusOperacao.REPROVADA: set(),
    StatusOperacao.DISPENSADA: set(),
    StatusOperacao.CANCELADA: set(),
}


class Etapa(models.TextChoices):
    """As oito etapas do fluxo padrão do guia, na ordem em que ocorrem."""

    TRIAGEM = "triagem", "1. Triagem de documentos (CRM)"
    DUE_DILIGENCE = "due_diligence", "2. Due diligence (Compliance)"
    RISCO_CREDITO = "risco_credito", "3. Pesquisa de crédito (Risco/Crédito)"
    JURIDICO = "juridico", "4. Revisão jurídica e vigência (Jurídico ASA/Genial)"
    ASSINATURAS = "assinaturas", "5. Upload para assinatura (Clube)"
    ENVIO_NF = "envio_nf", "6. Envio de NFs para liquidação (Clube)"
    BOLETAGEM = "boletagem", "7. Boletagem (ASA/CRM)"
    LIQUIDACAO = "liquidacao", "8. Liquidação (Genial)"


#: Ordem canônica das etapas — usada para descobrir qual é a próxima pendente.
ORDEM_ETAPAS = [
    Etapa.TRIAGEM,
    Etapa.DUE_DILIGENCE,
    Etapa.RISCO_CREDITO,
    Etapa.JURIDICO,
    Etapa.ASSINATURAS,
    Etapa.ENVIO_NF,
    Etapa.BOLETAGEM,
    Etapa.LIQUIDACAO,
]

#: Etapas dentro do escopo do MVP (AGENTS.md §7, D8). As demais existem apenas
#: como registro de status, sem tela de trabalho.
ETAPAS_NO_ESCOPO = frozenset(
    {
        Etapa.TRIAGEM,
        Etapa.DUE_DILIGENCE,
        Etapa.RISCO_CREDITO,
        Etapa.JURIDICO,
        Etapa.ASSINATURAS,
    }
)

#: Papel responsável por decidir cada etapa. Risco/Crédito não tem usuário no MVP:
#: CRM ou Compliance registra o parecer em nome do time (AGENTS.md §4.2, D9).
PAPEL_RESPONSAVEL = {
    Etapa.TRIAGEM: "crm",
    Etapa.DUE_DILIGENCE: "compliance",
    Etapa.RISCO_CREDITO: "compliance",
    Etapa.JURIDICO: "juridico",
    Etapa.ASSINATURAS: "clube",
    Etapa.ENVIO_NF: "clube",
    Etapa.BOLETAGEM: "crm",
    Etapa.LIQUIDACAO: "crm",
}


class StatusEtapa(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EM_ANALISE = "em_analise", "Em análise"
    APROVADA = "aprovada", "Aprovada"
    REPROVADA = "reprovada", "Reprovada"
    DISPENSADA = "dispensada", "Não aplicável"
    REGISTRADA_EXTERNAMENTE = "registrada_externamente", "Registrada externamente"
    # Triagem, due diligence e crédito acontecem na habilitação da contraparte
    # (Fase 1) e não se repetem a cada contrato (AGENTS.md §4.0, D19).
    CUMPRIDA_NA_HABILITACAO = "cumprida_na_habilitacao", "Cumprida na habilitação"


#: Etapas resolvidas na validação do perfil — a operação as exibe como cumpridas,
#: para o fluxo aparecer inteiro, mas não as executa de novo (AGENTS.md D29).
#:
#: Crédito está aqui: **existe uma análise de crédito e ela acontece na esteira
#: do perfil** (D30). O contrato não a refaz; se for preciso reavaliar por
#: mudança de faixa ou de tipo, isso é uma revalidação do perfil.
ETAPAS_DA_HABILITACAO = frozenset(
    {Etapa.TRIAGEM, Etapa.DUE_DILIGENCE, Etapa.RISCO_CREDITO}
)
