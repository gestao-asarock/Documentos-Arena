"""
Telas do Jurídico: a fila e a revisão de um contrato.

A revisão tem tela própria, como a triagem do CRM tem a dela (AGENTS.md D52).
Decidir a etapa de dentro da tela da operação misturava o painel de acompanhamento
com o posto de trabalho de uma área: quem revisa precisa do documento à mão, dos
campos a conferir e do parecer no mesmo lugar, sem o resto em volta.
"""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import ArquivoDocumento
from operacoes.conferencia import campos_do_contrato
from operacoes.estados import Etapa, TransicaoInvalida
from operacoes.models import Operacao
from operacoes.servicos import decidir_etapa

from .servicos import aguardando_documentacao, fila_juridica, pode_revisar


def _exigir_revisor(usuario):
    if not pode_revisar(usuario):
        raise PermissionDenied


@login_required
def fila(request):
    _exigir_revisor(request.user)

    return render(
        request,
        "juridico/fila.html",
        {
            "prontos": fila_juridica(),
            "aguardando": aguardando_documentacao(),
        },
    )


def _etapa_juridica(operacao):
    """A etapa 4 do contrato, se for ela a da vez."""
    etapa = operacao.etapa_atual
    if etapa is None or Etapa(etapa.etapa) != Etapa.JURIDICO:
        return None
    return etapa


@login_required
def revisar(request, operacao_id: int):
    """O contrato, os documentos e os campos a conferir, num lugar só."""
    _exigir_revisor(request.user)

    operacao = get_object_or_404(
        Operacao.objects.select_related("contraparte", "tipo_operacao", "regra"), pk=operacao_id
    )
    etapa = _etapa_juridica(operacao)

    return render(
        request,
        "juridico/revisar.html",
        {
            "operacao": operacao,
            "contraparte": operacao.contraparte,
            "etapa": etapa,
            "etapa_registrada": operacao.etapas.filter(etapa=Etapa.JURIDICO).first(),
            "conferencia": campos_do_contrato(operacao),
            "documentos": operacao.documentos.select_related("tipo", "subtipo").prefetch_related(
                "arquivos"
            ),
            "pode_decidir": etapa is not None and operacao.documentacao_entregue,
        },
    )


@login_required
def decidir(request, operacao_id: int):
    """Aprova ou recusa a revisão jurídica, sempre com parecer (AGENTS.md §5.1)."""
    _exigir_revisor(request.user)

    if request.method != "POST":
        return redirect("juridico:revisar", operacao_id=operacao_id)

    operacao = get_object_or_404(Operacao, pk=operacao_id)
    etapa = _etapa_juridica(operacao)
    if etapa is None:
        messages.error(request, "Este contrato não está na revisão jurídica.")
        return redirect("juridico:revisar", operacao_id=operacao_id)

    aprovada = request.POST.get("acao") == "aprovar"
    parecer = request.POST.get("parecer", "")

    # Aprovar afirma que o termo confere campo a campo: o formulário precisa
    # mostrar que cada campo foi de fato olhado. Reprovar não exige nada disso —
    # reprova-se justamente porque algum campo não confere (D53).
    if aprovada:
        marcados = set(request.POST.getlist("confere"))
        faltam = [c.rotulo for c in campos_do_contrato(operacao) if c.chave not in marcados]
        if faltam:
            messages.error(
                request,
                f"Confira todos os campos antes de aprovar. Falta marcar: {', '.join(faltam)}.",
            )
            return redirect("juridico:revisar", operacao_id=operacao_id)

    try:
        decidir_etapa(etapa, aprovada=aprovada, parecer=parecer, usuario=request.user)
    except (TransicaoInvalida, ValueError) as erro:
        messages.error(request, str(erro))
        return redirect("juridico:revisar", operacao_id=operacao_id)

    if aprovada:
        messages.success(
            request,
            f"Revisão jurídica do contrato #{operacao.pk} aprovada. "
            "Os documentos conferidos foram aprovados junto.",
        )
    else:
        messages.success(request, f"Contrato #{operacao.pk} reprovado na revisão jurídica.")

    return redirect("juridico:fila")


@login_required
def baixar_arquivo(request, operacao_id: int, arquivo_id: int):
    """Entrega o arquivo do contrato ao revisor, com registro na auditoria.

    Nunca exponha a pasta de uploads nem a URL do bucket (AGENTS.md §5.4, §6).
    O arquivo precisa ser deste contrato: sem isso, trocar o id na URL leria o
    documento de outra contraparte.
    """
    _exigir_revisor(request.user)

    operacao = get_object_or_404(Operacao, pk=operacao_id)
    arquivo = get_object_or_404(
        ArquivoDocumento.objects.select_related("documento").filter(documento__operacoes=operacao),
        pk=arquivo_id,
    )

    registrar(
        acao=Acao.DOWNLOAD,
        descricao=(
            f"Arquivo #{arquivo.pk} de {arquivo.documento.rotulo} baixado na revisão jurídica "
            f"do contrato #{operacao.pk}"
        ),
        objeto=arquivo.documento,
        usuario=request.user,
    )

    if settings.ARMAZENAMENTO == "s3":
        return redirect(arquivo.arquivo.url)

    return FileResponse(
        arquivo.arquivo.open("rb"),
        filename=arquivo.nome_original or Path(arquivo.arquivo.name).name,
    )
