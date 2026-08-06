"""
A barra de filtros da lista de perfis (CLAUDE.md, robustez do fluxo).

O perfil é reaproveitável e não se encerra junto com o contrato: a lista só
cresce. Sem recorte, achar "os perfis parados esperando documento" vira leitura
linha a linha.

Como na lista de contratos, tudo o que filtra é coluna do banco ou vem de
`consultas.com_validacao`. Nenhum filtro decide em memória.
"""

from django import forms
from django.db.models import Q

from arena.filtros import OPCOES_SIM_NAO, FiltroBase, SelecaoMultipla, partes_da_busca
from contrapartes.models import StatusHabilitacao, TipoPessoa

from .models import VALIDACAO_NAO_SE_APLICA, StatusSolicitacao

#: Chave da URL para os campos do banco por onde ela ordena (arena/listagem.py).
COLUNAS = {
    "numero": ("pk",),
    "contraparte": ("contraparte__nome",),
    "documento": ("contraparte__documento",),
    "tipo": ("contraparte__tipo_pessoa",),
    "situacao": ("status",),
    "validacao": ("validacao_codigo",),
    "criacao": ("data_criacao",),
    "movimentacao": ("data_atualizacao",),
}

ORDEM_PADRAO = "-criacao"

#: O selo cinza de perfil cancelado entra junto com os status de habilitação:
#: na coluna "Validação" ele aparece como qualquer outro, então também precisa
#: ser filtrável como qualquer outro (solicitacoes/models.py).
OPCOES_VALIDACAO = [
    *StatusHabilitacao.choices,
    (VALIDACAO_NAO_SE_APLICA, "Cancelada"),
]


class FiltroPerfis(FiltroBase):
    """Os recortes da lista de perfis."""

    #: Primeiro o que recorta a esteira, depois quem e quando.
    field_order = [
        "situacao",
        "validacao",
        "tipo_pessoa",
        "parado",
        "criador",
        "parte_relacionada",
        "criado_de",
        "criado_ate",
        "movimentado_de",
        "movimentado_ate",
    ]

    situacao = forms.MultipleChoiceField(
        label="Situação",
        required=False,
        choices=StatusSolicitacao.choices,
        widget=SelecaoMultipla,
    )
    validacao = forms.MultipleChoiceField(
        label="Validação",
        required=False,
        choices=OPCOES_VALIDACAO,
        widget=SelecaoMultipla,
    )
    tipo_pessoa = forms.ChoiceField(
        label="Tipo de pessoa",
        required=False,
        choices=[("", "Pessoa física e jurídica"), *TipoPessoa.choices],
    )
    parte_relacionada = forms.ChoiceField(
        label="Parte relacionada", required=False, choices=OPCOES_SIM_NAO
    )

    def condicao_de_busca(self, termo: str) -> Q:
        """Número do perfil, nome, nome fantasia ou CPF/CNPJ da contraparte."""
        condicao = Q(contraparte__nome__icontains=termo) | Q(
            contraparte__nome_fantasia__icontains=termo
        )

        numero, digitos = partes_da_busca(termo)
        if numero is not None:
            condicao |= Q(pk=numero)
        if digitos:
            condicao |= Q(contraparte__documento__contains=digitos)

        return condicao

    def _aplicar_proprios(self, queryset):
        if situacoes := self.valor("situacao"):
            queryset = queryset.filter(status__in=situacoes)
        if validacoes := self.valor("validacao"):
            # Vem de `com_validacao`: a mesma regra de `situacao_da_validacao`,
            # escrita em SQL para caber num WHERE (solicitacoes/consultas.py).
            queryset = queryset.filter(validacao_codigo__in=validacoes)
        if tipo := self.valor("tipo_pessoa"):
            queryset = queryset.filter(contraparte__tipo_pessoa=tipo)
        if relacionada := self.valor("parte_relacionada"):
            queryset = queryset.filter(contraparte__parte_relacionada=relacionada == "sim")

        return queryset


__all__ = ["COLUNAS", "ORDEM_PADRAO", "OPCOES_VALIDACAO", "FiltroPerfis"]
