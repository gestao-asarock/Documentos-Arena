"""
Fila do Jurídico (AGENTS.md §4.9, D34).

O Jurídico revisa contratos — e só isso. Não tria documento cadastral, não faz
due diligence, não analisa crédito. Por isso a fila dele traz apenas contratos
que já passaram por tudo isso e estão prontos para revisão.
"""

from contas.models import Papel
from operacoes.estados import Etapa, StatusEtapa
from operacoes.models import Operacao
from operacoes.servicos import avancar

PAPEIS_DO_JURIDICO = {Papel.JURIDICO, Papel.ADMINISTRADOR}


def pode_revisar(usuario) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=PAPEIS_DO_JURIDICO).exists()


def fila_juridica():
    """Contratos aguardando revisão jurídica, prontos para decidir.

    Basta a documentação ter **chegado**: conferir o Termo de Adesão é o trabalho
    desta etapa. Enquanto se exigia documento já aprovado, o contrato sumia da
    fila esperando uma triagem que ninguém tinha para fazer, e o Jurídico via
    "aguardando conferência" sem ter como conferir. O que a linearidade impede é
    revisar contrato **inexistente** — e isso `documentacao_entregue` garante.
    """
    candidatos = (
        Operacao.objects.filter(etapas__etapa=Etapa.JURIDICO, etapas__status=StatusEtapa.PENDENTE)
        .exclude(status__in=["cancelada", "reprovada", "concluida", "dispensada"])
        .select_related("contraparte", "tipo_operacao", "regra")
        .prefetch_related("etapas", "documentos")
        .distinct()
        .order_by("data_criacao")
    )
    return [
        operacao
        for operacao in candidatos
        if operacao.documentacao_entregue and operacao.etapa_atual.etapa == Etapa.JURIDICO
    ]


def aguardando_documentacao():
    """Contratos que virão ao Jurídico, com o motivo de ainda não estarem prontos.

    Ficam à vista para o Jurídico saber o que vem — sem ação possível ainda. O
    motivo importa: "falta o Clube enviar" e "documento recusado, esperando
    reenvio" são situações diferentes, e dizer só "aguardando documentos"
    confunde. Documento **enviado** já não cai aqui: vai para a fila de revisão.
    """
    candidatos = (
        Operacao.objects.filter(etapas__etapa=Etapa.JURIDICO, etapas__status=StatusEtapa.PENDENTE)
        .exclude(status__in=["cancelada", "reprovada", "concluida", "dispensada"])
        .select_related("contraparte", "tipo_operacao")
        .prefetch_related("etapas", "documentos")
        .distinct()
        .order_by("data_criacao")
    )

    pendentes = []
    for operacao in candidatos:
        if operacao.documentacao_entregue:
            continue

        # Recalcula antes de mostrar: o status gravado pode ter ficado para trás
        # de uma mudança de regra, e duas informações conflitantes na mesma tela
        # confundem mais do que ajudam.
        avancar(operacao)
        situacao = operacao.situacao_documental()
        if situacao["com_problema"]:
            operacao.motivo_da_espera = "Documento recusado, aguardando reenvio"
        else:
            operacao.motivo_da_espera = "Aguardando o Clube enviar os documentos"
        pendentes.append(operacao)
    return pendentes
