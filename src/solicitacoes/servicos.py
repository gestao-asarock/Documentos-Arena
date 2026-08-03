"""Serviços de solicitação: criação, dedução de PF/PJ e abertura da habilitação."""

from django.db import transaction

from auditoria.servicos import Acao, registrar
from contrapartes.models import (
    Contraparte,
    Habilitacao,
    StatusHabilitacao,
    apenas_digitos,
    deduzir_tipo_pessoa,
)

from .models import Solicitacao, StatusSolicitacao


def obter_ou_criar_contraparte(*, documento: str, dados: dict) -> tuple[Contraparte, bool]:
    """Reaproveita a contraparte pelo CPF/CNPJ, ou cria uma nova.

    O tipo de pessoa vem do documento, não de escolha do usuário (AGENTS.md §4.5).
    Dados de contato são atualizados; o documento nunca muda.
    """
    numero = apenas_digitos(documento)
    tipo_pessoa = deduzir_tipo_pessoa(numero)

    contraparte = Contraparte.objects.filter(documento=numero).first()
    if contraparte is None:
        return Contraparte.objects.create(documento=numero, tipo_pessoa=tipo_pessoa, **dados), True

    for campo, valor in dados.items():
        if valor:
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
    return habilitacao


def solicitacoes_visiveis_para(usuario):
    """Mesma regra das operações: o Clube vê apenas o que criou (AGENTS.md §4.2)."""
    base = Solicitacao.objects.select_related("contraparte", "habilitacao")
    if usuario.is_superuser or usuario.eh_interno:
        return base
    if usuario.eh_do_clube:
        return base.filter(criada_por=usuario)
    return base.none()
