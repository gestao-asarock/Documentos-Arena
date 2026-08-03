"""Ponto único de gravação da trilha de auditoria."""

from django.db import models

from .models import Acao, EventoAuditoria


def registrar(
    *,
    acao: str,
    descricao: str,
    objeto: models.Model | None = None,
    usuario=None,
    endereco_ip: str | None = None,
) -> EventoAuditoria:
    """Grava um evento de auditoria.

    `descricao` é texto curto e legível, sem dado sensível: identifique o objeto,
    não o conteúdo dele (AGENTS.md §6).
    """
    return EventoAuditoria.objects.create(
        acao=acao,
        descricao=descricao[:255],
        objeto=objeto,
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        endereco_ip=endereco_ip,
    )


__all__ = ["Acao", "EventoAuditoria", "registrar"]
