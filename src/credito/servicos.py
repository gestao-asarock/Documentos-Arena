"""
Serviços de risco e crédito (AGENTS.md §4.8, D30).

**Existe uma análise de crédito, e ela acontece na esteira do perfil.** O
contrato não a refaz: se for preciso reavaliar — porque o valor pulou de faixa,
por exemplo —, isso é uma revalidação do perfil, não uma etapa do contrato.
"""

from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar
from contas.models import Papel
from contrapartes.models import Habilitacao, StatusHabilitacao

from .models import ParecerCredito, StatusParecer

#: O time de Risco não é usuário no MVP: o **CRM** registra o parecer produzido
#: por ele, a partir da consulta ao Serasa (AGENTS.md D9, D34). Compliance ficou
#: de fora: due diligence e crédito são análises distintas, de áreas distintas.
PAPEIS_DE_CREDITO = {Papel.CRM, Papel.ADMINISTRADOR}


class ParecerIncompleto(Exception):
    """Falta veredito ou justificativa para concluir."""


def pode_analisar(usuario) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=PAPEIS_DE_CREDITO).exists()


def fila_de_perfis():
    """Perfis aprovados no compliance, aguardando a análise de crédito da pessoa."""
    return (
        Habilitacao.objects.filter(status=StatusHabilitacao.EM_CREDITO)
        .select_related("contraparte")
        .order_by("data_criacao")
    )


def obter_ou_criar_parecer_do_perfil(habilitacao: Habilitacao, *, usuario=None) -> ParecerCredito:
    """Parecer da pessoa, sem enquadramento: score, restrições, protestos."""
    parecer, _ = ParecerCredito.objects.get_or_create(
        contraparte=habilitacao.contraparte,
        regra=None,
        defaults={"analista": usuario},
    )
    return parecer


@transaction.atomic
def concluir_parecer_do_perfil(parecer: ParecerCredito, habilitacao: Habilitacao, *, usuario):
    """Fecha o crédito do perfil e valida a contraparte.

    Última etapa da esteira do perfil: daqui em diante ela pode contratar.
    """
    if not parecer.veredito:
        raise ParecerIncompleto("Escolha o veredito de risco para concluir.")
    if not parecer.justificativa.strip():
        raise ParecerIncompleto("Justifique o veredito para concluir.")

    parecer.status = StatusParecer.CONCLUIDO
    parecer.analista = parecer.analista or usuario
    parecer.data_conclusao = timezone.now()
    parecer.save()

    habilitacao.status = StatusHabilitacao.HABILITADA
    habilitacao.data_conclusao = timezone.now()
    habilitacao.save()
    habilitacao.solicitacoes.update(status="pronta_para_contrato")

    registrar(
        acao=Acao.APROVACAO,
        descricao=(
            f"Crédito do perfil concluído para a contraparte #{habilitacao.contraparte_id}: "
            f"{parecer.get_veredito_display()}. Perfil validado."
        ),
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao


@transaction.atomic
def recusar_perfil(habilitacao: Habilitacao, *, usuario, motivo: str) -> Habilitacao:
    """Barra a contraparte no crédito. Estado terminal do perfil."""
    if not motivo.strip():
        raise ParecerIncompleto("Informe o motivo da recusa.")

    habilitacao.status = StatusHabilitacao.RECUSADA
    habilitacao.motivo_recusa = motivo
    habilitacao.save()

    registrar(
        acao=Acao.REPROVACAO,
        descricao=f"Perfil da contraparte #{habilitacao.contraparte_id} recusado no crédito",
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao
