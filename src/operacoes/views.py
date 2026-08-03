"""
Views de operação.

View fina: recebe request, chama serviço, devolve resposta (AGENTS.md §8).
Toda listagem passa por `operacoes_visiveis_para` — nunca consulte `Operacao`
diretamente numa view, ou o filtro por papel se perde.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import ArquivoDocumento, DocumentoCadastral

from .conferencia import campos_do_contrato
from .estados import Etapa, TransicaoInvalida
from .forms import (
    DecisaoEtapaForm,
    EnvioDocumentoContratoForm,
    OperacaoForm,
    VincularDocumentosForm,
)
from .models import EtapaAprovacao, Operacao
from .permissoes import pode_cancelar, pode_criar_operacao, pode_decidir
from .servicos import (
    ContraparteNaoHabilitada,
    EnquadramentoAmbiguo,
    EnquadramentoNaoEncontrado,
    avancar,
    decidir_etapa,
    enquadrar,
    operacoes_visiveis_para,
)


@login_required
def lista(request):
    operacoes = operacoes_visiveis_para(request.user).prefetch_related("etapas")
    return render(
        request,
        "operacoes/lista.html",
        {"operacoes": operacoes, "pode_criar": pode_criar_operacao(request.user)},
    )


@login_required
def detalhe(request, pk: int):
    # Filtra pelo queryset permitido, não por Operacao.objects: assim trocar o ID
    # na URL devolve 404 em vez de vazar dado de outra operação (AGENTS.md §6).
    operacao = get_object_or_404(
        operacoes_visiveis_para(request.user).prefetch_related("etapas"), pk=pk
    )
    etapa_atual = operacao.etapa_atual
    form_envio = EnvioDocumentoContratoForm(operacao=operacao)

    # A revisão jurídica do piloto é conferência de campos: o Termo de Adesão
    # precisa repetir o que foi registrado aqui (AGENTS.md §4.9).
    na_revisao_juridica = bool(etapa_atual) and etapa_atual.etapa == Etapa.JURIDICO

    return render(
        request,
        "operacoes/detalhe.html",
        {
            "operacao": operacao,
            "etapas": operacao.etapas.all(),
            "etapa_atual": etapa_atual,
            # Documentação incompleta trava todas as etapas: o fluxo é linear.
            "documentacao_completa": operacao.documentacao_completa,
            "pode_decidir": (
                bool(etapa_atual)
                and operacao.documentacao_completa
                and pode_decidir(request.user, etapa_atual)
            ),
            "pode_cancelar": operacao.pode_ser_cancelada and pode_cancelar(request.user, operacao),
            "form_decisao": DecisaoEtapaForm(),
            "conferencia": campos_do_contrato(operacao) if na_revisao_juridica else None,
            "documentos_exigidos": operacao.documentos_exigidos(),
            "documentos_pendentes": operacao.documentos_pendentes(),
            "documentos_vinculados": operacao.documentos.select_related("tipo", "subtipo"),
            "form_documentos": VincularDocumentosForm(operacao=operacao),
            "form_envio": form_envio,
            "config_campos": {
                "subtipo": getattr(form_envio, "tipos_com_subtipo", []),
                "emissao": getattr(form_envio, "tipos_com_emissao", []),
            },
        },
    )


@login_required
def nova(request):
    """Cria o contrato para uma contraparte de perfil já validado (AGENTS.md D29)."""
    if not pode_criar_operacao(request.user):
        raise PermissionDenied

    form = OperacaoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        operacao = Operacao(
            contraparte=dados["contraparte"],
            tipo_operacao=dados["tipo_operacao"],
            descricao=dados["descricao"],
            data_evento=dados["data_evento"],
            horario_evento=dados["horario_evento"],
            valor_total=dados["valor_total"],
            criada_por=request.user,
        )
        operacao.save()

        # O enquadramento define alçadas e documentos; sem ele a operação não anda.
        try:
            enquadrar(operacao, usuario=request.user)
        except ContraparteNaoHabilitada as erro:
            operacao.delete()
            form.add_error("contraparte", str(erro))
        except EnquadramentoNaoEncontrado as erro:
            operacao.delete()
            form.add_error("valor_total", str(erro))
        except EnquadramentoAmbiguo as erro:
            operacao.delete()
            form.add_error(None, str(erro))
        else:
            messages.success(
                request,
                f"Operação #{operacao.pk} criada e enquadrada como “{operacao.regra.criterio}”.",
            )
            return redirect("operacoes:detalhe", pk=operacao.pk)

    return render(
        request,
        "operacoes/nova.html",
        {"form": form, "tem_perfis": form.fields["contraparte"].queryset.exists()},
    )


@login_required
def vincular_documentos(request, pk: int):
    """Escolhe documentos já validados do perfil para atender às exigências."""
    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    if request.method != "POST":
        return redirect("operacoes:detalhe", pk=pk)

    form = VincularDocumentosForm(request.POST, operacao=operacao)
    if form.is_valid():
        operacao.documentos.set(form.documentos_escolhidos())
        avancar(operacao)
        messages.success(request, "Documentos vinculados ao contrato.")

    return redirect("operacoes:detalhe", pk=pk)


@login_required
def enviar_documento(request, pk: int):
    """Envia documento complementar exigido pelo contrato.

    O arquivo fica no perfil da contraparte e já entra na fila de conferência —
    é o mesmo caminho dos documentos base (AGENTS.md §4.6, D29).
    """
    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    if request.method != "POST":
        return redirect("operacoes:detalhe", pk=pk)

    form = EnvioDocumentoContratoForm(request.POST, request.FILES, operacao=operacao)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect("operacoes:detalhe", pk=pk)

    arquivos = form.cleaned_data["arquivos"]
    documento = DocumentoCadastral.objects.create(
        contraparte=operacao.contraparte,
        tipo=form.cleaned_data["tipo"],
        subtipo=form.cleaned_data.get("subtipo"),
        data_emissao=form.cleaned_data["data_emissao"],
        enviado_por=request.user,
    )
    ArquivoDocumento.objects.bulk_create(
        [
            ArquivoDocumento(
                documento=documento,
                arquivo=arquivo,
                nome_original=arquivo.name[:255],
                ordem=ordem,
            )
            for ordem, arquivo in enumerate(arquivos)
        ]
    )
    operacao.documentos.add(documento)

    registrar(
        acao=Acao.ENVIO_DOCUMENTO,
        descricao=(
            f"{documento.rotulo} enviado para o contrato #{operacao.pk} "
            f"e guardado no perfil da contraparte #{operacao.contraparte_id}"
        ),
        objeto=documento,
        usuario=request.user,
    )

    messages.success(request, f"{documento.rotulo} enviado. Aguardando conferência.")
    return redirect("operacoes:detalhe", pk=pk)


@login_required
def cancelar(request, pk: int):
    """Encerra o contrato sem apagá-lo: o registro fica, com motivo e autor."""
    if request.method != "POST":
        return redirect("operacoes:detalhe", pk=pk)

    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    if not pode_cancelar(request.user, operacao):
        raise PermissionDenied

    try:
        operacao.cancelar(request.POST.get("motivo", ""), usuario=request.user)
    except (TransicaoInvalida, ValidationError) as erro:
        messages.error(request, _mensagem(erro))
        return redirect("operacoes:detalhe", pk=pk)

    operacao.save()
    registrar(
        acao=Acao.TRANSICAO_ESTADO,
        descricao=f"Operação #{operacao.pk} cancelada",
        objeto=operacao,
        usuario=request.user,
    )
    messages.success(request, f"Operação #{operacao.pk} cancelada.")
    return redirect("operacoes:detalhe", pk=pk)


def _mensagem(erro) -> str:
    """Texto legível de uma exceção de domínio ou de validação."""
    if isinstance(erro, ValidationError):
        return " ".join(m for lista in erro.message_dict.values() for m in lista)
    return str(erro)


@login_required
def decidir(request, pk: int, etapa_id: int):
    if request.method != "POST":
        return redirect("operacoes:detalhe", pk=pk)

    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    etapa = get_object_or_404(EtapaAprovacao, pk=etapa_id, operacao=operacao)

    if not pode_decidir(request.user, etapa):
        raise PermissionDenied

    form = DecisaoEtapaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Informe o parecer para registrar a decisão.")
        return redirect("operacoes:detalhe", pk=pk)

    aprovada = request.POST.get("acao") == "aprovar"
    try:
        decidir_etapa(
            etapa,
            aprovada=aprovada,
            parecer=form.cleaned_data["parecer"],
            usuario=request.user,
        )
    except (TransicaoInvalida, ValueError) as erro:
        messages.error(request, str(erro))
    else:
        messages.success(
            request,
            f"{etapa.get_etapa_display()} {'aprovada' if aprovada else 'reprovada'}.",
        )

    return redirect("operacoes:detalhe", pk=pk)
