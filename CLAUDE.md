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

## 🎯 Prioridade em vigor — leia antes de propor qualquer coisa

**O fluxo primeiro. Integração depois.** Decisão do responsável em 04/08/2026
(AGENTS.md D42 e §1). Isso vale acima de qualquer outra sugestão de ordem de trabalho,
inclusive das listas de "próximo passo" mais abaixo neste arquivo.

- **Agora:** deixar o fluxo interno funcional e robusto — cadastro, kit cadastral,
  triagem, pareceres, contrato, máquina de estados, permissões, telas, mensagens de erro.
- **Depois, uma de cada vez:** IA documental, API de compliance (Trillia) e Serasa.
- **Não** abra frente nova de integração externa, nem "só o esqueleto", sem o responsável
  dizer que a vez dela chegou.
- Achou problema de fluxo no meio de outra tarefa? Ele tem precedência. Diga e conserte.

**A triagem por IA já está escrita e testada, mas fora da `main`:** branch
`feat/triagem-ia` (AGENTS.md §9.4). Não a reescreva do zero e não a traga de volta sem
pedido — ela espera a vez. O que ela tem de **correção de fluxo**, e não de integração,
pode vir antes num commit separado: o principal é o `STATUS_EM_ANALISE`, que faz
documento já analisado contar como "em análise" em vez de pendência.

## Antes de escrever código, confira

- Código nosso em **português**; código do Django, intocado em inglês (AGENTS.md §3).
- **Enquadramento e alçadas são dados em tabela, não `if` no código** (AGENTS.md §4.4).
- Dinheiro em `Decimal`, nunca `float`. Teste de fronteira em cada limite de valor.
- **Nenhum documento real** enviado ao Gemini nesta fase — free tier treina com o
  conteúdo. Só dados fictícios (AGENTS.md §5.1).
- Integração externa só atrás de interface em `integracoes/`, e sempre via task Celery.
  `ProvedorIA` é agnóstica: um provedor local entra depois (AGENTS.md §7, D16).
- Data `31/07/2026`, valor `R$ 1.234,56` e CPF/CNPJ `589.747.908-90`, sempre pelos
  filtros de `operacoes/templatetags/formatacao.py` — nunca remontados na tela.
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

**Cadastro do perfil: tudo obrigatório** (AGENTS.md D43). Só escapam o complemento do
endereço e, para CNPJ, data de nascimento e RG — que somem da tela pelo próprio CPF/CNPJ
digitado, dizendo por quê: os dois campos trazem a ajuda "obrigatório para pessoa física"
e, no lugar deles, aparece um aviso quando o documento é de empresa. **O endereço se preenche ao completar o CEP** (D44): busca automática no oitavo
dígito, campos escondidos até lá, botão "Preencher endereço" para repetir a busca ou abrir
os campos à mão. Campo de formulário agora sai do partial `src/templates/_campo.html`.

> O formulário vai com `novalidate`: campo obrigatório escondido faz o navegador recusar o
> envio sem mostrar nada. Quem aponta o que falta é o servidor.

**Dinheiro na tela é campo de texto, nunca `type="number"`.** `MoedaBRField` em
`solicitacoes/campos.py`, com a máscara `moeda` do `formulario.js`: digita-se da direita
para a esquerda (123456 vira 1.234,56) e o servidor normaliza 1.234,56, 1234,56 e 1234.56.
O `input[type=number]` traz as setinhas e, com elas, a roda do mouse: passar o cursor sobre
o campo e rolar a página trocava o valor do contrato em silêncio.

**Identidade visual do Clube, em cinza** (AGENTS.md D45, D46). Os neutros viraram grafite
e quase-branco; as cinco cores de estado seguem intocadas e agora saltam mais. Link do
corpo leva sublinhado, porque sem azul a cor não distingue mais link de texto. O brasão
está no cabeçalho (pastilha branca, senão o contorno preto some no grafite) e grande na
tela de login.

> **Realce estrutural é cinza; cor é só estado.** A linha da etapa da vez
> (`.linha--atual`) usa `--cor-selecao` e faixa grafite, não azul: as cinco cores de estado
> dizem uma coisa só, e a pastilha da própria linha já diz "em andamento". Pintar a linha
> de azul repetia o recado e parecia um sexto estado. A linha do tempo (`.fluxo`) segue
> azul porque lá a cor **é** o status do passo, sem pastilha ao lado repetindo. O botão nativo do campo de arquivo é vestido por
`input[type="file"]::file-selector-button` em `base.css`, com a cara de `.botao--discreto`
— **não troque o input por um controle de JS** só para estilizá-lo.

> **Os arquivos da marca são gerados, não editados.** O original entregue é um JPEG com o
> quadriculado de transparência *desenhado nos pixels*. `docs/marca/gerar.py` recorta o
> fundo e escreve `src/static/img/marca.png` e `favicon.ico`. Precisa de Pillow, que **não**
> está nos requirements — é ferramenta de uma vez só (`pip install pillow` quando precisar).

**Edição do cadastro do perfil** (AGENTS.md D47): `/solicitacoes/<pk>/editar/`. Alterar o
que os documentos comprovam devolve o perfil ao começo da esteira — documentos aprovados
voltam para a triagem (arquivos ficam), pareceres concluídos voltam a rascunho. E-mail e
telefone salvam sem mexer em nada. **Antes de gravar, uma tela de confirmação**
(`editar_confirmar.html`) mostra o que muda e o que isso desfaz, em números, e exige marcar
a ciência. **CPF/CNPJ nunca é editável; perfil validado ou cancelado não se edita.** A marca da alteração fica em `Contraparte`
(`data_alteracao_cadastral`, `alterada_por`, `campos_alterados`) e aparece no detalhe.
Serviços em `contrapartes/servicos.py`: `alterar_dados_cadastrais` e `reiniciar_validacao`.

**Data de emissão obrigatória** onde o tipo a exige, e **alerta de prazo** quando o
documento chega vencido — aceita, mas com aviso forte no envio e no kit (AGENTS.md D48).
O prazo sai de `TipoDocumento.dias_validade`, nunca de constante no código. **Só no kit
cadastral:** o envio de documento do contrato não pede a data, porque ali o documento nasce
junto com o contrato e a emissão é sempre hoje.

**Selo de validação some quando o perfil é cancelado**: vira "Cancelada" em cinza. Mostrar
"Aguardando documentos" num cadastro encerrado sugeria que alguém ainda esperava algo. A
regra está em `Solicitacao.situacao_da_validacao`, e `VALIDACAO_NAO_SE_APLICA` entrou no
mapa de cores como qualquer status.

> **Nada de `—` nem de `·` na tela** (AGENTS.md D49). Dois pontos, vírgula, ponto e vírgula,
> parênteses e barra dizem o mesmo; valor vazio é `-`. Vale para template, `__str__`,
> `help_text` e mensagem — não para docstring nem comentário. `tests/test_templates.py`
> reprova quem esquecer, inclusive em arquivo novo.

> **`{# … #}` é de uma linha só.** O lexer do Django não usa `re.DOTALL`: em duas linhas o
> "comentário" vira **texto visível na página**, sem erro nenhum. Comentário de várias
> linhas é `{% comment %}`. `tests/test_templates.py` varre os templates atrás disso —
> três casos já tinham escapado para a `main`.

**Telas da Fase 1 prontas:** `/solicitacoes/` — formulário de entrada do Clube, detalhe com
**linha do tempo do fluxo** (`solicitacoes/fluxo.py`), kit cadastral com o que falta, envio
de documentos com as validações de D18 (`documentos/validadores.py`) e lista do que já foi
enviado, com vigência.

**Conferência documental funcionando** (app `analise`): fila em `/analise/` para `crm`,
`compliance` e `administrador`, tela de conferência com os dados declarados ao lado dos
arquivos, e decisão aprovar/rejeitar. Rejeição exige motivo e o Clube o vê na sua tela.
Aprovar o último documento do kit leva a habilitação para `EM_COMPLIANCE`.

**Due diligence funcionando** (app `compliance`): fila em `/compliance/` para `compliance` e
`administrador`, **Relatório** (um ou mais PDFs) acima da **Conclusão** (veredito
obrigatório, justificativa opcional), e recusa da contraparte. Concluir leva a habilitação
para `EM_CREDITO` ou direto para `HABILITADA`, conforme a matriz.

> **Os nove blocos de "Verificações" saíram** (AGENTS.md D50, 05/08/2026). O relatório é o
> parecer; a tela só coleta a decisão sobre ele. `concluir_parecer` recusa veredito sem
> relatório anexado. `EvidenciaParecer` virou `RelatorioParecer` (`related_name`
> `relatorios`), sem o campo `bloco`, e `documentos/validadores.validar_pdf` é o ponto
> único do "só PDF". **O crédito recebeu o mesmo tratamento** (`RelatorioCredito`,
> migration `credito/0004`), então as duas telas são gêmeas: mesmos formulários, mesmas
> regras de conclusão, mesma remoção de relatório.

**Relatório anexado por engano se remove** (`remover_relatorio`), enquanto o parecer está em
rascunho: o arquivo sai do storage junto e a remoção fica na auditoria. Depois de concluído
não sai — aquele PDF é o lastro do veredito que já correu para o crédito (AGENTS.md §6).
Tirar o último relatório tranca a conclusão de novo, pela mesma regra de D50.

**Risco e crédito funcionando** (app `credito`): fila em `/credito/` para `crm` e
`administrador` (o time de Risco não é usuário — D9), com **a mesma tela do compliance**
(D50): Relatório em PDF acima da Conclusão, veredito obrigatório, justificativa opcional,
remoção de relatório enquanto é rascunho. Concluir **habilita a contraparte** e marca a
solicitação como pronta para contrato — fim da Fase 1.

> A tela de crédito **nunca chegou a renderizar** o formulário de evidências: a view
> mandava `form_evidencia` para o template e o template não o usava, então o upload existia
> só na URL. Corrigido junto com o D50.

**Perfil × contrato separados** (AGENTS.md D29, D30): `Solicitacao` virou o **perfil** da
contraparte (só documentos base, sem valor nem evento); `Operacao` carrega tipo, descrição,
data, horário e valor, mais os documentos complementares escolhidos do perfil. Crédito
acontece **uma vez, na esteira do perfil**; o contrato não a refaz (AGENTS.md D30).

> **Dívida conhecida:** o app ainda se chama `solicitacoes`, mas hospeda os **perfis**.
> Renomear para `perfis` quando houver um momento tranquilo — mexe em migrations.

**Dossiê da tela de assinatura** (`operacoes/dossie.py`): a tela lista os **documentos
enviados pelo Clube** em duas seções — os deste contrato e o **kit cadastral do perfil** —,
baixáveis como foram enviados (`operacoes:baixar_documento`) — leitura
que **não cumpre a etapa 5**, ao contrário de `baixar_para_assinatura`, que converte o DOCX e
registra quem levou o contrato (AGENTS.md D54). Os relatórios de compliance e de
crédito são **baixáveis ali mesmo** (`operacoes:baixar_relatorio`, com a origem no caminho),
e a justificativa de cada parecer aparece como texto. O acesso é governado pela visibilidade
do **contrato**, não pelo papel da área: quem assina precisa poder ler o que sustenta a
assinatura. A view confere que o relatório é da contraparte daquele contrato — sem isso,
trocar o id na URL leria o parecer de outra pessoa — e registra o download na auditoria.

**Revisão jurídica tem tela própria** (AGENTS.md D52): `/juridico/<id>/`, com os documentos
baixáveis, os campos a conferir (`operacoes/conferencia.py`) e o parecer com aprovar/reprovar.
A fila do Jurídico leva para lá; a tela da operação virou painel e só oferece o botão "Abrir
revisão jurídica" para quem tem o papel. **Aprovar exige marcar todas as caixas de
conferência** (D53), e quem recusa é o servidor, nomeando o que falta; reprovar não exige
nenhuma. As marcações não são persistidas: o que fica é o parecer. O formulário genérico de decisão em
`operacoes/detalhe.html` continua servindo as etapas sem tela própria.

**Documento do contrato não tem triagem** (AGENTS.md D51): quem confere o Termo de Adesão é
a revisão jurídica. Duas propriedades, e a diferença importa: `documentacao_entregue` (nada
faltando, nada recusado) libera as **etapas** e a `fila_juridica`; `documentacao_completa`
(tudo aprovado) libera a **assinatura**. Aprovar a etapa jurídica aprova os documentos que
ela conferiu; reprovar devolve o contrato para `AGUARDANDO_DOCUMENTOS`.

> **`StatusOperacao.EM_ANALISE_DOCUMENTAL` ficou sem uso para contratos.** O valor segue no
> enum e nas transições, mas nada mais leva um contrato até lá: enviado já vai para
> `EM_APROVACAO`. Não o reintroduza sem antes reler D51.

> **"Documentos do contrato" fica concluída ao enviar**, não ao aprovar. A checagem responde
> "o Clube fez a parte dele?"; conferir o conteúdo é da revisão jurídica, que aparece logo
> abaixo como a etapa pendente. Dizer "pendente" com o documento já enviado cobrava duas
> vezes a mesma coisa. **Isso não libera a assinatura:** `pronto_para_assinatura` continua
> exigindo `documentacao_completa` e o jurídico decidido (D33).

**Fase 1 e Fase 2 amarradas:** a operação (contrato) só nasce de uma solicitação com
contraparte habilitada, e as etapas 1 a 3 chegam como `CUMPRIDA_NA_HABILITACAO`, trazendo
o veredito dos pareceres. O contrato começa direto na revisão jurídica.

**Estado do perfil é derivado do dossiê**, não do evento de aprovação
(`contrapartes/servicos.avancar_habilitacao`). É o que resolve o recadastro da mesma
pessoa: o kit é da contraparte, então um perfil novo pode nascer com ele já aprovado, e
antes ficava preso em "aguardando documentos" esperando uma aprovação que não tinha o que
aprovar. A regra roda ao abrir o perfil e ao abrir a tela — registro travado se conserta
sozinho. **Perfil em crédito ou adiante não regride:** dali em diante quem manda é o
parecer, não o dossiê.

**Visibilidade do Clube é do time, não do usuário** (AGENTS.md D35): filtro em
`contas/consultas.criado_dentro_da_casa`. Ver é do time; cancelar e excluir continuam
com quem abriu o registro (`operacoes.permissoes.eh_dono_ou_interno`).

**Ainda sem IA na `main`, e é assim de propósito:** a conferência é visual. A task Celery,
a extração e a evidência visual existem prontas na branch `feat/triagem-ia`, e entram
quando o fluxo estiver firme (D42). Enquanto isso, a triagem manual é o comportamento
oficial — trate-a como tal, não como provisório a ser tolerado: se ela está confusa ou
frágil, **é ali que se trabalha agora**.

> **Ao escrever migration à mão**, inclua `verbose_name="ID"` no `BigAutoField` da chave
> primária. Sem isso o Django gera uma migration corretiva no `makemigrations` seguinte
> (foi o que produziu `0003_alter_habilitacao_id` e companhia — inofensivas, mas ruído).

**Pendência conhecida:** baixar `htmx.min.js` para `src/static/js/` quando a primeira tela
precisar de interatividade. Nada de CDN. (Já baixado na branch `feat/triagem-ia`, versão
2.0.4 — dá para trazer só esse arquivo se alguma tela de fluxo precisar antes.)

**Próximo passo:** robustez do fluxo, não integração (D42). O que entra aqui sai de
conversa com o responsável — não presuma a lista.

## Perguntas em aberto

Dúvidas de negócio aguardando resposta do responsável. **Não resolva por conta própria.**
Ao ser respondida, a pergunta sai daqui e vira decisão no AGENTS.md §7.

| # | Pergunta | Impacto |
|---|---|---|
| P1 | A contraparte terá marcação de **parte relacionada** (só alerta em tela, sem alçada especial)? | Um booleano agora evita migration depois. |
| P2 | Quais **operações reais passadas** servirão de molde para a massa de teste, e quem prepara os arquivos com conteúdo fictício? | Bloqueia a validação com os times (AGENTS.md §7, D15). |
| P10 | **Cancelar o perfil deveria invalidar a habilitação da contraparte?** Hoje não invalida: a validação é da pessoa e sobrevive ao cadastro (D19, D29), então cancelar um perfil validado e recriá-lo devolve um perfil já pronto, sem refazer compliance. Se a intenção ao cancelar for "refazer do zero", o comportamento esperado é outro. | Define se cancelar é só arquivar o cadastro ou também derrubar a validação — e se existe um jeito de forçar nova due diligence. |
| P9 | A ASAROCK tem dever de comunicar operação suspeita ao **COAF/UIF**, e quer registrar essa comunicação aqui? | O campo existe no modelo mas saiu da tela: não altera o fluxo e confundia quem preenche. |
| P5 | **Prazo de validade da habilitação** da contraparte (praxe: 12 meses). | O campo existe; sem o número, não há revalidação automática (AGENTS.md D19). |
| P6 | Risco **alto** no parecer de compliance bloqueia a contratação ou escala para alguém liberar? Quem pode liberar? | Governança: define se existe estado de exceção aprovada (AGENTS.md §4.7). |
| P7 | Quais campos do formulário inicial são fixos e quais mudam por tipo de evento/serviço? | Define se o formulário é único ou por tipo de operação. |
| P8 | O check final ("ambas as análises conferidas") é feito por quem — a própria área, ou um segundo par de olhos? | Define se há etapa de conferência separada dos pareceres. |

## Pendências fora do código

> Estas são de **integração**: seguem valendo, mas estão em segundo plano até o fluxo
> ficar robusto (D42). Continuam aqui porque destravá-las leva tempo de calendário e o
> pedido pode ser feito em paralelo, sem consumir tempo de código.

- Obter acesso ao portal do desenvolvedor da Trillia: endpoints, payloads e preços.
- Migrar o Gemini para API paga antes de qualquer demo com dado real.
- Definir se a contraparte terá marcação de **parte relacionada** (só alerta em tela,
  sem alçada especial) — governança ainda "em discussão" no guia.
- Revisitar a etapa de **Risco/Crédito** quando o time entrar como usuário: hoje é
  aprovação manual com parecer, sem IA (AGENTS.md §4.2).
