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


#: Travessão e ponto médio saíram da interface por decisão do responsável
#: (AGENTS.md D49). Dois pontos, vírgula, ponto e vírgula, parênteses e barra
#: dizem a mesma coisa; para valor vazio, hífen.
PONTUACAO_BANIDA = {"—": "travessão", "·": "ponto médio"}


def test_pontuacao_banida_fora_dos_templates():
    achados = [
        f"{caminho.relative_to(settings.BASE_DIR)}:{numero} ({nome})"
        for caminho in templates()
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
        for simbolo, nome in PONTUACAO_BANIDA.items()
        if simbolo in linha
    ]

    assert not achados, f"Troque por pontuação comum: {', '.join(achados)}"


def test_pontuacao_banida_fora_do_texto_de_tela():
    """Vale para o que o Python manda para a tela: `__str__`, `help_text`, mensagem.

    Docstring e comentário ficam de fora: são texto para quem lê o código, não
    para quem usa o sistema.
    """
    import ast

    achados = []
    for caminho in sorted(Path(settings.SRC_DIR).rglob("*.py")):
        if "migrations" in caminho.parts:
            continue

        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        docstrings = {
            id(no.body[0].value)
            for no in ast.walk(arvore)
            if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and no.body
            and isinstance(no.body[0], ast.Expr)
            and isinstance(no.body[0].value, ast.Constant)
            and isinstance(no.body[0].value.value, str)
        }

        for no in ast.walk(arvore):
            if not isinstance(no, ast.Constant) or not isinstance(no.value, str):
                continue
            if id(no) in docstrings:
                continue
            for simbolo, nome in PONTUACAO_BANIDA.items():
                if simbolo in no.value:
                    achados.append(f"{caminho.relative_to(settings.BASE_DIR)}:{no.lineno} ({nome})")

    assert not achados, f"Troque por pontuação comum: {', '.join(achados)}"
