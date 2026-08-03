"""Serviços de risco e crédito (AGENTS.md §4.8)."""

from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar
from contas.models import Papel
from operacoes.estados import Etapa, StatusOperacao
from operacoes.models import Operacao
from operacoes.servicos import decidir_etapa

from .models import ParecerCredito, StatusParecer

#: O time de Risco não é usuário no MVP: CRM ou Compliance registra o parecer
#: produzido por ele (AGENTS.md D9).
PAPEIS_DE_CREDITO = {Papel.CRM, Papel.COMPLIANCE, Papel.ADMINISTRADOR}


class ParecerIncompleto(Exception):
    """Falta veredito ou justificativa para concluir."""


def pode_analisar(usuario) -> bool:
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=PAPEIS_DE_CREDITO).exists()


def fila_de_credito():
    """Contratos aguardando análise de crédito.

    Crédito é por contrato porque depende do valor (AGENTS.md D30).
    """
    return (
        Operacao.objects.filter(status=StatusOperacao.EM_CREDITO)
        .select_related("contraparte", "tipo_operacao", "regra")
        .order_by("data_criacao")
    )


def obter_ou_criar_parecer(operacao: Operacao, *, usuario=None) -> ParecerCredito:
    """Parecer do par contraparte + enquadramento deste contrato."""
    parecer, _ = ParecerCredito.objects.get_or_create(
        contraparte=operacao.contraparte,
        regra=operacao.regra,
        defaults={"analista": usuario, "operacao": operacao},
    )
    return parecer


@transaction.atomic
def concluir_parecer(parecer: ParecerCredito, operacao: Operacao, *, usuario) -> Operacao:
    """Fecha a análise de crédito e libera o contrato para a revisão jurídica.

    O parecer fica guardado no par contraparte + enquadramento: outro contrato
    do mesmo tipo e faixa o reaproveita (AGENTS.md D30).
    """
    if not parecer.veredito:
        raise ParecerIncompleto("Escolha o veredito de risco para concluir.")
    if not parecer.justificativa.strip():
        raise ParecerIncompleto("Justifique o veredito para concluir.")

    parecer.status = StatusParecer.CONCLUIDO
    parecer.analista = parecer.analista or usuario
    parecer.data_conclusao = timezone.now()
    parecer.save()

    etapa = operacao.etapas.filter(etapa=Etapa.RISCO_CREDITO).first()
    if etapa is not None and not etapa.esta_decidida:
        decidir_etapa(
            etapa,
            aprovada=True,
            parecer=f"{parecer.get_veredito_display()}: {parecer.justificativa}",
            usuario=usuario,
        )

    registrar(
        acao=Acao.APROVACAO,
        descricao=(
            f"Análise de crédito concluída para a contraparte #{operacao.contraparte_id} "
            f"no enquadramento '{parecer.regra.criterio}': {parecer.get_veredito_display()}"
        ),
        objeto=operacao,
        usuario=usuario,
    )
    operacao.refresh_from_db()
    return operacao


@transaction.atomic
def recusar_operacao(operacao: Operacao, *, usuario, motivo: str) -> Operacao:
    """Barra o contrato no crédito. O perfil da contraparte segue válido."""
    if not motivo.strip():
        raise ParecerIncompleto("Informe o motivo da recusa.")

    etapa = operacao.etapas.filter(etapa=Etapa.RISCO_CREDITO).first()
    if etapa is not None and not etapa.esta_decidida:
        decidir_etapa(etapa, aprovada=False, parecer=motivo, usuario=usuario)
    else:
        operacao.reprovar(motivo)
        operacao.save()

    registrar(
        acao=Acao.REPROVACAO,
        descricao=f"Operação #{operacao.pk} reprovada na análise de crédito",
        objeto=operacao,
        usuario=usuario,
    )
    operacao.refresh_from_db()
    return operacao
