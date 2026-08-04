"""Views da Fase 1: solicitação, kit cadastral e envio de documentos."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from auditoria.servicos import Acao, registrar
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from contrapartes.servicos import (
    alterar_dados_cadastrais,
    avancar_habilitacao,
    comparar_cadastro,
    efeitos_da_revalidacao,
    reiniciar_validacao,
)
from documentos.models import StatusDocumento
from integracoes.enderecos import buscar_por_cep
from operacoes.permissoes import eh_dono_ou_interno, pode_cancelar, pode_criar_operacao

from . import fluxo as fluxo_do_processo
from .forms import EdicaoPerfilForm, EnvioDocumentoForm, SolicitacaoForm
from .models import Solicitacao
from .servicos import abrir_habilitacao, obter_ou_criar_contraparte, solicitacoes_visiveis_para


@login_required
def lista(request):
    solicitacoes = solicitacoes_visiveis_para(request.user)
    return render(
        request,
        "solicitacoes/lista.html",
        {"solicitacoes": solicitacoes, "pode_criar": pode_criar_operacao(request.user)},
    )


@login_required
def nova(request):
    if not pode_criar_operacao(request.user):
        raise PermissionDenied

    form = SolicitacaoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        contraparte, _ = obter_ou_criar_contraparte(
            documento=form.cleaned_data["documento"], dados=form.dados_da_contraparte
        )
        solicitacao = Solicitacao.objects.create(contraparte=contraparte, criada_por=request.user)
        registrar(
            acao=Acao.CRIACAO,
            descricao=f"Perfil #{solicitacao.pk} cadastrado",
            objeto=solicitacao,
            usuario=request.user,
        )
        abrir_habilitacao(solicitacao, usuario=request.user)

        messages.success(request, f"Perfil #{solicitacao.pk} cadastrado.")
        return redirect("solicitacoes:detalhe", pk=solicitacao.pk)

    return render(request, "solicitacoes/nova.html", {"form": form})


@login_required
def editar(request, pk: int):
    """Corrige os dados cadastrais do perfil (AGENTS.md D47).

    Alterar o que os documentos comprovam devolve o perfil ao começo da
    esteira: o que foi conferido antes atestava os dados antigos. A tela avisa
    disso antes de gravar, e a confirmação é explícita.
    """
    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    if not eh_dono_ou_interno(request.user, solicitacao):
        raise PermissionDenied
    if not solicitacao.pode_ser_editada:
        messages.error(
            request,
            "Perfil validado ou cancelado não pode ter os dados alterados."
            if not solicitacao.esta_cancelada
            else "Perfil cancelado não pode ter os dados alterados.",
        )
        return redirect("solicitacoes:detalhe", pk=pk)

    contraparte = solicitacao.contraparte
    form = EdicaoPerfilForm(
        request.POST or None, initial=EdicaoPerfilForm.dados_iniciais(contraparte)
    )

    # "Voltar e corrigir" na confirmação: devolve o formulário com o que foi
    # digitado, em vez de recarregar o que está no banco.
    if request.method == "POST" and request.POST.get("voltar"):
        return render(
            request,
            "solicitacoes/editar.html",
            {
                "solicitacao": solicitacao,
                "contraparte": contraparte,
                "form": form,
                "tem_analise_feita": contraparte.documentos_cadastrais.exists(),
            },
        )

    if request.method == "POST" and form.is_valid():
        previa = comparar_cadastro(contraparte, form.dados_da_contraparte)

        if not previa:
            messages.info(request, "Nada foi alterado.")
            return redirect("solicitacoes:detalhe", pk=pk)

        # Alteração que derruba a conferência passa por uma confirmação própria,
        # que mostra o que muda e o que isso desfaz. Só depois dela se grava: o
        # efeito é grande demais para caber num aviso lido depois do fato.
        veio_da_confirmacao = bool(request.POST.get("confirmado"))
        if previa.exige_revalidacao and not (veio_da_confirmacao and request.POST.get("ciente")):
            return render(
                request,
                "solicitacoes/editar_confirmar.html",
                {
                    "solicitacao": solicitacao,
                    "contraparte": contraparte,
                    "form": form,
                    "previa": previa,
                    "efeitos": efeitos_da_revalidacao(solicitacao.habilitacao),
                    # Só é falta de ciência se a pessoa já esteve nesta tela e
                    # mandou sem marcar; da primeira vez, é só a tela abrindo.
                    "faltou_ciencia": veio_da_confirmacao,
                },
            )

        alteracao = alterar_dados_cadastrais(
            contraparte, form.dados_da_contraparte, usuario=request.user
        )

        if alteracao.exige_revalidacao:
            reiniciar_validacao(
                solicitacao.habilitacao,
                usuario=request.user,
                motivo=f"cadastro alterado: {alteracao.resumo}",
            )
            messages.warning(
                request,
                f"Dados alterados ({alteracao.resumo}). A validação recomeçou: "
                "os documentos voltaram para a triagem e as análises serão refeitas.",
            )
        else:
            messages.success(request, f"Dados alterados ({alteracao.resumo}).")

        return redirect("solicitacoes:detalhe", pk=pk)

    return render(
        request,
        "solicitacoes/editar.html",
        {
            "solicitacao": solicitacao,
            "contraparte": contraparte,
            "form": form,
            # A tela só avisa que a validação recomeça se houver o que recomeçar.
            "tem_analise_feita": contraparte.documentos_cadastrais.exists(),
        },
    )


@login_required
def detalhe(request, pk: int):
    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)

    # Reaplica a regra antes de mostrar, como o contrato já faz: perfil parado
    # numa etapa que o dossiê não sustenta mais se corrige ao ser aberto, em vez
    # de exigir intervenção no banco.
    if not solicitacao.esta_cancelada:
        avancar_habilitacao(solicitacao.habilitacao, usuario=request.user)

    pendencias = solicitacao.pendencias_cadastrais()
    form_envio = EnvioDocumentoForm(tipos_pendentes=pendencias)

    return render(
        request,
        "solicitacoes/detalhe.html",
        {
            "solicitacao": solicitacao,
            "contraparte": solicitacao.contraparte,
            "habilitacao": solicitacao.habilitacao,
            "fluxo": fluxo_do_processo.montar(solicitacao),
            "pode_cancelar": solicitacao.pode_ser_cancelada
            and pode_cancelar(request.user, solicitacao),
            "pode_editar": solicitacao.pode_ser_editada
            and eh_dono_ou_interno(request.user, solicitacao),
            "exigencias": solicitacao.exigencias_cadastrais(),
            "pendencias": pendencias,
            "kit": solicitacao.contraparte.situacao_do_kit(),
            "documentos": solicitacao.contraparte.documentos_cadastrais.select_related(
                "tipo", "subtipo"
            ).prefetch_related("arquivos"),
            "form_envio": form_envio,
            # Quais campos do formulário de envio se aplicam a cada tipo.
            "config_campos": {
                "subtipo": form_envio.tipos_com_subtipo,
                "emissao": form_envio.tipos_com_emissao,
            },
        },
    )


@login_required
def enviar_documento(request, pk: int):
    if request.method != "POST":
        return redirect("solicitacoes:detalhe", pk=pk)

    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    form = EnvioDocumentoForm(
        request.POST, request.FILES, tipos_pendentes=solicitacao.pendencias_cadastrais()
    )

    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect("solicitacoes:detalhe", pk=pk)

    arquivos = form.cleaned_data["arquivos"]
    documento = DocumentoCadastral.objects.create(
        contraparte=solicitacao.contraparte,
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

    # O identificador vai para a auditoria; o conteúdo, nunca (AGENTS.md §6).
    registrar(
        acao=Acao.ENVIO_DOCUMENTO,
        descricao=(
            f"{documento.rotulo} enviado ({len(arquivos)} arquivo"
            f"{'s' if len(arquivos) != 1 else ''}) "
            f"para a contraparte #{solicitacao.contraparte_id}"
        ),
        objeto=documento,
        usuario=request.user,
    )

    # Documento fora do prazo entra assim mesmo — barrar o envio deixaria o
    # Clube sem caminho —, mas ninguém pode descobrir isso só na triagem
    # (AGENTS.md D48).
    if documento.esta_vencido:
        messages.warning(
            request,
            f"{documento.rotulo} enviado, mas está fora do prazo: emitido há "
            f"{documento.dias_desde_emissao} dias, e vale {documento.tipo.dias_validade}. "
            "A triagem provavelmente vai pedir um mais recente.",
        )
    else:
        messages.success(request, f"{documento.rotulo} enviado. Aguardando análise.")
    return redirect("solicitacoes:detalhe", pk=pk)


@login_required
def cancelar(request, pk: int):
    """Encerra a solicitação sem apagá-la (AGENTS.md §6)."""
    if request.method != "POST":
        return redirect("solicitacoes:detalhe", pk=pk)

    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    if not pode_cancelar(request.user, solicitacao):
        raise PermissionDenied

    try:
        solicitacao.cancelar(request.POST.get("motivo", ""), usuario=request.user)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
        return redirect("solicitacoes:detalhe", pk=pk)

    solicitacao.save()
    registrar(
        acao=Acao.TRANSICAO_ESTADO,
        descricao=f"Solicitação #{solicitacao.pk} cancelada",
        objeto=solicitacao,
        usuario=request.user,
    )
    messages.success(request, f"Solicitação #{solicitacao.pk} cancelada.")
    return redirect("solicitacoes:detalhe", pk=pk)


@login_required
def excluir_documento(request, pk: int, documento_id: int):
    """Remove um documento enviado por engano.

    Documento **aprovado** não é removido pela tela: ele já sustentou uma
    decisão, e apagá-lo desfaria a base do parecer (AGENTS.md §6). O registro
    da exclusão fica na auditoria, que nunca é apagada.
    """
    if request.method != "POST":
        return redirect("solicitacoes:detalhe", pk=pk)

    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    # Ver é do time; apagar é de quem enviou (ou da ASAROCK) — D35.
    if not eh_dono_ou_interno(request.user, solicitacao):
        raise PermissionDenied

    documento = get_object_or_404(
        DocumentoCadastral, pk=documento_id, contraparte=solicitacao.contraparte
    )

    if documento.status == StatusDocumento.APROVADO:
        messages.error(
            request,
            "Documento aprovado não pode ser excluído aqui. Fale com a ASAROCK.",
        )
        return redirect("solicitacoes:detalhe", pk=pk)

    rotulo = documento.rotulo
    quantidade = documento.arquivos.count()

    # Apaga também os arquivos no storage — não deixe documento de identidade
    # órfão em disco ou no bucket.
    for arquivo in documento.arquivos.all():
        arquivo.arquivo.delete(save=False)
    documento.delete()

    registrar(
        acao=Acao.EXCLUSAO_DOCUMENTO,
        descricao=(
            f"{rotulo} excluído ({quantidade} arquivo{'s' if quantidade != 1 else ''}) "
            f"da contraparte #{solicitacao.contraparte_id}"
        ),
        objeto=solicitacao,
        usuario=request.user,
    )

    messages.success(request, f"{rotulo} excluído.")
    return redirect("solicitacoes:detalhe", pk=pk)


@login_required
def baixar_arquivo(request, pk: int, arquivo_id: int):
    """Entrega o arquivo só a quem pode ver a solicitação (AGENTS.md §5.4, §6).

    Nunca exponha a pasta de uploads nem a URL do bucket: o acesso passa por
    aqui, que confere permissão e registra o download na auditoria.
    """
    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    arquivo = get_object_or_404(
        ArquivoDocumento.objects.select_related("documento"),
        pk=arquivo_id,
        documento__contraparte=solicitacao.contraparte,
    )

    registrar(
        acao=Acao.DOWNLOAD,
        descricao=f"Arquivo #{arquivo.pk} de {arquivo.documento.rotulo} baixado",
        objeto=arquivo.documento,
        usuario=request.user,
    )

    if settings.ARMAZENAMENTO == "s3":
        # No S3 o acesso é por URL assinada de curta duração, gerada agora.
        return redirect(arquivo.arquivo.url)

    return FileResponse(
        arquivo.arquivo.open("rb"),
        as_attachment=True,
        filename=arquivo.nome_original or Path(arquivo.arquivo.name).name,
    )


@login_required
def buscar_cep(request):
    """Preenche o endereço a partir do CEP (AGENTS.md D24).

    Falha silenciosa: sem resposta, o usuário digita à mão.
    """
    endereco = buscar_por_cep(request.GET.get("cep", ""))
    if endereco is None:
        return JsonResponse({"encontrado": False})
    return JsonResponse({"encontrado": True, **endereco})
