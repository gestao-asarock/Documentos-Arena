"""
A etapa da vez como coluna consultável (CLAUDE.md, robustez do fluxo).

`Operacao.etapa_atual` é propriedade: varre as etapas em memória e devolve a
primeira ainda não decidida, na ordem do fluxo. Isso serve para a tela de uma
operação, mas não serve para **filtrar e ordenar uma lista**: exigiria carregar
todos os contratos a cada página, que é justamente o problema de escala.

Aqui a mesma regra é escrita em SQL, com `Subquery`. A regra passa a existir em
dois lugares, e isso é uma dívida assumida: `test_etapa_atual_anotada.py` compara
os dois caminhos registro a registro, e reprova se discordarem.
"""

from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When

from .estados import ORDEM_ETAPAS, StatusEtapa
from .models import EtapaAprovacao

#: O que conta como "ainda não decidida" — o mesmo conjunto de `etapa_atual`.
ETAPAS_EM_ABERTO = (StatusEtapa.PENDENTE, StatusEtapa.EM_ANALISE)


def _ordem_do_fluxo():
    """A posição de cada etapa em `ORDEM_ETAPAS`, como coluna do banco.

    A ordem do fluxo é da lista Python, não do id nem do alfabeto: "2. Due
    diligence" vem antes de "4. Revisão jurídica" porque a lista diz isso.
    """
    return Case(
        *[When(etapa=etapa, then=Value(posicao)) for posicao, etapa in enumerate(ORDEM_ETAPAS)],
        output_field=IntegerField(),
    )


def com_etapa_atual(queryset):
    """Acrescenta `etapa_atual_codigo` e `etapa_atual_ordem` ao queryset.

    Nulos nas duas colunas querem dizer "nenhuma etapa em aberto": contrato
    concluído, cancelado ou ainda sem etapas geradas.
    """
    em_aberto = (
        EtapaAprovacao.objects.filter(operacao=OuterRef("pk"), status__in=ETAPAS_EM_ABERTO)
        .annotate(posicao=_ordem_do_fluxo())
        .order_by("posicao")
    )

    return queryset.annotate(
        etapa_atual_codigo=Subquery(em_aberto.values("etapa")[:1]),
        etapa_atual_ordem=Subquery(em_aberto.values("posicao")[:1]),
    )


__all__ = ["ETAPAS_EM_ABERTO", "com_etapa_atual"]
