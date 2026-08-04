"""Telas internas da ASAROCK: fila de conferência e análise de um documento."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from operacoes.templatetags.formatacao import cpf_cnpj, data_br

from .servicos import aprovar_documento, fila_de_conferencia, pode_conferir, rejeitar_documento


def _exigir_conferente(usuario):
    if not pode_conferir(usuario):
        raise PermissionDenied


@login_required
def fila(request):
    _exigir_conferente(request.user)
    documentos = fila_de_conferencia()
    return render(request, "analise/fila.html", {"documentos": documentos})


@login_required
def conferir(request, documento_id: int):
    """Compara o que o Clube declarou com o que o documento diz (AGENTS.md §4.6)."""
    _exigir_conferente(request.user)

    documento = get_object_or_404(
        DocumentoCadastral.objects.select_related("contraparte", "tipo", "subtipo"),
        pk=documento_id,
    )
    contraparte = documento.contraparte
    solicitacao = contraparte.solicitacoes.order_by("-data_criacao").first()

    # Enquanto a IA não entra, o confronto é visual: os dados declarados ficam
    # lado a lado com o documento, para a pessoa comparar. Por isso vão
    # formatados como aparecem no documento: "58974790890" ao lado de
    # "589.747.908-90" atrasa a leitura sem necessidade (AGENTS.md §8).
    #
    # A data fica de fora quando não existe: `data_br` devolveria o marcador de
    # vazio, e o filtro no fim desta view o deixaria passar como dado declarado.
    nascimento = data_br(contraparte.data_nascimento) if contraparte.data_nascimento else ""

    declarados = [
        ("Nome", contraparte.nome),
        ("CPF/CNPJ", cpf_cnpj(contraparte.documento)),
        ("Data de nascimento", nascimento),
        ("RG", contraparte.rg),
        ("Endereço", contraparte.endereco),
    ]

    return render(
        request,
        "analise/conferir.html",
        {
            "documento": documento,
            "contraparte": contraparte,
            "solicitacao": solicitacao,
            "declarados": [(rotulo, valor) for rotulo, valor in declarados if valor],
            "arquivos": documento.arquivos.all(),
        },
    )


@login_required
def decidir(request, documento_id: int):
    _exigir_conferente(request.user)

    if request.method != "POST":
        return redirect("analise:conferir", documento_id=documento_id)

    documento = get_object_or_404(DocumentoCadastral, pk=documento_id)
    aprovar = request.POST.get("acao") == "aprovar"
    texto = request.POST.get("observacao", "").strip()

    if aprovar:
        aprovar_documento(documento, usuario=request.user, observacao=texto)
        messages.success(request, f"{documento.rotulo} aprovado.")
    else:
        try:
            rejeitar_documento(documento, usuario=request.user, motivo=texto)
        except ValueError as erro:
            messages.error(request, str(erro))
            return redirect("analise:conferir", documento_id=documento_id)
        messages.success(request, f"{documento.rotulo} rejeitado. O Clube foi notificado na tela.")

    return redirect("analise:fila")


@login_required
def baixar_arquivo(request, arquivo_id: int):
    """Mesma proteção da tela do Clube: permissão + auditoria (AGENTS.md §5.4)."""
    _exigir_conferente(request.user)

    arquivo = get_object_or_404(ArquivoDocumento.objects.select_related("documento"), pk=arquivo_id)
    registrar(
        acao=Acao.DOWNLOAD,
        descricao=f"Arquivo #{arquivo.pk} de {arquivo.documento.rotulo} baixado na conferência",
        objeto=arquivo.documento,
        usuario=request.user,
    )

    if settings.ARMAZENAMENTO == "s3":
        return redirect(arquivo.arquivo.url)

    return FileResponse(
        arquivo.arquivo.open("rb"),
        filename=arquivo.nome_original or Path(arquivo.arquivo.name).name,
    )
