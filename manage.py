#!/usr/bin/env python
"""Utilitário de linha de comando do Django.

O código da aplicação vive em `src/`; este arquivo fica na raiz por convenção
do Django e acrescenta `src/` ao caminho de importação.
"""

import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"


def main():
    sys.path.insert(0, str(SRC))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "arena.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django não encontrado. O ambiente virtual está ativo e as dependências "
            "de config/requirements/dev.txt foram instaladas?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
