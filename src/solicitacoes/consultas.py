"""
O selo de validação como coluna consultável (CLAUDE.md, robustez do fluxo).

`Solicitacao.situacao_da_validacao` é propriedade e devolve o par status/rótulo
que a coluna "Validação" mostra. Para **filtrar e ordenar** a lista, a mesma
regra precisa existir em SQL, ou cada página teria de carregar todos os perfis
para decidir quais entram.

A regra é curta e cabe num `Case`: perfil cancelado não tem validação em curso;
sem habilitação, não há o que mostrar; no resto, vale o status da habilitação.
`test_validacao_anotada.py` compara os dois caminhos e reprova se discordarem.
"""

from django.db.models import Case, CharField, F, Value, When

from .models import VALIDACAO_NAO_SE_APLICA, StatusSolicitacao


def com_validacao(queryset):
    """Acrescenta `validacao_codigo`: o status bruto do selo da coluna."""
    return queryset.annotate(
        validacao_codigo=Case(
            When(status=StatusSolicitacao.CANCELADA, then=Value(VALIDACAO_NAO_SE_APLICA)),
            When(habilitacao__isnull=True, then=Value("")),
            default=F("habilitacao__status"),
            output_field=CharField(),
        )
    )


__all__ = ["com_validacao"]
