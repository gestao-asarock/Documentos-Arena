"""Serviços de due diligence (AGENTS.md §4.7)."""

from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar
from contas.models import Papel
from contrapartes.models import Habilitacao, StatusHabilitacao

from .models import ParecerCompliance, StatusParecer, Veredito

PAPEIS_DE_COMPLIANCE = {Papel.COMPLIANCE, Papel.ADMINISTRADOR}


def pode_analisar(usuario) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=PAPEIS_DE_COMPLIANCE).exists()


def fila_de_compliance():
    """Contrapartes com o dossiê completo, esperando due diligence."""
    return (
        Habilitacao.objects.filter(status=StatusHabilitacao.EM_COMPLIANCE)
        .select_related("contraparte")
        .order_by("data_criacao")
    )


def obter_ou_criar_parecer(habilitacao: Habilitacao, *, usuario=None) -> ParecerCompliance:
    parecer, criado = ParecerCompliance.objects.get_or_create(
        habilitacao=habilitacao, defaults={"analista": usuario}
    )
    if criado:
        registrar(
            acao=Acao.CONSULTA_COMPLIANCE,
            descricao=f"Due diligence iniciada para a contraparte #{habilitacao.contraparte_id}",
            objeto=habilitacao,
            usuario=usuario,
        )
    return parecer


class ParecerIncompleto(Exception):
    """Falta veredito ou justificativa para concluir."""


@transaction.atomic
def concluir_parecer(parecer: ParecerCompliance, *, usuario) -> Habilitacao:
    """Fecha a due diligence e manda o perfil para a análise de crédito.

    O veredito é humano e obrigatório: sem ele o perfil não avança
    (AGENTS.md §4.7).
    """
    if not parecer.veredito:
        raise ParecerIncompleto("Escolha o veredito de risco para concluir.")
    if not parecer.justificativa.strip():
        raise ParecerIncompleto("Justifique o veredito para concluir.")

    parecer.status = StatusParecer.CONCLUIDO
    parecer.analista = parecer.analista or usuario
    parecer.data_conclusao = timezone.now()
    parecer.save()

    # Aprovado no compliance, o perfil segue para a análise de crédito (D30).
    habilitacao = parecer.habilitacao
    habilitacao.status = StatusHabilitacao.EM_CREDITO
    habilitacao.save()

    registrar(
        acao=Acao.APROVACAO,
        descricao=(
            f"Due diligence concluída para a contraparte #{habilitacao.contraparte_id}: "
            f"{parecer.get_veredito_display()}"
        ),
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao


@transaction.atomic
def recusar_contraparte(habilitacao: Habilitacao, *, usuario, motivo: str) -> Habilitacao:
    """Barra a contraparte. Estado terminal — a Fase 2 não acontece."""
    if not motivo.strip():
        raise ParecerIncompleto("Informe o motivo da recusa.")

    habilitacao.status = StatusHabilitacao.RECUSADA
    habilitacao.motivo_recusa = motivo
    habilitacao.save()

    registrar(
        acao=Acao.REPROVACAO,
        descricao=f"Contraparte #{habilitacao.contraparte_id} recusada no compliance",
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao


__all__ = [
    "ParecerIncompleto",
    "Veredito",
    "concluir_parecer",
    "fila_de_compliance",
    "obter_ou_criar_parecer",
    "pode_analisar",
    "recusar_contraparte",
]
