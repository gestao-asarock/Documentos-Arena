# Contexto de build é a RAIZ do repositório, não esta pasta.
# Local:     docker compose -f config/docker-compose.yml build
# Produção:  docker build -f config/Dockerfile .
# 3.11 para casar com o ambiente de desenvolvimento (AGENTS.md §7, D17).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# A imagem de produção não leva pytest nem ruff. O Compose de desenvolvimento
# constrói com INSTALAR_DEV=true para poder rodar os testes dentro do container.
ARG INSTALAR_DEV=false

COPY config/requirements/ ./config/requirements/
RUN if [ "$INSTALAR_DEV" = "true" ]; then \
        pip install --no-cache-dir -r config/requirements/dev.txt; \
    else \
        pip install --no-cache-dir -r config/requirements/base.txt; \
    fi

COPY . .

EXPOSE 8000

CMD ["gunicorn", "arena.wsgi:application", "--chdir", "/app/src", "--bind", "0.0.0.0:8000", "--workers", "3"]
