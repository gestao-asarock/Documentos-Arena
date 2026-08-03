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

from .estados import TransicaoInvalida
from .forms import DecisaoEtapaForm, OperacaoForm
from .models import EtapaAprovacao, Operacao
from .permissoes import pode_cancelar, pode_criar_operacao, pode_decidir
from .servicos import (
    ContraparteNaoHabilitada,
    EnquadramentoAmbiguo,
    EnquadramentoNaoEncontrado,
    decidir_etapa,
    enquadrar,
    operacoes_visiveis_para,
    solicitacoes_prontas_para_contrato,
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

    return render(
        request,
        "operacoes/detalhe.html",
        {
            "operacao": operacao,
            "etapas": operacao.etapas.all(),
            "etapa_atual": etapa_atual,
            "pode_decidir": bool(etapa_atual) and pode_decidir(request.user, etapa_atual),
            "pode_cancelar": operacao.pode_ser_cancelada
            and pode_cancelar(request.user, operacao),
            "form_decisao": DecisaoEtapaForm(),
            # O kit exigido depende do valor: PF acima de R$ 4.000,00 comprova renda.
            "pendencias_cadastrais": operacao.contraparte.pendencias_cadastrais(
                operacao.valor_total
            ),
            "documentos_exigidos": operacao.documentos_exigidos(),
        },
    )


@login_required
def nova(request):
    """Cria o contrato a partir de uma solicitação já habilitada (AGENTS.md §4.0).

    Não existe contrato do nada: a Fase 2 nasce da Fase 1.
    """
    if not pode_criar_operacao(request.user):
        raise PermissionDenied

    solicitacoes = solicitacoes_prontas_para_contrato(request.user)
    form = OperacaoForm(request.POST or None, solicitacoes=solicitacoes)

    if request.method == "POST" and form.is_valid():
        solicitacao = form.cleaned_data["solicitacao"]
        operacao = Operacao(
            solicitacao=solicitacao,
            contraparte=solicitacao.contraparte,
            tipo_operacao=solicitacao.tipo_operacao,
            valor_total=solicitacao.valor,
            descricao=form.cleaned_data["descricao"],
            criada_por=request.user,
        )
        operacao.save()

        # O enquadramento define alçadas e documentos; sem ele a operação não anda.
        try:
            enquadrar(operacao, usuario=request.user)
        except ContraparteNaoHabilitada as erro:
            operacao.delete()
            form.add_error("solicitacao", str(erro))
        except EnquadramentoNaoEncontrado as erro:
            operacao.delete()
            form.add_error(None, str(erro))
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
        {"form": form, "tem_solicitacoes": solicitacoes.exists()},
    )


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
