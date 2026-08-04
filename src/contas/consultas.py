"""
Visibilidade por papel, num lugar só (AGENTS.md §4.2, D35).

O Clube enxerga a esteira **do time**, não a caixa de entrada pessoal de cada
usuário: o perfil que a ASAROCK cadastrou em nome dele, ou que outro colega
abriu, é dele também — e precisa aparecer, ou o Clube fica sem saber que existe.

O que continua fora do alcance dele é o trabalho interno: fila de análise,
parecer de compliance, resultado bruto de consulta. Isso é barrado por papel na
view, não por este filtro.
"""

from django.db.models import Q

from .models import PAPEIS_INTERNOS, Papel

#: Quem cria registros que pertencem à esteira: a ASAROCK e o próprio Clube.
#: Um papel externo futuro (outra contraparte, outro clube) fica de fora por
#: omissão — o filtro falha fechado, que é o lado certo de errar.
PAPEIS_DA_CASA = frozenset(PAPEIS_INTERNOS | {Papel.CLUBE})


def criado_dentro_da_casa(campo: str = "criada_por") -> Q:
    """Registros abertos por alguém da ASAROCK ou do Clube.

    O superusuário entra explicitamente: conta de administração costuma não ter
    grupo nenhum, e sem esta cláusula o que ela cadastrasse sumiria da tela do
    Clube — foi exatamente assim que um perfil criado pelo admin ficou invisível.
    """
    return Q(**{f"{campo}__groups__name__in": PAPEIS_DA_CASA}) | Q(
        **{f"{campo}__is_superuser": True}
    )


__all__ = ["PAPEIS_DA_CASA", "criado_dentro_da_casa"]
