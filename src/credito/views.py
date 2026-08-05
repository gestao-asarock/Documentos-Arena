"""
Telas de risco e crédito.

A análise é do **perfil**, não do contrato (AGENTS.md D30): acontece uma vez, na
esteira de validação da contraparte.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import Habilitacao

from .forms import ParecerCreditoForm, RelatorioCreditoForm
from .models import RelatorioCredito
from .servicos import (
    ParecerIncompleto,
    concluir_parecer_do_perfil,
    fila_de_perfis,
    obter_ou_criar_parecer_do_perfil,
    pode_analisar,
    recusar_perfil,
)


def _exigir_analista(usuario):
    if not pode_analisar(usuario):
        raise PermissionDenied


@login_required
def fila(request):
    _exigir_analista(request.user)
    return render(request, "credito/fila.html", {"perfis": fila_de_perfis()})


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
            "form_relatorio": RelatorioCreditoForm(),
            "parecer_compliance": getattr(habilitacao, "parecer_compliance", None),
        },
    )


@login_required
def anexar_relatorio(request, habilitacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    registro = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=request.user)

    form = RelatorioCreditoForm(request.POST, request.FILES)
    if form.is_valid():
        arquivos = form.cleaned_data["arquivos"]
        descricao = form.cleaned_data["descricao"]
        RelatorioCredito.objects.bulk_create(
            [
                RelatorioCredito(
                    parecer=registro,
                    arquivo=arquivo,
                    nome_original=arquivo.name[:255],
                    descricao=descricao,
                    enviada_por=request.user,
                )
                for arquivo in arquivos
            ]
        )
        messages.success(
            request,
            f"{len(arquivos)} relatório{'s' if len(arquivos) != 1 else ''} anexado"
            f"{'s' if len(arquivos) != 1 else ''}.",
        )
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)

    return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)


@login_required
def remover_relatorio(request, habilitacao_id: int, relatorio_id: int):
    """Tira um relatório anexado por engano, antes de o parecer fechar.

    Depois de concluído não se mexe: aquele arquivo é o lastro do veredito que
    validou o perfil (AGENTS.md §6, D50).
    """
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    registro = obter_ou_criar_parecer_do_perfil(habilitacao, usuario=request.user)

    if registro.esta_concluido:
        messages.error(
            request,
            "O parecer já foi concluído: o relatório que sustentou o veredito não sai.",
        )
        return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)

    relatorio = get_object_or_404(RelatorioCredito, pk=relatorio_id, parecer=registro)
    nome = relatorio.nome_original or "relatório"

    # Some do storage também: relatório de crédito não fica órfão em disco.
    relatorio.arquivo.delete(save=False)
    relatorio.delete()

    registrar(
        acao=Acao.EXCLUSAO_DOCUMENTO,
        descricao=f"Relatório de crédito removido da contraparte #{habilitacao.contraparte_id}",
        objeto=habilitacao,
        usuario=request.user,
    )

    messages.success(request, f"{nome} removido.")
    return redirect("credito:parecer_perfil", habilitacao_id=habilitacao_id)


@login_required
def recusar(request, habilitacao_id: int):
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
