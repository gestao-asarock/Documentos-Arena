"""Serviços de solicitação: criação, dedução de PF/PJ e abertura da habilitação."""

from django.db import transaction
from django.db.models import Q

from auditoria.servicos import Acao, registrar
from contas.consultas import criado_dentro_da_casa
from contrapartes.models import (
    Contraparte,
    Habilitacao,
    StatusHabilitacao,
    apenas_digitos,
    deduzir_tipo_pessoa,
)
from contrapartes.servicos import CAMPOS_DE_CONTATO, avancar_habilitacao

from .models import Solicitacao, StatusSolicitacao

#: Situações em que o perfil ainda **ocupa** o CPF/CNPJ e barra um cadastro novo
#: (AGENTS.md D57). Cancelado fica de fora de propósito: perfil cancelado não se
#: edita (`Solicitacao.pode_ser_editada`), então bloquear nele deixaria o
#: documento sem caminho nenhum, nem cadastro novo nem correção do antigo.
STATUS_QUE_OCUPAM_O_DOCUMENTO = frozenset(
    set(StatusSolicitacao.values) - {StatusSolicitacao.CANCELADA}
)


def perfil_ativo_de(documento: str) -> Solicitacao | None:
    """O perfil que já ocupa este CPF/CNPJ, se houver (AGENTS.md D57).

    Olha a base **inteira**, sem filtro de visibilidade: o bloqueio precisa valer
    também quando o perfil existente é de outro time, ou dois times abririam
    esteiras paralelas para a mesma pessoa. Quem decide se o número pode ser
    mostrado a quem está cadastrando é a view, não esta função (AGENTS.md D35).

    Havendo mais de um (base antiga, antes de D57), devolve o mais velho: é o
    que tem histórico e é o que o comando `perfis_duplicados` mantém.
    """
    numero = apenas_digitos(documento)
    if not numero:
        return None
    return (
        Solicitacao.objects.filter(
            contraparte__documento=numero, status__in=STATUS_QUE_OCUPAM_O_DOCUMENTO
        )
        .select_related("contraparte", "habilitacao")
        .order_by("pk")
        .first()
    )


def obter_ou_criar_contraparte(*, documento: str, dados: dict) -> tuple[Contraparte, bool]:
    """Reaproveita a contraparte pelo CPF/CNPJ, ou cria uma nova.

    O tipo de pessoa vem do documento, não de escolha do usuário (AGENTS.md §4.5).
    O documento nunca muda.

    **Contraparte que já existe não é reescrita por um cadastro novo.** O que os
    documentos comprovam (nome, endereço, RG) só se altera pela edição do perfil,
    que mostra o efeito antes de gravar e reinicia a validação (AGENTS.md D47).
    Sem esta guarda, cadastrar de novo o mesmo CPF/CNPJ com outro nome trocava o
    nome de uma contraparte **já validada**, sem confirmação e sem auditoria: a
    porta lateral do D47. Aqui só se preenche o que estava em branco, e o
    contato, que nenhum documento atesta.
    """
    numero = apenas_digitos(documento)
    tipo_pessoa = deduzir_tipo_pessoa(numero)

    contraparte = Contraparte.objects.filter(documento=numero).first()
    if contraparte is None:
        return Contraparte.objects.create(documento=numero, tipo_pessoa=tipo_pessoa, **dados), True

    for campo, valor in dados.items():
        if valor and (campo in CAMPOS_DE_CONTATO or not getattr(contraparte, campo)):
            setattr(contraparte, campo, valor)
    contraparte.save()
    return contraparte, False


@transaction.atomic
def abrir_habilitacao(solicitacao: Solicitacao, *, usuario=None) -> Habilitacao:
    """Inicia a validação do perfil — ou reaproveita a que já está vigente.

    O perfil é da contraparte, não do contrato: um segundo cadastro do mesmo
    terceiro não refaz compliance (AGENTS.md D19, D29).
    """
    contraparte = solicitacao.contraparte
    vigente = contraparte.habilitacao_vigente

    if vigente is not None:
        solicitacao.habilitacao = vigente
        solicitacao.status = StatusSolicitacao.PRONTA_PARA_CONTRATO
        solicitacao.save()
        registrar(
            acao=Acao.ENQUADRAMENTO,
            descricao=(
                f"Solicitação #{solicitacao.pk} reaproveitou habilitação vigente "
                f"da contraparte #{contraparte.pk}"
            ),
            objeto=solicitacao,
            usuario=usuario,
        )
        return vigente

    habilitacao = Habilitacao.objects.create(
        contraparte=contraparte, status=StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    )
    solicitacao.habilitacao = habilitacao
    solicitacao.status = StatusSolicitacao.EM_HABILITACAO
    solicitacao.save()

    registrar(
        acao=Acao.CRIACAO,
        descricao=f"Habilitação aberta para a contraparte #{contraparte.pk}",
        objeto=habilitacao,
        usuario=usuario,
    )

    # O kit é da contraparte: um perfil novo pode já nascer com ele completo e
    # aprovado. Sem derivar o estado aqui, a habilitação ficava presa em
    # "aguardando documentos" esperando uma aprovação que não tinha o que
    # aprovar — nada para o Clube enviar, nada na triagem, fluxo parado.
    return avancar_habilitacao(habilitacao, usuario=usuario)


def solicitacoes_visiveis_para(usuario):
    """Mesma regra das operações: o Clube vê a esteira do time (AGENTS.md §4.2, D35)."""
    base = Solicitacao.objects.select_related("contraparte", "habilitacao")
    if usuario.is_superuser or usuario.eh_interno:
        return base
    if usuario.eh_do_clube:
        return base.filter(criado_dentro_da_casa()).distinct()
    return base.none()


def buscar_contrapartes_visiveis(usuario, termo: str):
    """Contrapartes que o usuário já enxerga, casando com o termo digitado.

    A permissão não é da contraparte, e sim dos registros dela: quem vê um
    perfil ou um contrato vê a contraparte por trás. Derivar daí, em vez de
    consultar `Contraparte` direto, mantém a regra de visibilidade num lugar só
    (AGENTS.md §4.2, D35) e evita que o autocomplete vire uma porta lateral para
    listar toda a base.
    """
    from operacoes.servicos import operacoes_visiveis_para

    dos_perfis = solicitacoes_visiveis_para(usuario).values("contraparte_id")
    dos_contratos = operacoes_visiveis_para(usuario).values("contraparte_id")

    digitos = apenas_digitos(termo)
    casa = Q(nome__icontains=termo) | Q(nome_fantasia__icontains=termo)
    if digitos:
        casa |= Q(documento__contains=digitos)

    return (
        Contraparte.objects.filter(Q(pk__in=dos_perfis) | Q(pk__in=dos_contratos))
        .filter(casa)
        .order_by("nome")
        .distinct()
    )
