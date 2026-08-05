"""Telas de due diligence (AGENTS.md §4.7)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import Habilitacao

from .forms import ParecerForm, RelatorioForm
from .models import RelatorioParecer
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
            "form_relatorio": RelatorioForm(),
            "documentos": contraparte.documentos_cadastrais.select_related(
                "tipo", "subtipo"
            ).prefetch_related("arquivos"),
            "solicitacao": contraparte.solicitacoes.order_by("-data_criacao").first(),
        },
    )


@login_required
def anexar_relatorio(request, habilitacao_id: int):
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    registro = obter_ou_criar_parecer(habilitacao, usuario=request.user)

    form = RelatorioForm(request.POST, request.FILES)
    if form.is_valid():
        arquivos = form.cleaned_data["arquivos"]
        descricao = form.cleaned_data["descricao"]
        RelatorioParecer.objects.bulk_create(
            [
                RelatorioParecer(
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

    return redirect("compliance:parecer", habilitacao_id=habilitacao_id)


@login_required
def remover_relatorio(request, habilitacao_id: int, relatorio_id: int):
    """Tira um relatório anexado por engano, antes de o parecer fechar.

    Depois de concluído não se mexe: aquele arquivo é o lastro do veredito que
    já correu para o crédito (AGENTS.md §6, D50).
    """
    _exigir_analista(request.user)

    if request.method != "POST":
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    habilitacao = get_object_or_404(Habilitacao, pk=habilitacao_id)
    registro = obter_ou_criar_parecer(habilitacao, usuario=request.user)

    if registro.esta_concluido:
        messages.error(
            request,
            "O parecer já foi concluído: o relatório que sustentou o veredito não sai.",
        )
        return redirect("compliance:parecer", habilitacao_id=habilitacao_id)

    relatorio = get_object_or_404(RelatorioParecer, pk=relatorio_id, parecer=registro)
    nome = relatorio.nome_original or "relatório"

    # Some do storage também: relatório de due diligence não fica órfão em disco.
    relatorio.arquivo.delete(save=False)
    relatorio.delete()

    registrar(
        acao=Acao.EXCLUSAO_DOCUMENTO,
        descricao=(
            f"Relatório de due diligence removido da contraparte #{habilitacao.contraparte_id}"
        ),
        objeto=habilitacao,
        usuario=request.user,
    )

    messages.success(request, f"{nome} removido.")
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
