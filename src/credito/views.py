"""Telas de risco e crédito — por contrato, porque dependem do valor (AGENTS.md D30)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from contrapartes.models import Habilitacao
from operacoes.models import Operacao

from .forms import EvidenciaCreditoForm, ParecerCreditoForm
from .servicos import (
    ParecerIncompleto,
    concluir_parecer,
    concluir_parecer_do_perfil,
    fila_de_credito,
    fila_de_perfis,
    obter_ou_criar_parecer,
    obter_ou_criar_parecer_do_perfil,
    pode_analisar,
    recusar_operacao,
    recusar_perfil,
)


def _exigir_analista(usuario):
    if not pode_analisar(usuario):
        raise PermissionDenied


@login_required
def fila(request):
    _exigir_analista(request.user)
    return render(
        request,
        "credito/fila.html",
        {"perfis": fila_de_perfis(), "operacoes": fila_de_credito()},
    )


@login_required
def parecer_perfil(request, habilitacao_id: int):
    """Análise de crédito da pessoa — sem valor de referência (AGENTS.md D30)."""
    _exigir_analista(request.user)

    habilitacao = get_object_or_404(
        Habilitacao.objects.select_related("contraparte"), pk=habilitacao_id
    )
    registro = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=request.user)

    if request.method == "POST" and not registro.esta_concluido:
        form = ParecerCreditoForm(request.POST, instance=registro)
        if form.is_valid():
            form.save()

            if request.POST.get("acao") == "concluir":
                try:
                    concluir_parecer_do_perfil(registro, habilitacao, usuario=request.user)
                except ParecerIncompleto as erro:
                    messages.error(request, str(erro))
                else:
                    messages.success(
                        request,
                        f"Crédito concluído: {registro.get_veredito_display()}. Perfil validado.",
                    )
                    return redirect("credito:fila")
            else:
                messages.success(request, "Parecer salvo.")
            return redirect("credito:parecer_perfil", habilitacao_id=habilitacao.pk)
    else:
        form = ParecerCreditoForm(instance=registro)

    return render(
        request,
        "credito/parecer_perfil.html",
        {
            "habilitacao": habilitacao,
            "contraparte": habilitacao.contraparte,
            "parecer": registro,
            "form": form,
            "form_evidencia": EvidenciaCreditoForm(),
            "parecer_compliance": getattr(habilitacao, "parecer_compliance", None),
        },
    )


@login_required
def recusar_perfil_view(request, habilitacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    try:
        recusar_perfil(habilitacao, usuario=request.user, motivo=request.POST.get("motivo", ""))
    except ParecerIncompleto as erro:
        messages.error(request, str(erro))
        return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)

    messages.success(request, "Perfil recusado na análise de crédito.")
    return redirect("credito:fila")


@login_required
def parecer(request, operacao_id: int):
    _exigir_analista(request.user)

    operacao = get_object_or_404(
        Operacao.objects.select_related("contraparte", "regra", "tipo_operacao"), pk=operacao_id
    )
    registro = obter_ou_criar_parecer(operacao, usuario=request.user)
    habilitacao = operacao.contraparte.habilitacao_vigente

    if request.method == "POST" and not registro.esta_concluido:
        form = ParecerCreditoForm(request.POST, instance=registro)
        if form.is_valid():
            form.save()

            if request.POST.get("acao") == "concluir":
                try:
                    concluir_parecer(registro, operacao, usuario=request.user)
                except ParecerIncompleto as erro:
                    messages.error(request, str(erro))
                else:
                    messages.success(
                        request,
                        f"Análise de crédito concluída: {registro.get_veredito_display()}.",
                    )
                    return redirect("credito:fila")
            else:
                messages.success(request, "Parecer salvo.")
            return redirect("credito:parecer", operacao_id=operacao.pk)
    else:
        form = ParecerCreditoForm(instance=registro)

    return render(
        request,
        "credito/parecer.html",
        {
            "operacao": operacao,
            "contraparte": operacao.contraparte,
            "parecer": registro,
            "form": form,
            "form_evidencia": EvidenciaCreditoForm(),
            "parecer_compliance": getattr(habilitacao, "parecer_compliance", None),
        },
    )


@login_required
def anexar_evidencia(request, operacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("credito:parecer", operacao_id=operacao_id)

    operacao = get_object_or_404(Operacao, pk=operacao_id)
    registro = obter_ou_criar_parecer(operacao, usuario=request.user)

    form = EvidenciaCreditoForm(request.POST, request.FILES)
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

    return redirect("credito:parecer", operacao_id=operacao_id)


@login_required
def recusar(request, operacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("credito:parecer", operacao_id=operacao_id)

    operacao = get_object_or_404(Operacao, pk=operacao_id)
    try:
        recusar_operacao(operacao, usuario=request.user, motivo=request.POST.get("motivo", ""))
    except ParecerIncompleto as erro:
        messages.error(request, str(erro))
        return redirect("credito:parecer", operacao_id=operacao_id)

    messages.success(request, "Contrato reprovado na análise de crédito.")
    return redirect("credito:fila")
