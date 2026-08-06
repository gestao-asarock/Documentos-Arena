"""
Views de operação.

View fina: recebe request, chama serviço, devolve resposta (AGENTS.md §8).
Toda listagem passa por `operacoes_visiveis_para` — nunca consulte `Operacao`
diretamente numa view, ou o filtro por papel se perde.
"""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render

from arena.listagem import ordenar, paginar
from auditoria.servicos import Acao, registrar
from contrapartes.models import ArquivoDocumento, DocumentoCadastral
from integracoes.conversao import ConversaoIndisponivel, converter_docx_em_pdf

from .consultas import com_etapa_atual
from .dossie import montar as montar_dossie
from .dossie import nome_do_contrato, pronto_para_assinatura
from .estados import Etapa, TransicaoInvalida
from .filtros import COLUNAS, ORDEM_PADRAO, FiltroOperacoes, montar_abas
from .forms import (
    DecisaoEtapaForm,
    EnvioDocumentoContratoForm,
    OperacaoForm,
    VincularDocumentosForm,
)
from .models import EtapaAprovacao, Operacao
from .permissoes import pode_cancelar, pode_criar_operacao, pode_decidir, pode_excluir
from .servicos import (
    ContraparteNaoHabilitada,
    EnquadramentoAmbiguo,
    EnquadramentoNaoEncontrado,
    avancar,
    decidir_etapa,
    enquadrar,
    operacoes_visiveis_para,
    registrar_download_para_assinatura,
)


@login_required
def lista(request):
    """Lista de contratos com abas por tipo, filtros, ordenação e paginação.

    A ordem das operações importa: filtrar primeiro, ordenar depois, paginar por
    último. Paginar antes de filtrar devolveria "25 de 300" e recortaria a
    página, não a lista.
    """
    visiveis = com_etapa_atual(operacoes_visiveis_para(request.user))
    filtro = FiltroOperacoes(request.GET, visiveis=visiveis)

    encontradas, ordem = ordenar(
        filtro.aplicar(visiveis),
        request.GET.get("ordem", ""),
        colunas=COLUNAS,
        padrao=ORDEM_PADRAO,
    )
    pagina = paginar(encontradas.prefetch_related("etapas"), request.GET.get("pagina"))

    return render(
        request,
        "operacoes/lista.html",
        {
            "pagina": pagina,
            "operacoes": pagina.object_list,
            "total": pagina.paginator.count,
            "filtro": filtro,
            "ordem": ordem,
            "abas": montar_abas(request.GET, visiveis, filtro.valor("tipo")),
            "pode_criar": pode_criar_operacao(request.user),
        },
    )


@login_required
def detalhe(request, pk: int):
    # Filtra pelo queryset permitido, não por Operacao.objects: assim trocar o ID
    # na URL devolve 404 em vez de vazar dado de outra operação (AGENTS.md §6).
    operacao = get_object_or_404(
        operacoes_visiveis_para(request.user).prefetch_related("etapas"), pk=pk
    )
    # Reaplica as regras antes de mostrar: registros parados durante uma mudança
    # de regra ficariam com o status antigo, contradizendo o resto da tela.
    if not operacao.esta_encerrada:
        avancar(operacao)
        operacao.refresh_from_db()

    etapa_atual = operacao.etapa_atual
    form_envio = EnvioDocumentoContratoForm(operacao=operacao)

    # A revisão jurídica tem tela própria (AGENTS.md D52): aqui a operação só
    # aponta o caminho para quem tem papel de revisar.
    na_revisao_juridica = bool(etapa_atual) and etapa_atual.etapa == Etapa.JURIDICO

    # A etapa 5 não se decide por parecer: ela se cumpre baixando o contrato. A
    # tela manda o responsável para o download em vez de oferecer aprovar/reprovar.
    na_assinatura = bool(etapa_atual) and etapa_atual.etapa == Etapa.ASSINATURAS

    return render(
        request,
        "operacoes/detalhe.html",
        {
            "operacao": operacao,
            "etapas": operacao.etapas.all(),
            "etapa_atual": etapa_atual,
            "documentacao_completa": operacao.documentacao_completa,
            # O que destrava as etapas é o **envio**: conferir o documento é o
            # trabalho da revisão jurídica, não um pré-requisito dela.
            "documentacao_entregue": operacao.documentacao_entregue,
            "na_assinatura": na_assinatura,
            "pode_baixar_contrato": (
                na_assinatura
                and pode_decidir(request.user, etapa_atual)
                and pronto_para_assinatura(operacao)
            ),
            "pode_decidir": (
                bool(etapa_atual)
                and not na_assinatura
                and not na_revisao_juridica
                and operacao.documentacao_entregue
                and pode_decidir(request.user, etapa_atual)
            ),
            "na_revisao_juridica": na_revisao_juridica,
            "pode_revisar": (
                na_revisao_juridica
                and operacao.documentacao_entregue
                and pode_decidir(request.user, etapa_atual)
            ),
            "pode_cancelar": operacao.pode_ser_cancelada and pode_cancelar(request.user, operacao),
            "pode_excluir": pode_excluir(request.user, operacao),
            # A tela conta o que a exclusão leva junto: as etapas são CASCATA e
            # com elas vai o texto de cada parecer (AGENTS.md D58).
            "etapas_decididas": sum(1 for e in operacao.etapas.all() if e.esta_decidida),
            "form_decisao": DecisaoEtapaForm(),
            "documentos_exigidos": operacao.documentos_exigidos(),
            "documentos_pendentes": operacao.documentos_pendentes(),
            # Separa "falta enviar" de "enviado, aguardando conferência": o mesmo
            # documento aparecia nos dois lugares e parecia ser dois.
            "situacao": operacao.situacao_documental(),
            "tipos_a_enviar": operacao.tipos_a_enviar(),
            "form_documentos": VincularDocumentosForm(operacao=operacao),
            "form_envio": form_envio,
            # Documento de contrato não pede data de emissão: só o subtipo depende
            # do tipo escolhido.
            "config_campos": {"subtipo": getattr(form_envio, "tipos_com_subtipo", [])},
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
def assinatura(request, pk: int):
    """Dossiê de checagens e download do contrato pronto (AGENTS.md §4.10, D33)."""
    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)

    return render(
        request,
        "operacoes/assinatura.html",
        {
            "operacao": operacao,
            "checagens": montar_dossie(operacao),
            "liberado": pronto_para_assinatura(operacao),
            # Quando já houve download, a etapa guarda quem baixou e quando.
            "etapa_assinatura": next(
                (e for e in operacao.etapas.all() if e.etapa == Etapa.ASSINATURAS), None
            ),
            "documentos": operacao.documentos.select_related("tipo", "subtipo").prefetch_related(
                "arquivos"
            ),
            # O kit cadastral é da contraparte, não deste contrato: entra numa
            # lista à parte, para não parecer exigência da operação (D29, D54).
            "documentos_do_perfil": (
                operacao.contraparte.documentos_cadastrais.exclude(operacoes=operacao)
                .select_related("tipo", "subtipo")
                .prefetch_related("arquivos")
                .order_by("tipo__nome")
            ),
        },
    )


@login_required
def baixar_para_assinatura(request, pk: int, arquivo_id: int):
    """Entrega o contrato em PDF, convertendo o DOCX quando necessário.

    A conversão acontece uma vez e fica guardada: o Clube baixa sempre o mesmo
    arquivo, e a auditoria registra cada download.
    """
    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    if not pronto_para_assinatura(operacao):
        messages.error(request, "O contrato ainda não passou por todas as checagens.")
        return redirect("operacoes:assinatura", pk=pk)

    arquivo = get_object_or_404(
        ArquivoDocumento.objects.filter(documento__operacoes=operacao), pk=arquivo_id
    )

    if arquivo.precisa_converter:
        try:
            pdf = converter_docx_em_pdf(
                arquivo.arquivo.read(), nome=arquivo.nome_original or "termo.docx"
            )
        except ConversaoIndisponivel as erro:
            messages.error(request, str(erro))
            return redirect("operacoes:assinatura", pk=pk)

        nome = Path(arquivo.nome_original or "termo").stem + ".pdf"
        arquivo.pdf_convertido.save(nome, ContentFile(pdf), save=True)

    entrega = arquivo.arquivo_para_assinatura
    # O nome de entrega é montado agora, e nada muda no storage: lá o UUID
    # continua, porque caminho adivinhável é vazamento (AGENTS.md §5.4, D60).
    nome_entregue = nome_do_contrato(operacao, Path(entrega.name).suffix.lower() or ".pdf")

    registrar(
        acao=Acao.DOWNLOAD,
        descricao=f"Contrato #{operacao.pk} baixado para assinatura",
        objeto=operacao,
        usuario=request.user,
    )

    # Baixar é o ato que cumpre a etapa 5: quem baixou e quando ficam guardados
    # e aparecem na tela da operação.
    if registrar_download_para_assinatura(operacao, usuario=request.user):
        messages.success(
            request,
            "Etapa de assinatura registrada: o contrato foi baixado para coleta de assinaturas.",
        )

    if settings.ARMAZENAMENTO == "s3":
        # A URL assinada serve o objeto pelo nome da chave, que é o UUID. Quem
        # renomeia é o próprio S3, pelo cabeçalho pedido na assinatura: sem este
        # parâmetro o navegador salvaria o UUID mesmo com o nome montado acima.
        return redirect(
            entrega.storage.url(
                entrega.name,
                parameters={
                    "ResponseContentDisposition": f'attachment; filename="{nome_entregue}"'
                },
            )
        )

    return FileResponse(entrega.open("rb"), as_attachment=True, filename=nome_entregue)


@login_required
def baixar_documento(request, pk: int, arquivo_id: int):
    """Entrega o documento **como o Clube enviou**, para leitura.

    Diferente de `baixar_para_assinatura`, que converte o DOCX em PDF e **cumpre
    a etapa 5**: este caminho é de conferência e não decide nada. Quem precisa
    ler o que foi enviado antes de assinar não deveria ter de cumprir a etapa
    para conseguir abrir o arquivo (AGENTS.md §4.10, D54).

    Serve tanto os documentos do contrato quanto o kit cadastral: os dois são da
    **contraparte** deste contrato, e é isso que a busca confere. Sem esse
    filtro, trocar o id na URL leria documento de outra pessoa.
    """
    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    arquivo = get_object_or_404(
        ArquivoDocumento.objects.select_related("documento").filter(
            documento__contraparte=operacao.contraparte
        ),
        pk=arquivo_id,
    )

    registrar(
        acao=Acao.DOWNLOAD,
        descricao=(
            f"Arquivo #{arquivo.pk} de {arquivo.documento.rotulo} baixado no dossiê "
            f"do contrato #{operacao.pk}"
        ),
        objeto=arquivo.documento,
        usuario=request.user,
    )

    if settings.ARMAZENAMENTO == "s3":
        return redirect(arquivo.arquivo.url)

    return FileResponse(
        arquivo.arquivo.open("rb"),
        as_attachment=True,
        filename=arquivo.nome_original or Path(arquivo.arquivo.name).name,
    )


#: De onde vem o relatório do dossiê. O acesso é governado pela visibilidade do
#: **contrato**, não pelo papel da área: quem pode assinar precisa poder ler o
#: parecer que sustenta a assinatura (AGENTS.md §4.10, §6).
RELATORIOS_DO_DOSSIE = {
    "compliance": ("compliance.RelatorioParecer", "parecer__habilitacao__contraparte"),
    "credito": ("credito.RelatorioCredito", "parecer__contraparte"),
}


@login_required
def baixar_relatorio(request, pk: int, origem: str, relatorio_id: int):
    """Entrega o relatório de compliance ou de crédito a quem vê o contrato.

    Nunca exponha a pasta de uploads nem a URL do bucket: o acesso passa por
    aqui, que confere permissão e registra o download na auditoria.
    """
    from django.apps import apps

    if origem not in RELATORIOS_DO_DOSSIE:
        raise PermissionDenied

    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    rotulo_modelo, caminho_contraparte = RELATORIOS_DO_DOSSIE[origem]
    Modelo = apps.get_model(rotulo_modelo)

    # O relatório precisa ser da contraparte deste contrato: sem isso, trocar o
    # id na URL leria o parecer de outra pessoa.
    relatorio = get_object_or_404(
        Modelo, pk=relatorio_id, **{caminho_contraparte: operacao.contraparte}
    )

    registrar(
        acao=Acao.DOWNLOAD,
        descricao=f"Relatório de {origem} baixado no dossiê do contrato #{operacao.pk}",
        objeto=operacao,
        usuario=request.user,
    )

    if settings.ARMAZENAMENTO == "s3":
        # No S3 o acesso é por URL assinada de curta duração, gerada agora.
        return redirect(relatorio.arquivo.url)

    return FileResponse(
        relatorio.arquivo.open("rb"),
        as_attachment=True,
        filename=relatorio.nome_original or Path(relatorio.arquivo.name).name,
    )


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


@login_required
def excluir(request, pk: int):
    """Apaga de vez um contrato cancelado (AGENTS.md D58). Só o administrador.

    **Isto apaga as etapas junto**, e com elas os pareceres de quem aprovou ou
    reprovou cada uma (`EtapaAprovacao` é `CASCADE`). A trilha de auditoria fica
    (§6), mas o texto das decisões, não: por isso a tela conta quantas etapas
    vão embora antes do clique, e por isso o evento gravado aqui também conta.

    Os documentos **não** saem: eles pertencem à contraparte e podem estar
    sustentando outro contrato (D29). O parecer de crédito também fica, só perde
    o vínculo com este contrato (`SET_NULL`).
    """
    if request.method != "POST":
        return redirect("operacoes:detalhe", pk=pk)

    operacao = get_object_or_404(operacoes_visiveis_para(request.user), pk=pk)
    if not pode_excluir(request.user, operacao):
        raise PermissionDenied

    numero, etapas = operacao.pk, operacao.etapas.count()
    registrar(
        acao=Acao.EXCLUSAO_REGISTRO,
        descricao=(
            f"Contrato #{numero} excluído pelo administrador, com {etapas} etapa"
            f"{'s' if etapas != 1 else ''} e seus pareceres. "
            f"Contraparte #{operacao.contraparte_id} e documentos mantidos"
        ),
        objeto=operacao,
        usuario=request.user,
    )
    operacao.delete()

    messages.success(request, f"Contrato #{numero} excluído. Os documentos da contraparte ficam.")
    return redirect("operacoes:lista")


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
