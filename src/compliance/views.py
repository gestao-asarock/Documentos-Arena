"""Telas de due diligence (AGENTS.md §4.7)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from contrapartes.models import Habilitacao

from .forms import EvidenciaForm, ParecerForm
from .servicos import (
    ParecerIncompleto,
    concluir_parecer,
    fila_de_compliance,
    obter_ou_criar_parecer,
    pode_analisar,
    recusar_contraparte,
)


def _exigir_analista(usuario):
    if not pode_analisar(usuario):
        raise PermissionDenied


@login_required
def fila(request):
    _exigir_analista(request.user)
    return render(request, "compliance/fila.html", {"habilitacoes": fila_de_compliance()})


@login_required
def parecer(request, habilitacao_id: int):
    _exigir_analista(request.user)

    habilitacao = get_object_or_404(
        Habilitacao.objects.select_related("contraparte"), pk=habilitacao_id
    )
    registro = obter_ou_criar_parecer(habilitacao, usuario=request.user)
    contraparte = habilitacao.contraparte

    if request.method == "POST" and not registro.esta_concluido:
        form = ParecerForm(request.POST, instance=registro)
        if form.is_valid():
            form.save()

            if request.POST.get("acao") == "concluir":
                try:
                    concluir_parecer(registro, usuario=request.user)
                except ParecerIncompleto as erro:
                    messages.error(request, str(erro))
                else:
                    messages.success(
                        request,
                        f"Due diligence concluída: {registro.get_veredito_display()}.",
                    )
                    return redirect("compliance:fila")
            else:
                messages.success(request, "Parecer salvo.")
            return redirect("compliance:parecer", habilitacao_id=habilitacao.pk)
    else:
        form = ParecerForm(instance=registro)

    return render(
        request,
        "compliance/parecer.html",
        {
            "habilitacao": habilitacao,
            "contraparte": contraparte,
            "parecer": registro,
            "form": form,
            "form_evidencia": EvidenciaForm(),
            "documentos": contraparte.documentos_cadastrais.select_related(
                "tipo", "subtipo"
            ).prefetch_related("arquivos"),
            "solicitacao": contraparte.solicitacoes.order_by("-data_criacao").first(),
        },
    )


@login_required
def anexar_evidencia(request, habilitacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    registro = obter_ou_criar_parecer(habilitacao, usuario=request.user)

    form = EvidenciaForm(request.POST, request.FILES)
    if form.is_valid():
        evidencia = form.save(commit=False)
        evidencia.parecer = registro
        evidencia.nome_original = evidencia.arquivo.name[:255]
        evidencia.enviada_por = request.user
        evidencia.save()
        messages.success(request, "Evidência anexada.")
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)

    return redirect("compliance:parecer", habilitacao_id=habilitacao_id)


@login_required
def recusar(request, habilitacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    try:
        recusar_contraparte(
            habilitacao, usuario=request.user, motivo=request.POST.get("motivo", "")
        )
    except ParecerIncompleto as erro:
        messages.error(request, str(erro))
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    messages.success(request, "Contraparte recusada.")
    return redirect("compliance:fila")
