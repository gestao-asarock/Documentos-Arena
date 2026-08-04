"""
Erros de template que passam calados (CLAUDE.md — robustez do fluxo).

Nenhum destes quebra o servidor: eles vazam para a tela do usuário, onde só
alguém olhando a página encontra. Por isso viram teste.
"""

import re
from pathlib import Path

from django.conf import settings

#: O mesmo reconhecimento do lexer do Django (`django.template.base.tag_re`).
#: Sem `re.DOTALL`, de propósito: `{# … #}` **não** atravessa linha.
TAG = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")


def templates() -> list[Path]:
    return sorted(Path(settings.SRC_DIR).rglob("*.html"))


def test_ha_templates_para_conferir():
    """Guarda contra o teste passar porque não achou arquivo nenhum."""
    assert len(templates()) > 10


def test_comentario_de_template_nao_vaza_para_a_tela():
    """`{# … #}` é de uma linha só. Em duas, o Django imprime o texto na página.

    Comentário de várias linhas é `{% comment %}`. O engano não dá erro: o
    comentário aparece no HTML, e só se descobre olhando a tela.
    """
    vazando = []
    for caminho in templates():
        # Fora as tags reconhecidas, nenhum `{#` ou `#}` deveria sobrar no HTML.
        sobra = TAG.sub("", caminho.read_text(encoding="utf-8"))
        for numero, linha in enumerate(sobra.splitlines(), 1):
            if "{#" in linha or "#}" in linha:
                vazando.append(f"{caminho.relative_to(settings.BASE_DIR)}:{numero}")

    assert not vazando, (
        "Comentário `{# #}` em mais de uma linha vira texto visível na página. "
        f"Troque por `{{% comment %}}`: {', '.join(vazando)}"
    )
