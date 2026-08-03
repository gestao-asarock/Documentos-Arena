# CLAUDE.md

> **Leia o [AGENTS.md](AGENTS.md) antes de qualquer alteração neste repositório.**
>
> Ele contém o domínio, a stack, as decisões travadas e as regras obrigatórias.
> Este arquivo não repete aquele conteúdo — traz apenas o operacional do dia a dia.
> Em caso de conflito entre os dois, **AGENTS.md prevalece**.

## Resumo em 30 segundos

Plataforma da ASAROCK para validar documentos e orquestrar a aprovação das operações do
**FII ARENA** (fundo ligado ao Corinthians): aluguel de espaço, reembolsos, pagamentos,
serviços NQA e compras. O **enquadramento** de cada operação (tipo + faixa de valor)
define quais áreas precisam aprovar e quais documentos são exigidos.
Django + Templates/HTMX + PostgreSQL + S3 + Celery. Análise documental via Gemini,
compliance via Trillia (mockado). Fase de **MVP**: mínimo, limpo e apresentável.

Regra de negócio vem do *Guia de Regras de Compliance — FII ARENA v2.0*. Se este repo
divergir do guia, **o guia prevalece**.

## Antes de escrever código, confira

- Código nosso em **português**; código do Django, intocado em inglês (AGENTS.md §3).
- **Enquadramento e alçadas são dados em tabela, não `if` no código** (AGENTS.md §4.4).
- Dinheiro em `Decimal`, nunca `float`. Teste de fronteira em cada limite de valor.
- **Nenhum documento real** enviado ao Gemini nesta fase — free tier treina com o
  conteúdo. Só dados fictícios (AGENTS.md §5.1).
- Integração externa só atrás de interface em `integracoes/`, e sempre via task Celery.
  `ProvedorIA` é agnóstica: um provedor local entra depois (AGENTS.md §7, D16).
- Data `31/07/2026` e valor `R$ 1.234,56`, sempre por filtro de template único.
- Nenhum segredo no repositório. Nenhum CPF, token ou conteúdo de documento em log.
- A IA não aprova nem reprova, e não enquadra — decisão é humana e auditada.
- **Não invente regra de compliance.** Não está no guia? Pergunte.
- Não introduza tecnologia fora da stack definida sem perguntar.

## Escopo ativo

Apenas o fluxo piloto: **Aluguel de Espaço — Evento até R$ 5.000,00** (AGENTS.md §4.3).
Os outros dez enquadramentos da matriz estão documentados mas **não implementados** —
entram um a um, após validação do piloto.

**O fluxo tem duas fases** (AGENTS.md §4.0): habilitar a contraparte (formulário → kit
cadastral → OCR com evidência visual → compliance → crédito) e só então contratar (tipo de
contrato → documentos → análise jurídica → assinatura). A contraparte **não é usuária do
sistema** — quem opera é o Clube, em nome dela.

## Regras de trabalho (detalhe em AGENTS.md §9)

1. **Não execute comandos do Django nem do Docker.** `makemigrations`, `migrate`,
   `startapp`, `createsuperuser`, `docker compose up`, `pip install`, deploy — todos são
   rodados pelo responsável. Escreva o código, pare, e diga qual comando rodar e em que
   ordem. Depois siga a partir da saída real.
2. **Documente antes de encerrar.** Toda troca importante vira texto em `AGENTS.md`
   (decisão/regra) ou `CLAUDE.md` (comando/ambiente/pendência), na mesma sessão.
3. **`pytest` verde antes de qualquer deploy**, com a saída mostrada. Sem exceção.

## Comandos

> Rodados pelo responsável, não pelo agente. Preencher conforme o projeto for montado.

Sempre a partir da **raiz** do repositório. O código fica em `src/`, a infraestrutura em
`config/` (AGENTS.md §8).

```powershell
# Dependências (venv ativo)
pip install -r config/requirements/dev.txt

# Serviços de apoio — em dev basta db e redis, rodando o Django no venv
docker compose -f config/docker-compose.yml up -d db redis

# Banco e execução
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Qualidade
pytest
pytest src/operacoes/tests/test_enquadramento.py::test_waiver_dispensa_documentacao_e_etapas
ruff check .
ruff format .

# Ambiente completo em containers
docker compose -f config/docker-compose.yml up -d
docker compose -f config/docker-compose.yml logs -f app worker
```

## Checklist de deploy

Executado pelo responsável. O agente prepara e descreve; não roda nada (AGENTS.md §9.1).

1. `pytest` completo, verde, com a saída mostrada. Falhou = não há deploy.
2. `ruff check .` e `ruff format .` sem pendência.
3. Confirmar **contra qual ambiente** o deploy vai — conferir que o `.env` em uso é o de
   produção e que o banco alvo é o RDS certo.
4. Backup do banco antes de aplicar migration (`pg_dump` ou snapshot do RDS).
5. `git pull` na EC2 e rebuild das imagens.
6. Aplicar migrations, revisando antes o que cada uma faz.
7. `collectstatic`.
8. Subir os containers e conferir `docker compose ps` e os logs.
9. Teste de fumaça: login, abrir uma operação, subir um documento, ver o status avançar.
10. Se algo falhar: como voltar (imagem anterior + restore do backup) antes de tentar
    consertar em produção.

## Ambiente

- Windows + PowerShell. Use sintaxe PowerShell no terminal (não `&&`, não `export`).
- Copie `.env.example` para `.env` e preencha. `.env` nunca é commitado.
- Sem AWS local: `AWS_STORAGE` aponta para MinIO ou pasta local; o código não muda.
- **`.env` de desenvolvimento e de produção são arquivos distintos.** A máquina local
  nunca aponta para o RDS de produção. Antes de comando destrutivo ou migration, confira
  o banco alvo e diga qual é, em voz alta, ao responsável.
- **Dois arquivos de dependência, de propósito.** `requirements.txt` é o que roda em
  produção; `requirements-dev.txt` inclui aquele e acrescenta `pytest` e `ruff`. O
  Dockerfile decide pelo argumento `INSTALAR_DEV` (o Compose local passa `true`; o build
  de produção omite). Dependência nova de execução vai no primeiro arquivo, ferramenta de
  desenvolvimento no segundo.

## Estado atual do projeto

**Infraestrutura pronta e núcleo do domínio escrito. Migrations ainda não geradas.**

Estrutura em `src/` (código), `config/` (infra) e `docs/`, com o projeto Django chamado
`arena` — ver AGENTS.md §8.

Apps escritos: `contas` (usuário próprio + papéis), `auditoria` (trilha imutável, Admin
somente leitura), `documentos` (catálogo `TipoDocumento`), `contrapartes` (dossiê
reaproveitável com vigência) e `operacoes` (tabela de regras, enquadramento, etapas e
máquina de estados). Testes cobrindo fronteiras de valor, matriz de alçadas, waiver e
transições inválidas.

**Cargas iniciais escritas à mão** (não rode `makemigrations` para elas):

- `contas/0002_papeis` — cria os cinco grupos de papéis, sem permissões (atribuídas no Admin).
- `documentos/0002` e `0003` — campo `obrigatorio_no_kit` + catálogo do guia: os cinco
  itens do Kit Cadastral PJ e o contrato do fluxo piloto.
- `operacoes/0002` — o enquadramento piloto com as seis alçadas e sua exigência documental.

Todas são reversíveis e idempotentes (`update_or_create`), então rodar de novo não duplica.

**Telas de trabalho prontas:** login próprio, lista de operações, criação com
enquadramento automático, detalhe com etapas, e decisão de etapa (aprovar/reprovar com
parecer obrigatório) restrita ao papel responsável. Templates em `src/templates/`,
componentes de CSS em `src/static/css/base.css`, filtros `moeda`, `data_br` e
`data_hora_br` em `operacoes/templatetags/formatacao.py`, papéis por etapa em
`operacoes/permissoes.py`, avanço de estado em `servicos.avancar`.

**Fase 1 iniciada** (AGENTS.md §4.0): app `solicitacoes` com o formulário de entrada do
Clube, `Habilitacao` em `contrapartes`, e `ExigenciaCadastral` em `documentos` — o kit
cadastral agora é tabela por tipo de pessoa e faixa de valor, com grupos de alternativas
(holerite **ou** declaração de IR). Dedução de PF/PJ pelo CPF/CNPJ em
`contrapartes.models.deduzir_tipo_pessoa`.

**Telas da Fase 1 prontas:** `/solicitacoes/` — formulário de entrada do Clube, detalhe com
**linha do tempo do fluxo** (`solicitacoes/fluxo.py`), kit cadastral com o que falta, envio
de documentos com as validações de D18 (`documentos/validadores.py`) e lista do que já foi
enviado, com vigência.

**Conferência documental funcionando** (app `analise`): fila em `/analise/` para `crm`,
`compliance` e `administrador`, tela de conferência com os dados declarados ao lado dos
arquivos, e decisão aprovar/rejeitar. Rejeição exige motivo e o Clube o vê na sua tela.
Aprovar o último documento do kit leva a habilitação para `EM_COMPLIANCE`.

**Due diligence funcionando** (app `compliance`): fila em `/compliance/` para `compliance` e
`administrador`, parecer com os nove blocos de AGENTS.md §4.7, evidências anexadas por
bloco, veredito de risco obrigatório com justificativa, e recusa da contraparte. Concluir
leva a habilitação para `EM_CREDITO` ou direto para `HABILITADA`, conforme a matriz.

**Risco e crédito funcionando** (app `credito`): fila em `/credito/` para `crm`,
`compliance` e `administrador` (o time de Risco não é usuário — D9), parecer com cinco
blocos, evidências e veredito. Concluir **habilita a contraparte** e marca a solicitação
como pronta para contrato — fim da Fase 1.

**Perfil × contrato separados** (AGENTS.md D29, D30): `Solicitacao` virou o **perfil** da
contraparte (só documentos base, sem valor nem evento); `Operacao` carrega tipo, descrição,
data, horário e valor, mais os documentos complementares escolhidos do perfil. Crédito
continua na esteira do perfil (análise da pessoa) e é **ancorado** no enquadramento do
primeiro contrato que o usar — outro tipo ou outra faixa pedem análise nova.

> **Dívida conhecida:** o app ainda se chama `solicitacoes`, mas hospeda os **perfis**.
> Renomear para `perfis` quando houver um momento tranquilo — mexe em migrations.

**Fase 1 e Fase 2 amarradas:** a operação (contrato) só nasce de uma solicitação com
contraparte habilitada, e as etapas 1 a 3 chegam como `CUMPRIDA_NA_HABILITACAO`, trazendo
o veredito dos pareceres. O contrato começa direto na revisão jurídica.

**Ainda sem IA:** a conferência é visual. A task Celery, a extração e a evidência visual
entram no próximo incremento — e é lá que o `htmx.min.js` passa a ser necessário.

> **Ao escrever migration à mão**, inclua `verbose_name="ID"` no `BigAutoField` da chave
> primária. Sem isso o Django gera uma migration corretiva no `makemigrations` seguinte
> (foi o que produziu `0003_alter_habilitacao_id` e companhia — inofensivas, mas ruído).

**Pendência conhecida:** baixar `htmx.min.js` para `src/static/js/` quando a primeira tela
precisar de interatividade (upload, polling de análise). Nada de CDN.

**Próximo passo:** upload de documento (`DocumentoOperacao` + armazenamento) e o pipeline
de análise por IA.

## Perguntas em aberto

Dúvidas de negócio aguardando resposta do responsável. **Não resolva por conta própria.**
Ao ser respondida, a pergunta sai daqui e vira decisão no AGENTS.md §7.

| # | Pergunta | Impacto |
|---|---|---|
| P1 | A contraparte terá marcação de **parte relacionada** (só alerta em tela, sem alçada especial)? | Um booleano agora evita migration depois. |
| P2 | Quais **operações reais passadas** servirão de molde para a massa de teste, e quem prepara os arquivos com conteúdo fictício? | Bloqueia a validação com os times (AGENTS.md §7, D15). |
| P4 | Quem no Clube são os usuários do papel `clube`, e eles enxergam todas as operações do Clube ou só as que criaram? | Define a regra de filtragem de queryset. |
| P9 | A ASAROCK tem dever de comunicar operação suspeita ao **COAF/UIF**, e quer registrar essa comunicação aqui? | O campo existe no modelo mas saiu da tela: não altera o fluxo e confundia quem preenche. |
| P5 | **Prazo de validade da habilitação** da contraparte (praxe: 12 meses). | O campo existe; sem o número, não há revalidação automática (AGENTS.md D19). |
| P6 | Risco **alto** no parecer de compliance bloqueia a contratação ou escala para alguém liberar? Quem pode liberar? | Governança: define se existe estado de exceção aprovada (AGENTS.md §4.7). |
| P7 | Quais campos do formulário inicial são fixos e quais mudam por tipo de evento/serviço? | Define se o formulário é único ou por tipo de operação. |
| P8 | O check final ("ambas as análises conferidas") é feito por quem — a própria área, ou um segundo par de olhos? | Define se há etapa de conferência separada dos pareceres. |

## Pendências fora do código

- Obter acesso ao portal do desenvolvedor da Trillia: endpoints, payloads e preços.
- Migrar o Gemini para API paga antes de qualquer demo com dado real.
- Definir se a contraparte terá marcação de **parte relacionada** (só alerta em tela,
  sem alçada especial) — governança ainda "em discussão" no guia.
- Revisitar a etapa de **Risco/Crédito** quando o time entrar como usuário: hoje é
  aprovação manual com parecer, sem IA (AGENTS.md §4.2).
