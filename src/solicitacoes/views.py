"""Views da Fase 1: solicitação, kit cadastral e envio de documentos."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from arena.listagem import ordenar, paginar
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
from operacoes.permissoes import (
    eh_administrador,
    eh_dono_ou_interno,
    pode_cancelar,
    pode_criar_operacao,
    pode_editar_perfil,
    pode_excluir,
)

from . import fluxo as fluxo_do_processo
from .consultas import com_validacao
from .filtros import COLUNAS, ORDEM_PADRAO, FiltroPerfis
from .forms import EdicaoPerfilForm, EnvioDocumentoForm, SolicitacaoForm
from .models import Solicitacao
from .servicos import (
    abrir_habilitacao,
    buscar_contrapartes_visiveis,
    obter_ou_criar_contraparte,
    perfil_ativo_de,
    solicitacoes_visiveis_para,
)

#: As listas que têm busca com autocomplete. O nome da rota nunca vem da URL do
#: pedido: sem esse mapa, `origem` viraria um link para onde quem chamasse
#: quisesse, dentro de uma página nossa.
LISTAS_COM_BUSCA = {
    "perfis": "solicitacoes:lista",
    "contratos": "operacoes:lista",
}

#: Sugestão é atalho, não relatório: passando de oito a lista deixa de caber na
#: tela e a pessoa volta a ler linha a linha.
LIMITE_DE_SUGESTOES = 8


@login_required
def lista(request):
    """Lista de perfis com filtros, ordenação e paginação.

    Filtrar, ordenar e só então paginar: a página é o último recorte, ou a
    contagem passa a descrever a página em vez da lista.
    """
    visiveis = com_validacao(solicitacoes_visiveis_para(request.user))
    filtro = FiltroPerfis(request.GET, visiveis=visiveis)

    encontrados, ordem = ordenar(
        filtro.aplicar(visiveis),
        request.GET.get("ordem", ""),
        colunas=COLUNAS,
        padrao=ORDEM_PADRAO,
    )
    pagina = paginar(
        encontrados.select_related("contraparte", "habilitacao"), request.GET.get("pagina")
    )

    return render(
        request,
        "solicitacoes/lista.html",
        {
            "pagina": pagina,
            "solicitacoes": pagina.object_list,
            "total": pagina.paginator.count,
            "filtro": filtro,
            "ordem": ordem,
            "pode_criar": pode_criar_operacao(request.user),
        },
    )


@login_required
def buscar_contrapartes(request):
    """Sugestões de contraparte para a busca das listas (AGENTS.md D56).

    Devolve um pedaço de HTML, não JSON: quem consome é o htmx, que troca o
    conteúdo da caixa de sugestões. Cada sugestão é um **link** para a mesma
    lista com `contraparte` fixada, preservando os outros filtros que vieram
    junto no pedido; sem JavaScript nenhum a busca por texto continua servindo.

    As sugestões saem do que o usuário já pode ver. Oferecer um nome que ele não
    tem permissão de listar vazaria a existência da contraparte, e clicar nele
    devolveria tela vazia.
    """
    termo = request.GET.get("busca", "").strip()
    origem = request.GET.get("origem", "")
    destino = reverse(LISTAS_COM_BUSCA.get(origem, "solicitacoes:lista"))

    # Uma letra casa com quase tudo: a lista de sugestões viraria a lista inteira.
    encontradas = (
        buscar_contrapartes_visiveis(request.user, termo)[:LIMITE_DE_SUGESTOES]
        if len(termo) >= 2
        else []
    )

    # O link da sugestão leva os filtros em vigor: escolher a contraparte é um
    # recorte a mais, não um recomeço. `pagina` sai porque o resultado é outro.
    parametros = request.GET.copy()
    for chave in ("busca", "origem", "pagina", "contraparte"):
        parametros.pop(chave, None)

    sugestoes = []
    for contraparte in encontradas:
        parametros["contraparte"] = str(contraparte.pk)
        sugestoes.append({"contraparte": contraparte, "url": f"{destino}?{parametros.urlencode()}"})

    return render(
        request,
        "solicitacoes/_sugestoes.html",
        {"sugestoes": sugestoes, "termo": termo, "buscou": len(termo) >= 2},
    )


@login_required
def nova(request):
    """Cadastra o perfil, **um por CPF/CNPJ** (AGENTS.md D57).

    Documento que já tem perfil ativo não abre um segundo: a contraparte é uma
    só, o dossiê é dela e a validação também. Cadastrar de novo criava uma
    segunda esteira para a mesma pessoa, e o perfil novo nascia validado de
    graça, herdando a habilitação da primeira (D19, D29). Para atualizar dados
    ou trocar documento, o caminho é o perfil existente.
    """
    if not pode_criar_operacao(request.user):
        raise PermissionDenied

    form = SolicitacaoForm(request.POST or None)
    ja_existe = None

    if request.method == "POST" and form.is_valid():
        ja_existe = perfil_ativo_de(form.cleaned_data["documento"])
        if ja_existe is None:
            contraparte, _ = obter_ou_criar_contraparte(
                documento=form.cleaned_data["documento"], dados=form.dados_da_contraparte
            )
            solicitacao = Solicitacao.objects.create(
                contraparte=contraparte, criada_por=request.user
            )
            registrar(
                acao=Acao.CRIACAO,
                descricao=f"Perfil #{solicitacao.pk} cadastrado",
                objeto=solicitacao,
                usuario=request.user,
            )
            abrir_habilitacao(solicitacao, usuario=request.user)

            messages.success(request, f"Perfil #{solicitacao.pk} cadastrado.")
            return redirect("solicitacoes:detalhe", pk=solicitacao.pk)

        form.add_error("documento", "Já existe um cadastro de perfil para este CPF/CNPJ.")

    return render(
        request,
        "solicitacoes/nova.html",
        {
            "form": form,
            "bloqueado_por_duplicidade": ja_existe is not None,
            # Só oferece o link se quem cadastra puder mesmo abrir o registro.
            # Apontar para um perfil de outro time revelaria a existência dele,
            # e o link levaria a um 404 (AGENTS.md D35).
            "perfil_existente": (
                solicitacoes_visiveis_para(request.user).filter(pk=ja_existe.pk).first()
                if ja_existe is not None
                else None
            ),
        },
    )


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
    if not pode_editar_perfil(request.user, solicitacao):
        messages.error(
            request,
            "Perfil validado ou cancelado não pode ter os dados alterados."
            if not solicitacao.esta_cancelada
            else "Perfil cancelado não pode ter os dados alterados.",
        )
        return redirect("solicitacoes:detalhe", pk=pk)

    # O administrador edita o que o fluxo normal trava, e por padrão **sem**
    # reiniciar a validação (AGENTS.md D58): a edição dele é para corrigir
    # engano de digitação, não para invalidar análise que já correu. Quando ele
    # quiser o contrário, a caixa na tela pede a revalidação de propósito.
    como_administrador = eh_administrador(request.user)
    revalidar_por_escolha = bool(request.POST.get("revalidar"))

    contraparte = solicitacao.contraparte
    form = EdicaoPerfilForm(
        request.POST or None, initial=EdicaoPerfilForm.dados_iniciais(contraparte)
    )

    contexto = {
        "solicitacao": solicitacao,
        "contraparte": contraparte,
        "form": form,
        # A tela só avisa que a validação recomeça se houver o que recomeçar.
        "tem_analise_feita": contraparte.documentos_cadastrais.exists(),
        "como_administrador": como_administrador,
        # O aviso de poder excepcional só faz sentido onde o fluxo normal barra.
        "fora_do_fluxo_normal": como_administrador and not solicitacao.pode_ser_editada,
        "revalidar_marcado": revalidar_por_escolha,
    }

    # "Voltar e corrigir" na confirmação: devolve o formulário com o que foi
    # digitado, em vez de recarregar o que está no banco.
    if request.method == "POST" and request.POST.get("voltar"):
        return render(request, "solicitacoes/editar.html", contexto)

    if request.method == "POST" and form.is_valid():
        previa = comparar_cadastro(contraparte, form.dados_da_contraparte)

        if not previa:
            messages.info(request, "Nada foi alterado.")
            return redirect("solicitacoes:detalhe", pk=pk)

        # Quem decide se a validação recomeça: para o fluxo normal, a natureza do
        # campo alterado; para o administrador, a escolha dele na tela (D58).
        # Sem habilitação não há o que reiniciar, e `reiniciar_validacao` não
        # aceita nula: perfil nesse estado só chega aqui por dado antigo, mas
        # atender com erro 500 seria a pior forma de descobrir isso.
        pediu_revalidar = revalidar_por_escolha if como_administrador else previa.exige_revalidacao
        vai_revalidar = pediu_revalidar and solicitacao.habilitacao_id is not None

        # Alteração que derruba a conferência passa por uma confirmação própria,
        # que mostra o que muda e o que isso desfaz. Só depois dela se grava: o
        # efeito é grande demais para caber num aviso lido depois do fato. Sem
        # revalidação não há o que desfazer, e a confirmação seria só um clique.
        veio_da_confirmacao = bool(request.POST.get("confirmado"))
        if vai_revalidar and not (veio_da_confirmacao and request.POST.get("ciente")):
            return render(
                request,
                "solicitacoes/editar_confirmar.html",
                {
                    **contexto,
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

        if vai_revalidar:
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
            return redirect("solicitacoes:detalhe", pk=pk)

        if alteracao.exige_revalidacao:
            # Mudou o que os documentos comprovam e nada foi refeito. Isto não
            # pode acontecer em silêncio: fica na trilha (o autor vai no campo
            # `usuario`) e a marca de alteração aparece no detalhe.
            registrar(
                acao=Acao.ALTERACAO_CADASTRAL,
                descricao=(
                    f"Perfil #{solicitacao.pk}: {alteracao.resumo} alterado "
                    f"sem reiniciar a validação"
                ),
                objeto=solicitacao,
                usuario=request.user,
            )

        if pediu_revalidar:
            # Pediu e não havia habilitação para reiniciar. Um sucesso mudo aqui
            # faria a pessoa sair achando que a conferência foi refeita.
            messages.warning(
                request,
                f"Dados alterados ({alteracao.resumo}). Não havia validação em curso "
                "para reiniciar, então nada foi devolvido para a triagem.",
            )
        elif alteracao.exige_revalidacao:
            messages.warning(
                request,
                f"Dados alterados ({alteracao.resumo}) sem reiniciar a validação. "
                "Os documentos aprovados continuam valendo e agora atestam dados "
                "diferentes dos que foram conferidos.",
            )
        else:
            messages.success(request, f"Dados alterados ({alteracao.resumo}).")

        return redirect("solicitacoes:detalhe", pk=pk)

    return render(request, "solicitacoes/editar.html", contexto)


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
            "pode_editar": pode_editar_perfil(request.user, solicitacao),
            # Poder de correção do administrador (D58): a tela precisa dizer que
            # a edição está fora do fluxo normal, senão parece rotina.
            "edicao_excepcional": eh_administrador(request.user)
            and not solicitacao.pode_ser_editada,
            "pode_excluir": pode_excluir(request.user, solicitacao),
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
            "A triagem decide se aceita assim mesmo ou pede um mais recente.",
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
def excluir(request, pk: int):
    """Apaga de vez um perfil cancelado (AGENTS.md D58). Só o administrador.

    O que sai é o **cadastro**, e só ele. A contraparte fica, com o dossiê, os
    documentos e a habilitação: eles são dela, não deste registro (D29), e
    contrato antigo continua apontando para ela. Apagar o perfil não recomeça
    ninguém do zero, e a tela precisa dizer isso antes do clique.

    O evento de auditoria é gravado **antes** da exclusão, e é o que sobra do
    registro: depois dele não há mais objeto para apontar (AGENTS.md §6).
    """
    if request.method != "POST":
        return redirect("solicitacoes:detalhe", pk=pk)

    solicitacao = get_object_or_404(solicitacoes_visiveis_para(request.user), pk=pk)
    if not pode_excluir(request.user, solicitacao):
        raise PermissionDenied

    numero, contraparte = solicitacao.pk, solicitacao.contraparte
    registrar(
        acao=Acao.EXCLUSAO_REGISTRO,
        # Sem CPF/CNPJ: a descrição vai para a trilha e não guarda dado pessoal
        # (AGENTS.md §6). O id da contraparte basta para reencontrar quem era.
        descricao=(
            f"Perfil #{numero} excluído pelo administrador. "
            f"Contraparte #{contraparte.pk} mantida, com dossiê e habilitação"
        ),
        objeto=solicitacao,
        usuario=request.user,
    )
    solicitacao.delete()

    messages.success(
        request,
        f"Perfil #{numero} excluído. A contraparte, os documentos e a validação continuam.",
    )
    return redirect("solicitacoes:lista")


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
