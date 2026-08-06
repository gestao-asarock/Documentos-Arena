"""
Ordenação e paginação de lista, num lugar só.

As duas listas grandes do sistema (perfis e contratos) precisam do mesmo
comportamento, e ele não pertence a nenhum dos dois apps: mora aqui, ao lado da
configuração do projeto.

A ordenação **nunca** entrega o texto da URL ao `order_by`: só passam as chaves
que a própria tela declarou. Sem essa lista branca, qualquer campo do modelo (e
das tabelas ligadas a ele) vira ordenável pela barra de endereço, inclusive os
que não deveriam sequer aparecer.
"""

from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import F

#: Vinte e cinco por página, por decisão do responsável: a lista cabe na tela
#: sem rolagem longa e a paginação continua barata no banco.
POR_PAGINA = 25


@dataclass(frozen=True)
class Ordem:
    """A ordenação em vigor, do jeito que o cabeçalho da tabela precisa saber."""

    chave: str
    descendente: bool

    @property
    def pedido(self) -> str:
        """Como esta ordem aparece na URL: `valor` ou `-valor`."""
        return f"-{self.chave}" if self.descendente else self.chave

    def direcao_de(self, chave: str) -> str:
        """`asc`, `desc` ou vazio, para a seta e o `aria-sort` da coluna."""
        if chave != self.chave:
            return ""
        return "desc" if self.descendente else "asc"

    def alternar(self, chave: str) -> str:
        """O pedido que o link da coluna deve levar.

        Clicar na coluna que já ordena inverte o sentido; clicar em outra começa
        crescente, que é o que se espera de nome e de valor. Data é o caso em que
        crescente engana (mostra o mais antigo), e por isso a tela declara o
        padrão dela em `padrao`.
        """
        if chave == self.chave and not self.descendente:
            return f"-{chave}"
        return chave


def _expressao(campo: str, descendente: bool):
    """Ordenação com nulo sempre no fim, seja qual for o sentido.

    Vale tanto para coluna do banco quanto para campo vindo de `annotate` (a
    etapa atual, por exemplo, que é nula quando o contrato terminou). Sem
    `nulls_last`, o PostgreSQL joga os nulos para o topo em ordem decrescente e
    a primeira página fica cheia de linha vazia.
    """
    expressao = F(campo)
    return expressao.desc(nulls_last=True) if descendente else expressao.asc(nulls_last=True)


def ordenar(queryset, pedido: str, *, colunas: dict[str, tuple[str, ...]], padrao: str):
    """Aplica a ordenação pedida na URL, ou o padrão da tela.

    `colunas` mapeia a chave que aparece na URL para os campos reais do banco:
    uma chave pode ordenar por mais de um campo (contraparte ordena por nome e,
    em empate, por documento).

    Devolve o queryset ordenado e a `Ordem` em vigor. Pedido desconhecido cai no
    padrão em silêncio: é URL editada à mão ou link velho, não erro do usuário.
    """
    escolhido = pedido or padrao
    chave = escolhido.removeprefix("-")
    descendente = escolhido.startswith("-")

    if chave not in colunas:
        chave = padrao.removeprefix("-")
        descendente = padrao.startswith("-")

    campos = [_expressao(campo, descendente) for campo in colunas[chave]]
    # Desempate fixo pelo id: sem ele, duas linhas com o mesmo valor podem trocar
    # de lugar entre uma página e outra, e um registro some da listagem.
    campos.append(_expressao("pk", True))

    return queryset.order_by(*campos), Ordem(chave=chave, descendente=descendente)


def paginar(queryset, numero, *, por_pagina: int = POR_PAGINA):
    """Página pedida, tolerante a número inválido ou fora do intervalo."""
    return Paginator(queryset, por_pagina).get_page(numero)


__all__ = ["POR_PAGINA", "Ordem", "ordenar", "paginar"]
