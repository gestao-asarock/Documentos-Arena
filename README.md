# Portal de Documentação do FII ARENA

Plataforma da **ASAROCK Asset Management** para validação de documentos e orquestração do
fluxo de aprovação das operações do **FII ARENA** — o fundo imobiliário ligado ao
S.C. Corinthians Paulista, cujo imóvel é a Neo Química Arena.

Cada operação (aluguel de espaço, reembolso, pagamento, serviço NQA, compra) é
**enquadrada** por tipo e faixa de valor, e esse enquadramento define ao mesmo tempo quais
áreas precisam aprovar e quais documentos são exigidos, conforme o *Guia de Regras de
Compliance — FII ARENA v2.0*.

> **Fase atual: MVP.** Apenas o fluxo piloto *Aluguel de Espaço — Evento até R$ 5.000,00*
> está no escopo. Uso interno.

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [AGENTS.md](AGENTS.md) | Domínio, regras de negócio, decisões e padrões de código. **Leia antes de contribuir.** |
| [CLAUDE.md](CLAUDE.md) | Operacional: comandos, ambiente, deploy e perguntas em aberto. |

## Stack

Django · Templates + HTMX · PostgreSQL · S3 · Celery/Redis · Gemini (análise documental) ·
Trillia/Neoway (compliance, mockado nesta fase).

## Rodando localmente

Requer Python 3.12 e Docker.

```powershell
# 1. Ambiente virtual ativo, dependências instaladas
pip install -r config/requirements/dev.txt

# 2. Configuração
Copy-Item .env.example .env    # e preencha DJANGO_SECRET_KEY

# 3. Serviços de apoio
docker compose -f config/docker-compose.yml up -d db redis

# 4. Banco e execução
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## Organização

| Pasta | Conteúdo |
|---|---|
| `src/` | Código da aplicação. O projeto Django é `src/arena/`. |
| `config/` | Infraestrutura: `Dockerfile`, `docker-compose.yml`, `requirements/`. |
| `docs/` | Documentação de negócio e material de referência. |
| `tests/` | Testes transversais; os de cada app ficam dentro do app. |

O Admin fica em http://localhost:8000/admin/.

## Avisos

- **Nenhum documento real** deve ser enviado à IA nesta fase: o free tier do Gemini usa o
  conteúdo para treinamento. Apenas dados fictícios (AGENTS.md §5.1).
- `.env` nunca é commitado, e o ambiente local nunca aponta para o banco de produção.
