"""Tela do Jurídico: os contratos que dependem dele."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .servicos import aguardando_documentacao, fila_juridica, pode_revisar


@login_required
def fila(request):
    if not pode_revisar(request.user):
        raise PermissionDenied

    return render(
        request,
        "juridico/fila.html",
        {
            "prontos": fila_juridica(),
            "aguardando": aguardando_documentacao(),
        },
    )
