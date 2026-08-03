# AGENTS.md — Documentos Arena

Documento de referência para qualquer agente de IA ou pessoa que escreva código neste
repositório. Ele define **o que estamos construindo**, **como construímos** e
**o que é proibido**. Leia inteiro antes da primeira alteração.

Fonte de negócio: *Guia de Regras de Compliance — FII ARENA, v2.0, julho/2026*
(uso interno). Quando este documento e o guia divergirem, **o guia prevalece** e o
AGENTS.md deve ser corrigido.

---

## 1. O produto

Plataforma interna da **ASAROCK Asset Management** (referida como "ASA") para
**validação de documentos** e **orquestração do fluxo de aprovação e assinaturas** das
operações do **FII ARENA** — o fundo imobiliário ligado ao S.C. Corinthians Paulista.

O fluxo, em uma frase: alguém registra uma **operação** entre o Fundo e um terceiro,
o sistema **enquadra** essa operação nas regras de alçada, exige a documentação
correspondente, a IA classifica/extrai/valida os documentos, o Compliance faz due
diligence, e as áreas responsáveis aprovam etapa por etapa até a assinatura.

**Cliente:** Corinthians (cliente único — ver §7, D2).

### Fase atual: MVP

Objetivo: chegar rápido a algo demonstrável, **limpo e apresentável**, mas mínimo.
Depois vem a validação (times internos + cliente) e só então melhorias.

Na prática:

- Preferir o recurso pronto do Django a construir abstração própria.
- Não construir para requisitos que ninguém pediu.
- Não otimizar performance sem medida que justifique.
- Mas: nada de gambiarra visível na tela ou erro não tratado na frente do cliente.

**Estratégia de entrega: um enquadramento por vez.** O MVP implementa **apenas o
fluxo piloto** (§4.3) de ponta a ponta. Os demais enquadramentos só entram depois que
o piloto for validado com os times. O motor de regras (§4.4) já nasce genérico, mas a
tabela de regras começa preenchida com um caso só.

---

## 2. Stack e decisões travadas

| Camada | Escolha |
|---|---|
| Backend | **Django** (Python), com uso intenso do **Django Admin** |
| Frontend | **Django Templates + HTMX** (+ Alpine.js se necessário), CSS próprio |
| Banco | **PostgreSQL** (RDS em produção, container em dev) |
| Arquivos | **S3** desde o início — nunca disco local, nunca `bytea` no banco |
| Fila | **Celery + Redis** (chamada externa nunca no ciclo de request) |
| IA documental | **Gemini** (multimodal: PDF e imagem no mesmo pipeline) |
| Compliance | **Trillia/Neoway** — mockado nesta fase (§5.2) |
| Deploy | **Docker Compose** na EC2; RDS + S3 na conta AWS da empresa |
| Testes | pytest + pytest-django |

**Não introduza tecnologia fora desta lista sem perguntar.** Nada de React/Vue/SPA,
nada de npm/webpack/build step, nada de ORM alternativo, nada de microserviço.
Dependência nova = pare e pergunte.

### Por que HTMX

O sistema é formulário, lista, upload e aprovação — não precisa de SPA. HTMX resolve
por atributos no HTML os três pontos onde o server-side puro trava: upload sem recarregar
a página, status de análise atualizando sozinho enquanto a IA processa, e filtro/busca
atualizando só a tabela. Sem build step, um deploy só, Django Admin preservado.

---

## 3. Idioma e nomenclatura

**Regra:** código nosso em **português**; código do framework, intocado em inglês.

```python
# CERTO
class Operacao(models.Model):
    valor_total = models.DecimalField(...)
    data_criacao = models.DateTimeField(auto_now_add=True)

    def esta_documentada(self) -> bool: ...


# ERRADO — mistura injustificada
class Operacao(models.Model):
    valor_total = models.DecimalField(...)
    created_at = models.DateTimeField(auto_now_add=True)
```

Permanece em inglês, por ser do Django: `User`, `password`, `is_active`,
`get_absolute_url`, `save`, `clean`, `Meta`, `verbose_name`, nomes de settings, e a
assinatura de qualquer método que sobrescreve o framework.

Sem acento e sem cedilha em identificadores (`analise`, `servico`, `operacao`). Acento
existe apenas em strings visíveis, `verbose_name`, docstrings e comentários.

Interface, mensagens, e-mails e labels em **português do Brasil**.
`LANGUAGE_CODE = "pt-br"`, `TIME_ZONE = "America/Sao_Paulo"`.

### Vocabulário do domínio

Use exatamente estes termos no código e na interface:

| Termo | Significado |
|---|---|
| **Fundo** | FII ARENA, o fundo imobiliário. Parte contratante de toda operação. |
| **ASA** | ASAROCK Asset Management, a gestora. Nós. |
| **Clube** | S.C. Corinthians Paulista. Usuário externo do sistema. |
| **Genial** | Administradora do fundo. Executa boletagem e liquidação **fora** do sistema. |
| **NQA** | **Neo Química Arena** — o imóvel dentro do FII ARENA para o qual este fluxo é desenhado. "Serviços NQA" = serviços prestados na arena. |
| **Contraparte** | O terceiro (PF ou PJ) do outro lado da operação. |
| **Operação** | O caso concreto a ser aprovado (um aluguel, uma compra, um pagamento). |
| **Enquadramento** | Classificação da operação (tipo + faixa de valor) que define alçadas e documentos. |
| **Alçada** | Conjunto de áreas cuja aprovação é obrigatória para aquele enquadramento. |
| **Kit Cadastral PJ** | Documentação base exigida de toda contraparte pessoa jurídica. |
| **Waiver** | Dispensa de documentação e de etapas (compras até R$ 10.000,00). |
| **DD** | Due diligence, feita pelo Compliance. |

---

## 4. Domínio

### 4.0 O fluxo real, em duas fases

O guia descreve as **áreas** que aprovam. A operação real acontece em duas fases, e a
distinção é estruturante: **habilitar a contraparte** vem antes de **contratar**.

```
FASE 1 — HABILITAÇÃO DA CONTRAPARTE (por contraparte, reaproveitável)

  1. Clube preenche o formulário de solicitação
     (dados do evento/serviço + dados do contratante + valor)
     → o sistema deduz PF ou PJ pelo documento informado
  2. Sistema pede o kit cadastral aplicável (§4.5)
  3. Documentos enviados entram na FILA DE ANÁLISE
  4. IA faz OCR, extrai os dados e devolve EVIDÊNCIA VISUAL de cada campo
  5. Sistema confronta documento × formulário e verifica validade
       divergência ou documento vencido → PENDÊNCIA, o fluxo trava
       corrige o Clube (reenvio) ou a ASAROCK (erro de leitura da IA)
  6. Sem pendência → fila de COMPLIANCE (due diligence, §4.8)
  7. Aprovado no compliance → fila de RISCO/CRÉDITO, quando exigido (§4.4)
  8. Ambos aprovados e conferidos → CONTRAPARTE HABILITADA

FASE 2 — CONTRATAÇÃO (por contrato)

  9. Formulário do tipo de contrato (os processos do guia) +
     se usa MODELO DA BASE ou DOCUMENTO PRÓPRIO da contraparte
 10. Sistema pede os documentos daquele enquadramento
 11. Fila de ANÁLISE DOCUMENTAL: IA compara com o modelo, aponta
     inconsistências e riscos jurídicos, sempre com trecho do documento
 12. Check manual do Jurídico
 13. Tudo validado → liberado para ASSINATURA
     (o Clube vê e baixa o contrato; só aparece se todas as checagens passaram)
```

O que vem depois da assinatura — envio de NFs, boletagem e liquidação — fica para uma
etapa posterior do projeto (§7, D8).

**Duas consequências que não podem ser esquecidas:**

- A contraparte **não tem acesso ao sistema**. Quem opera é o Clube, em nome dela. Não
  existe login de contraparte, nem convite por e-mail, nem portal externo.
- A habilitação é **da contraparte**, não do contrato: uma segunda contratação com o mesmo
  terceiro entra direto na Fase 2, desde que a habilitação siga válida (§7, D19).

### 4.1 As oito etapas do guia

O guia numera as áreas que atuam. Elas continuam valendo e são a base da matriz de
alçadas (§4.4) — a Fase 1 corresponde às etapas 1 a 3, a Fase 2 às etapas 4 e 5.

| # | Etapa | Área responsável | No sistema? |
|---|---|---|---|

| # | Etapa | Área responsável | No sistema? |
|---|---|---|---|
| 1 | Triagem de documentos | CRM (ASA) | ✅ |
| 2 | Due diligence | Compliance (ASA) | ✅ |
| 3 | Pesquisa de crédito | Risco / Crédito (ASA) | ⚠️ registrada, executada fora (§4.2) |
| 4 | Revisão de docs, assinatura pelo Clube e vigência | Jurídico ASA / Genial | ✅ |
| 5 | Upload no sistema para assinatura | Clube | ✅ |
| 6 | Envio de NFs e docs de suporte p/ liquidação | Clube | 📌 só status |
| 7 | Boletagem no sistema da Genial | ASA / CRM | 📌 só status |
| 8 | Liquidação | Genial | 📌 só status |

**Escopo do MVP: etapas 1 a 5.** As etapas 6 a 8 existem como registro de status e data,
sem integração com a Genial e sem tela de trabalho (§7, D8).

### 4.2 Papéis de usuário

Papéis são **Groups do Django** com permissões, nunca campo de texto solto.

| Papel | Quem | Pode |
|---|---|---|
| `administrador` | ASA | tudo, incluindo gestão de usuários e da tabela de regras |
| `crm` | ASA | criar operação, enquadrar, triagem de documentos (etapa 1), registrar boletagem |
| `compliance` | ASA | due diligence, consulta Trillia, aprovar/reprovar (etapa 2) |
| `juridico` | ASA | revisão de documentos e vigência, aprovação final (etapa 4) |
| `clube` | Corinthians | criar operação, subir documentos da contraparte, upload para assinatura (etapa 5) |

**Risco/Crédito (etapa 3) não tem usuário próprio no MVP.** A etapa é criada normalmente
quando o enquadramento exige, e funciona como **aprovação manual**: decisão
(aprova/reprova) + **campo de parecer obrigatório** + anexo opcional do estudo de crédito.
Quem registra é `crm` ou `compliance`, em nome do time de Risco. Quando o time entrar
como usuário, vira um grupo de permissão novo — a modelagem não muda (§7, D9).

**Sem IA nesta etapa.** A análise de crédito depende de balanço/DRE, que só é exigido nos
enquadramentos maiores — no piloto não existe insumo. Como a IA já extrai dados do balanço
no pipeline documental, um parecer automático pode ser acrescentado depois sem alterar a
modelagem. Não antecipe isso.

O papel `clube` é externo à ASA. Toda tela e toda queryset precisa considerar que esse
usuário **não pode** ver operações que seu time não criou, pareceres internos, comentários
internos, nem o resultado bruto da consulta de compliance.

### 4.3 Fluxo piloto do MVP

**Aluguel de Espaço — Evento até R$ 5.000,00.**

Escolhido porque exerce **todas as seis colunas da matriz de alçadas** com a menor lista
de documentos, validando o caminho completo com o menor esforço.

- Alçadas: Triagem CRM, Compliance (DD), Risco/Crédito, Jurídico ASA/Genial,
  Assinaturas, Boletagem & Liquidação — todas obrigatórias.
- Documentação: **Kit Cadastral PJ** + *Contrato entre o Fundo e o Cessionário*.

Nada além disso é implementado como regra até validação. O motor é genérico; a tabela
de regras começa com uma linha.

### 4.4 Enquadramento: o coração do sistema

O enquadramento (tipo de operação + critério, normalmente faixa de valor) determina
**simultaneamente** duas coisas: as etapas obrigatórias e a lista de documentos exigidos.

**Isso é dado em tabela, não código.** Nada de `if valor < 5000` espalhado por views ou
serviços. Existe uma tabela de regras consultada em tempo de execução, editável pelo
`administrador` no Admin, e as regras do guia entram como *data migration* / fixture.
Adicionar um enquadramento novo deve ser preencher linhas, não escrever `elif`.

Matriz completa do guia (referência — apenas o piloto está ativo no MVP):

| Processo | Critério | Triagem CRM | Compliance | Risco | Jurídico | Assinaturas | Boletagem/Liq. |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Aluguel de Espaço | Evento até R$ 5.000,00 | ● | ● | ● | ● | ● | ● |
| Aluguel de Espaço | Jogo ou Temporada | ● | ● | ● | ● | ● | ● |
| Reembolso para o Clube | Período anterior | ● | – | – | ● | ● | ● |
| Pagamentos (rotina diária) | Serviços emergenciais até R$ 5.000,00 | ● | – | – | – | – | ● |
| Serviços NQA | Prestadores até R$ 5.000,00/mês | ● | – | – | – | – | ● |
| Serviços NQA | Pessoa Física (PF) | ● | ● | – | – | – | ● |
| Serviços NQA | > R$ 5.000,00 e ≤ R$ 199.999,99/mês | ● | ● | ● | ● | ● | ● |
| Serviços NQA | ≥ R$ 200.000,00 | ● | ● | ● | ● | ● | ● |
| Compras / Manutenção | Até R$ 10.000,00 (**waiver**) | – | – | – | – | – | – |
| Compras / Manutenção | Até R$ 20.000,00 | ● | – | – | – | – | ● |
| Compras / Manutenção | Acima de R$ 20.000,00 | ● | ● | ● | ● | ● | ● |

Atenção aos limites, que não são uniformes: R$ 5.000,00 para serviços e pagamentos,
R$ 10.000,00 e R$ 20.000,00 para compras, e a faixa de serviços NQA fecha em
R$ 199.999,99 (a partir de R$ 200.000,00 é outro enquadramento). Use `Decimal` para
dinheiro — **nunca `float`** — e escreva teste de fronteira para cada limite, inclusive
o valor exato do limite.

O **waiver** (compras até R$ 10.000,00) dispensa documentação *e* etapas: a operação vai
direto para um estado terminal de dispensa, com registro de auditoria. Não é atalho de
código, é uma regra da tabela como qualquer outra.

### 4.5 Documentação exigida

Duas camadas, e a distinção importa:

**Camada 1 — kit cadastral, pertence à contraparte** (reaproveitado entre contratos,
§7 D10). O conjunto exigido depende de **PF ou PJ** e, para PF, também do **valor**:

*Pessoa jurídica (guia, página 2):*

- Contrato Social / Última Alteração Contratual
- Certidão de Inteiro Teor ou Simplificada — JUCESP (para São Paulo)
- Procuração (quando houver — condicional, não conta como pendência)
- Comprovante de endereço (**até 90 dias após o vencimento**)
- Documento de identificação dos representantes (RG, CPF e/ou CNH)

*Pessoa física:*

- Documento de identificação (RG, CPF e/ou CNH)
- Comprovante de residência válido
- **Acima de R$ 4.000,00**: holerite **ou** declaração de Imposto de Renda (§7, D20)

O limite de R$ 4.000,00 para PF **não vem do guia** — foi definido pelo responsável e vale
como regra de comprovação de renda. Como qualquer faixa de valor, é dado em tabela, com
teste de fronteira no valor exato.

**Camada 2 — documentos específicos, pertencem ao contrato.** Variam por enquadramento;
exemplos do guia: contrato entre Fundo e Cessionário; balanço/DRE ou declaração de
faturamento dos últimos 12 meses; nota de débito/boleto; nota fiscal; comprovante de
pagamento; descritivo do serviço; cotações; relatório de capacidade técnica; autorização
específica para prestação do serviço; contrato com NQA; CNPJ; documentação suporte;
descritivo da compra.

Consequências obrigatórias na modelagem:

- Documento cadastral tem **validade**. O sistema calcula se está vigente (comprovante de
  endereço: 90 dias) e, ao abrir uma solicitação nova, pede **apenas o que falta ou venceu**.
- **O tipo de pessoa é deduzido do documento informado no formulário** (CPF ou CNPJ), não
  perguntado ao usuário. O sistema pede o kit correspondente sozinho.
- Serviços NQA para **Pessoa Física** não usam Kit Cadastral PJ: exigem comprovante de
  endereço e documento de identificação, e são explicitamente sujeitos a DD.
- Pagamentos de rotina diária têm documentação **pós-prestação do serviço** — a operação
  legitimamente existe antes dos documentos. O modelo não pode presumir o contrário.
- A aceitação da documentação está sujeita a análise complementar de Compliance e
  Risco/Crédito: **estar completo não é estar aprovado**. São estados distintos.

### 4.6 Conferência documental (Fase 1, etapas 3 a 5)

Documento enviado entra em **fila de análise** (task Celery, nunca no request). A IA faz
OCR, extrai os campos e **devolve evidência visual de onde leu cada dado**.

**Evidência visual (D21).** O modelo retorna, junto de cada campo extraído, a coordenada
normalizada da região onde encontrou o valor. O sistema gera o **recorte da imagem** e o
guarda junto do resultado. O revisor vê o dado ao lado do pedaço do documento que o
originou — é isso que torna a conferência auditável em vez de um ato de fé.

Coordenada de modelo é aproximada e erra em documento torto, escaneado torto ou de baixa
resolução. Trate isso como caso normal: guarde a confiança, e quando ela for baixa mostre
a página inteira em vez do recorte justo. Nunca descarte o resultado por causa do recorte.

**Confronto formulário × documento.** Para cada campo comum (nome, CPF/CNPJ, endereço,
data de nascimento), compara-se o que o Clube digitou com o que o documento diz.
Divergência gera **pendência**, e pendência **trava o fluxo** — a contraparte não avança
para compliance enquanto houver pendência aberta. Também trava documento fora da validade.

Comparação tolera diferença de formatação (pontuação de CPF, maiúsculas, abreviação de
logradouro), **nunca** diferença de conteúdo. Na dúvida, gere pendência: falso positivo
custa um clique, falso negativo passa documento errado.

Duas saídas para a pendência, e o sistema precisa distinguir as duas na auditoria:

- **Erro de envio** — o Clube mandou o documento errado ou desatualizado: ele reenvia.
- **Erro de leitura da IA** — o dado no documento está certo e a extração errou: a
  **ASAROCK corrige manualmente**, registrando quem corrigiu, o valor anterior e o novo.

### 4.7 Due diligence de compliance (Fase 1, etapa 6)

**No MVP a análise é manual.** O sistema entrega ao analista os dados e os documentos
baixáveis, e coleta um parecer estruturado com evidências (prints anexados). A integração
com a Trillia entra depois, se e quando for contratada (§5.2, §7 D22).

O parecer tem campos próprios, não um campo de texto livre único — assim vira dado
auditável e comparável:

| Bloco | O que registra |
|---|---|
| Situação cadastral | CPF regular / CNPJ ativo; para PJ, CNAE compatível com o que está sendo contratado |
| Processos | judiciais e administrativos, separados por esfera: cível, criminal, trabalhista, fiscal e execuções |
| Sanções e listas restritivas | ONU, OFAC, União Europeia; e as nacionais: CEIS, CNEP, CEPIM, inidôneos do TCU, "lista suja" do trabalho escravo, CADIN |
| PEP | pessoa exposta politicamente — o titular, sócios, administradores, beneficiário final **e** familiares/relacionados próximos |
| Bloqueios e restrições | indisponibilidade de bens, restrições cadastrais |
| Mídia adversa (webcheck) | busca por palavras-chave (fraude, lavagem, corrupção, crime ambiental...) com registro dos termos usados e do que foi encontrado |
| Beneficiário final e grupo econômico | para PJ: quem controla de fato, e o grupo ao qual pertence |
| Sócios | as mesmas checagens acima replicadas nos sócios relevantes, quando PJ |
| Parte relacionada | vínculo com o Fundo, o Clube ou a gestora — conflito de interesse |
| **Veredito** | **risco baixo, moderado ou alto**, com justificativa obrigatória |

Notas de implementação:

- O veredito é **humano e obrigatório**. Sem veredito não há habilitação.
- Risco alto não bloqueia automaticamente: escala a decisão. Quem pode liberar apesar de
  risco alto é regra de governança — **pergunte, não invente** (§10).
- Cada bloco aceita evidência anexada (print, PDF), e todos ficam versionados na auditoria.
- Prazo de validade da análise: campo no modelo, **valor a definir com o compliance**
  (§7, D19). A praxe de mercado é 12 meses, com reavaliação por evento — mudança
  societária, por exemplo.
- Comunicação de operação suspeita ao COAF/UIF tem prazo legal (hoje, 24 horas). O sistema
  **não** faz essa comunicação; deve apenas registrar se ela foi feita e quando.

### 4.8 Análise de crédito (Fase 1, etapa 7)

Mesmo formato do compliance: análise manual, parecer estruturado, veredito de risco
(baixo/moderado/alto). Fonte prevista é o **Serasa**, ainda não confirmada, e a etapa só
existe **quando a matriz do guia a exige** para aquele enquadramento (§4.4).

Roda **depois** do compliance, não em paralelo: não se gasta análise de crédito em quem
vai ser barrado antes (§7, D23).

### 4.9 Análise contratual (Fase 2, etapas 10 a 12)

O formulário do contrato registra o tipo (os processos do guia) e, obrigatoriamente, se o
contrato **segue o modelo da base** ou é **documento próprio da contraparte** — comum
quando o terceiro é uma empresa grande, e é justamente o caso que exige leitura atenta.

A IA compara o contrato com o modelo e produz:

- divergências em relação ao modelo, cláusula a cláusula;
- inconsistências de dados (partes, valores, datas, vigência) contra o formulário;
- **riscos jurídicos**, sobretudo em documento próprio da contraparte;
- para cada apontamento, **o trecho do documento que o fundamenta** — nada de afirmação
  sem origem rastreável.

A maioria dos contratos é PDF nativo, com texto selecionável — OCR só é necessário quando
o arquivo for digitalizado. Detecte, não presuma.

O resultado é **insumo para o Jurídico**, que aprova ou reprova manualmente. A IA não
libera contrato.

### 4.10 Visibilidade do fluxo

Requisito de produto, não enfeite: a tela precisa mostrar, de forma simples e visual,
**o fluxo inteiro** — que etapas já passaram, qual está em andamento, quais faltam, e o
que está travado e por quê. Cada pendência aparece onde ocorreu, com o motivo.

E **toda checagem mostra quem a fez**: nome do usuário, data e hora, tanto da ASAROCK
quanto do Clube. Login é individual — não existe conta compartilhada por área.

### 4.11 Entidades principais

- **`Contraparte`** — o terceiro (PF ou PJ). **Não é usuário do sistema.** Dona do dossiê
  cadastral e da habilitação, reutilizada entre contratos.
- **`Habilitacao`** — o resultado da Fase 1 para uma contraparte: pareceres de compliance
  e de crédito, veredito de risco, quem conferiu, data e validade.
- **`ParecerCompliance`** / **`ParecerCredito`** — os blocos estruturados de §4.7 e §4.8,
  com evidências anexadas e veredito de risco.
- **`Solicitacao`** — o formulário inicial do Clube: dados do evento/serviço, dados do
  contratante e valor. É o que dispara a Fase 1.
- **`DocumentoCadastral`** — documento do kit, pertence à contraparte, com data de
  emissão/validade e cálculo de vigência.
- **`Pendencia`** — divergência ou invalidez que trava o fluxo, com origem (erro de envio
  ou erro de leitura da IA), responsável pela correção e histórico da resolução.
- **`Operacao`** — o contrato em si (Fase 2): contraparte, tipo, valor, enquadramento, e
  se segue modelo da base ou documento próprio.
- **`TipoOperacao`** e **`RegraEnquadramento`** — a tabela de regras de §4.4: critério,
  alçadas obrigatórias, exigências documentais.
- **`ExigenciaDocumental`** — que tipo de documento cada enquadramento exige e se é obrigatório.
- **`DocumentoOperacao`** — arquivo específico da operação (no S3).
- **`EtapaAprovacao`** — instância de etapa gerada para a operação a partir do
  enquadramento: área responsável, status, decisor, parecer, data.
- **`AnaliseDocumento`** — resultado da IA: tipo classificado, dados extraídos (JSON),
  inconsistências, confiança, modelo e versão do prompt.
- **`CampoExtraido`** — cada dado lido de um documento com sua **evidência visual**:
  valor, confiança, coordenada e o recorte da imagem (§4.6).
- **`ConsultaCompliance`** — resultado da consulta ao provedor externo.
- **`EventoAuditoria`** — quem fez o quê, quando (§6).

### 4.7 Estados

**`Habilitacao` (Fase 1):**

```
AGUARDANDO_DOCUMENTOS → EM_ANALISE_DOCUMENTAL → COM_PENDENCIA ⇄ EM_ANALISE_DOCUMENTAL
                     → EM_COMPLIANCE → EM_CREDITO → HABILITADA
qualquer ponto → RECUSADA
```

`COM_PENDENCIA` é estado de ida e volta: a correção (reenvio do Clube ou ajuste manual da
ASAROCK) devolve o dossiê à análise. Enquanto houver pendência aberta, **não avança**.
`EM_CREDITO` só existe quando o enquadramento exige Risco/Crédito.

**`Operacao` (Fase 2):**

```
RASCUNHO → AGUARDANDO_DOCUMENTOS → EM_APROVACAO → AGUARDANDO_ASSINATURA
        → ASSINADA → CONCLUIDA
qualquer etapa → REPROVADA
enquadramento com waiver → DISPENSADA (terminal)
```

A Fase 2 **só começa com a contraparte habilitada e a habilitação vigente**. O contrato
fica disponível para assinatura apenas quando todas as checagens passaram (§4.0).

`EM_APROVACAO` não é linear: a operação percorre as `EtapaAprovacao` que o
enquadramento gerou, na ordem do fluxo de §4.1, pulando as não aplicáveis.

**`EtapaAprovacao`:** `PENDENTE → EM_ANALISE → APROVADA | REPROVADA`, mais
`DISPENSADA` (não aplicável ao enquadramento) e `REGISTRADA_EXTERNAMENTE` (etapa 3 no MVP).

**`DocumentoOperacao` / `DocumentoCadastral`:**

```
ENVIADO → PROCESSANDO → ANALISADO → APROVADO | REJEITADO
                     ↘ FALHA_ANALISE
```

Regras que valem para todas:

- Transição só acontece **em método do modelo ou em serviço**, nunca com `.status = ...`
  na view. O método valida o estado de origem.
- Transição inválida levanta exceção de domínio; nunca falha em silêncio.
- Toda transição gera `EventoAuditoria`.
- `FALHA_ANALISE` é estado previsto, não exceção: a IA vai falhar às vezes e o usuário
  precisa poder reenviar.
- Reprovação em qualquer etapa interrompe o fluxo e exige parecer textual.

---

## 5. Integrações externas

**Regra geral:** toda integração fica atrás de uma interface em `integracoes/`, com uma
implementação real e uma falsa. Nenhum `import google.generativeai` ou chamada HTTP a
terceiro fora dessa pasta. Nenhuma chamada externa dentro do ciclo de request — sempre
task Celery.

### 5.1 IA documental (Gemini)

Gemini é multimodal: PDF, foto de RG e scan torto entram no mesmo pipeline, sem OCR
separado (nada de Tesseract/Textract). Pré-tratamento permitido: converter páginas de PDF
em imagem e comprimir.

Quatro responsabilidades:

1. **Classificar** o tipo do documento enviado (é contrato social? certidão JUCESP? NF?).
2. **Extrair** dados estruturados (CNPJ, razão social, sócios, nome, CPF, datas, valores).
3. **Validar consistência** — dados do documento contra os da contraparte e da operação;
   documento vencido; valor da NF compatível com o valor da operação.
4. **Checar completude** — quais exigências do enquadramento ainda faltam.

Obrigatório:

- Resposta **sempre em JSON validado contra schema** (Pydantic). Resposta que não valida
  = `FALHA_ANALISE`, nunca dado salvo pela metade.
- Persistir modelo, versão do prompt e resposta bruta junto do resultado — sem isso não há
  como auditar nem depurar uma decisão.
- Prompts em arquivos versionados, não embutidos no meio da função.
- **A IA nunca aprova nem reprova.** Ela produz evidência; a decisão é humana, registrada
  com nome de quem decidiu e parecer. Isso vale especialmente para DD e enquadramento —
  o enquadramento é regra de tabela, não inferência de modelo.

> ### ⚠️ Restrição LGPD — bloqueante
>
> Estamos no **free tier** do Gemini (chave do AI Studio), e o free tier **usa o conteúdo
> enviado para treinar o modelo**.
>
> **É proibido enviar documento real de pessoa real nesta fase.** Apenas dados fictícios.
>
> No free tier, os termos permitem que o Google use entradas e saídas para melhorar os
> modelos, e **revisores humanos podem ler o conteúdo**. No tier pago (API direta ou
> Vertex AI) isso não acontece: conteúdo não vai para treino e há adendo de processamento
> de dados.
>
> Antes de qualquer demonstração com dado real, ou de qualquer uso pelo Clube, é
> obrigatório migrar para a **API paga**. O código deve tornar essa troca uma mudança de
> variável de ambiente — nada mais.
> Não remova este aviso e não relaxe esta regra sem autorização explícita.

**Custo da migração, para referência** (julho/2026, por milhão de tokens): Flash-Lite
US$ 0,10 entrada / US$ 0,40 saída; Flash US$ 1,50 / US$ 7,50; Pro US$ 2,00 / US$ 12,00.
É pagamento por uso, sem mensalidade. Um documento de ~10 páginas custa cerca de
US$ 0,002 no Flash-Lite e US$ 0,03 no Flash. *Thinking tokens* são cobrados como saída;
lote tem 50% de desconto; cache de contexto reduz até 90% da entrada — relevante porque
nosso prompt de extração é quase idêntico a cada chamada.

**A interface precisa comportar um provedor local.** Está previsto rodar modelos locais
via proxy para teste e comparação (§7, D16). Portanto `ProvedorIA` é agnóstica: nada de
tipo, exceção ou parâmetro específico do Gemini vazando para fora de
`integracoes/ia/gemini.py`. As implementações previstas são `gemini`, `local` (proxy,
futura) e `fake` (testes), escolhidas por variável de ambiente.

### 5.2 Compliance (Trillia / ex-Neoway)

Pesquisa de julho/2026:

- A Neoway foi absorvida pela **Trillia B3**; a marca segue como produto.
- **A API existe e é ativa** — a página de status monitora "Neoway | API" e
  "Neoway | Plataforma" separadamente, ambas operacionais.
- Autenticação por **token Bearer**, com exemplos oficiais em Python.
- Dados relevantes para a DD: cadastrais de PF/PJ, QSA, processos judiciais, listas
  restritivas e sanções, PEP, mídia adversa, **score de risco por IA**, e mapeamento de
  grupo econômico/beneficiário final (módulo Pathfinder).
- **Bloqueio:** `developer.neoway.com.br` não resolve mais em DNS. Não há documentação
  pública de endpoints, payloads ou preços — portal aparentemente fechado a contratados.

**Portanto:** implementar `ProvedorCompliance` (interface) + `ProvedorComplianceFake`
(payload realista, usado agora) + `ProvedorComplianceTrillia` (esqueleto documentado, não
funcional), selecionados por variável de ambiente. **Não invente nomes de endpoint ou
formatos de resposta da Trillia como se fossem reais** — marque explicitamente o que é
suposição.

Pendências comerciais (não são tarefas de código): acesso ao portal do desenvolvedor,
endpoints com contrato de resposta, modelo de cobrança.

### 5.3 Assinatura eletrônica

**Fora do escopo do MVP.** A etapa 5 é o Clube fazer *upload no sistema para assinatura*;
o sistema registra `AGUARDANDO_ASSINATURA` → `ASSINADA` e permite anexar o PDF assinado.
Não integre Clicksign, D4Sign ou DocuSign nesta fase. Modele os estados de forma que a
integração encaixe depois sem migração dolorosa.

### 5.4 Arquivos (S3)

- Bucket **privado**. Nenhum objeto público, nenhuma ACL aberta.
- **A pasta de uploads nunca é servida como estático — nem em desenvolvimento.** Todo
  acesso passa por uma view que confere permissão e registra o download na auditoria
  (D28). Nada de `static(MEDIA_URL, ...)` no `urls.py`.
- **O nome no disco é um UUID**, gerado por `contrapartes.models.caminho_do_arquivo`. O
  nome enviado pelo usuário fica no banco, só para exibição: guardar
  `rg-joao-silva.jpg` no disco expõe o titular pela própria URL.
- Acesso sempre por **presigned URL de curta duração**, gerada após checar permissão.
  Nunca exponha URL direta do bucket em template.
- Chave do objeto não adivinhável (UUID, não o nome original do arquivo).
- Valide extensão, tipo MIME real e tamanho máximo **antes** de subir.
- **Limites (D18):** aceitos `.pdf`, `.jpg`/`.jpeg` e `.png`, até **25 MB** por arquivo.
  Qualquer outra extensão é recusada com mensagem clara em português. Os limites moram em
  um único ponto de configuração — nenhuma tela define o seu.
- Em dev, o mesmo código aponta para MinIO ou pasta local — a interface não muda.

---

## 6. Segurança, privacidade e auditoria

O sistema lida com documento de identidade, CPF, CNPJ, contrato e nota fiscal de terceiros
de um fundo de investimento. Não é opcional:

- **Auditoria**: toda ação relevante (criação e enquadramento de operação, upload, análise,
  consulta de compliance, aprovação, reprovação, waiver, download, mudança de estado) gera
  `EventoAuditoria` com usuário, ação, objeto, data/hora e IP. Registro de auditoria
  **nunca** é editado ou apagado.
- **Valor e tipo são imutáveis após o início do processo.** Uma vez que a operação saia de
  `RASCUNHO`, valor e tipo não podem ser editados — o enquadramento, e portanto as alçadas,
  ficam congelados. Bloqueie isso no modelo, não só na tela. Se for preciso corrigir, o
  caminho é reprovar/cancelar e abrir operação nova. Reenquadramento de operação em
  andamento é **feature futura** e não deve ser implementado agora (§7, D13).
- **Sem segredo no repositório.** Chaves, tokens e senhas só por variável de ambiente.
  `.env.example` com valores falsos; `.env` no `.gitignore`. Se encontrar segredo
  commitado, pare e avise.
- **Nunca logue** documento, dado extraído, CPF completo ou token. Log de erro carrega
  identificador do objeto, não o conteúdo.
- **Nunca commite** documento real, nem em fixture ou teste. Fixtures usam dados fictícios
  com CPF/CNPJ inválidos de propósito.
- **Nunca aponte o ambiente local para o RDS de produção.** `.env` de desenvolvimento e de
  produção são arquivos distintos e nunca compartilham credencial. Antes de qualquer
  comando destrutivo ou de migração, confira contra qual banco ele vai rodar e diga
  isso explicitamente ao responsável (§9.1). Na dúvida, pare e pergunte.
- Toda queryset de listagem filtra por permissão. Assuma que o usuário vai trocar o ID na
  URL — teste acesso direto ao objeto, não só o link na tela.
- `DEBUG = False` em produção, `ALLOWED_HOSTS` explícito, CSRF ativo, cookies `Secure`.

---

## 7. Registro de decisões

Decisões tomadas com o responsável pelo projeto. **Não reabra sem perguntar.**

- **D1 — Django em vez de FastAPI.** O Django Admin dá ao jurídico e ao compliance uma
  interface de revisão sem que a construamos, e permite editar a tabela de regras.
  Preserve isso: mantenha os modelos registrados e utilizáveis no Admin.
- **D2 — Cliente único, sem multi-tenant.** Decisão explícita, contra a recomendação
  inicial. Não existe modelo `Organizacao` e não se deve inventar um.
- **D3 — Tudo em português no código nosso**, contra a recomendação inicial de inglês
  (§3).
- **D4 — Assinatura eletrônica fora do MVP** (§5.3).
- **D5 — Gemini free tier apenas com dados fictícios** (§5.1).
- **D6 — S3 desde o dia 1**, mesmo em dev.
- **D7 — Celery + Redis** em vez de alternativa mais leve: caminho mais documentado e
  previsível; o Redis já cabe no Compose.
- **D8 — Escopo do fluxo: etapas 1 a 5.** Boletagem e liquidação (7 e 8) e envio de NFs
  (6) ficam como registro de status, sem integração com a Genial.
- **D9 — Risco/Crédito sem usuário no MVP**, registrada como aprovação manual com parecer
  obrigatório, sem IA (§4.2). Revisável quando o time de Risco entrar.
- **D10 — Dossiê cadastral único por contraparte.** Kit Cadastral PJ é reaproveitado entre
  operações, com controle de vigência; o sistema pede apenas o que falta ou venceu.
- **D11 — Um enquadramento por vez**, começando pelo piloto de §4.3.
- **D12 — Enquadramento é dado em tabela, não código** (§4.4).
- **D13 — Valor e tipo congelados após o início.** Sem reenquadramento de operação em
  andamento no MVP; correção se faz cancelando e reabrindo (§6). Feature futura.
- **D14 — Partes relacionadas: sem regra.** O guia declara a governança "em discussão".
  Não há alçada especial a implementar. Não invente uma.
- **D15 — Dados de teste espelham operações reais passadas, com conteúdo fictício.**
  A estrutura, os tipos de documento e as faixas de valor vêm de operações que de fato
  ocorreram, para que o teste tenha fidelidade; nomes, CPF/CNPJ, endereços e valores
  identificáveis são substituídos. **Nenhum documento real é enviado ao Gemini enquanto
  estivermos no free tier** (§5.1). Quem prepara e fornece essa massa é o responsável
  pelo projeto — não invente operações do nada nem presuma quais existem.
- **D28 — Documento nunca é URL pública.** Download passa por view autenticada, com
  checagem de permissão e registro na auditoria; no S3, redireciona para URL assinada de
  curta duração. Nome no disco é UUID (§5.4).
- **D24 — Endereço estruturado, com busca por CEP.** Campos separados (CEP, logradouro,
  número, complemento, bairro, cidade, UF) em vez de texto livre — sem isso o confronto
  com o comprovante de residência é frágil. A consulta usa o **ViaCEP** (público e
  gratuito) e é a **única exceção** à regra de §5: roda no ciclo de request, porque o
  usuário está esperando o preenchimento. Em troca: timeout de 4s, cache de 30 dias,
  falha silenciosa (o usuário digita à mão) e stdlib, sem dependência nova.
- **D25 — Um documento, vários arquivos.** Frente e verso do RG são o mesmo documento;
  `ArquivoDocumento` guarda cada arquivo. Exigir envios separados só piora a operação.
- **D26 — Subtipo de documento.** "Documento de identificação" aceita RG, CIN, CNH,
  passaporte e RNE/CRNM. Saber qual é torna a extração por IA mais precisa, e alguns têm
  validade própria. Cadastrável no Admin, sem deploy.
- **D27 — Data em formato brasileiro, digitável.** Campo de texto com máscara em vez do
  seletor nativo, que não aceita texto colado. Aceita `dd/mm/aaaa`; o servidor revalida.
- **D19 — Habilitação da contraparte separada da contratação.** A Fase 1 pertence à
  contraparte e é reaproveitada; um segundo contrato com o mesmo terceiro entra direto na
  Fase 2 (§4.0). **Prazo de validade da habilitação: a definir com o compliance** — o
  campo existe no modelo, sem número travado.
- **D20 — PF acima de R$ 4.000,00 exige comprovação de renda** (holerite ou declaração de
  IR). Regra do responsável, não do guia (§4.5).
- **D21 — Evidência visual por recorte automático.** A IA devolve a coordenada de cada
  campo e o sistema gera o recorte; confiança baixa mostra a página inteira (§4.6).
- **D22 — Compliance manual no MVP.** Parecer estruturado com evidências, sem integração
  externa. A contratação da Trillia ainda está em avaliação por causa do custo; fontes
  públicas gratuitas cobrem boa parte das listas (§4.7).
- **D23 — Crédito roda depois do compliance**, e apenas quando a matriz do guia exige
  Risco/Crédito para aquele enquadramento (§4.8).
- **D18 — Upload: PDF, JPG e PNG, até 25 MB.** Cobre contrato digitalizado, certidão e
  foto de documento tirada no celular (§5.4). Formatos de escritório (DOCX, XLSX) ficam
  fora: exigiriam conversão antes da IA.
- **D17 — Python 3.11 em todos os ambientes.** O venv de desenvolvimento é 3.11 e o
  Dockerfile foi alinhado a ele; `target-version` do ruff idem. A máquina do responsável
  tem 3.11 e 3.14 — o 3.14 não é suportado pelo Django 5.2. Ao mudar de versão, mude nos
  três lugares de uma vez.
- **D16 — Provedor de IA local previsto.** Haverá proxy para testar modelos locais e
  comparar com o Gemini. A interface `ProvedorIA` é agnóstica desde já; nenhum detalhe do
  Gemini vaza para fora da sua implementação.

---

## 8. Como escrever o código

### Organização

```
manage.py                   raiz, por convenção do Django; acrescenta src/ ao path
AGENTS.md CLAUDE.md README.md
pyproject.toml              ruff + pytest
.env.example                modelo de variáveis (o .env nunca é commitado)

config/                     INFRAESTRUTURA (não confundir com o projeto Django)
    Dockerfile
    docker-compose.yml
    requirements/
        base.txt            dependências de execução
        dev.txt             inclui base + pytest e ruff

docs/                       documentação de negócio e material de referência

src/                        todo o código da aplicação
    arena/                  projeto Django: settings, urls, celery, wsgi/asgi
    contas/                 usuário, papéis, permissões
    auditoria/              EventoAuditoria
    documentos/             TipoDocumento, DocumentoOperacao, upload, storage
    contrapartes/           Contraparte, DocumentoCadastral, vigência
    operacoes/              Operacao, RegraEnquadramento, EtapaAprovacao, estados
    analise/                AnaliseDocumento, tasks, prompts
    compliance/             ConsultaCompliance, tasks
    integracoes/
        enderecos.py        busca de CEP (ViaCEP), síncrona por exceção — D24
        ia/                 interface + gemini + local + fake
        compliance/         interface + trillia (esqueleto) + fake
        armazenamento/      interface + s3 + local
    templates/              base + por app
    static/                 css, js

tests/                      testes transversais; testes de app ficam no app
```

O projeto Django chama-se **`arena`**, não `config` — a pasta `config/` na raiz é de
infraestrutura. `DJANGO_SETTINGS_MODULE` é `arena.settings`, e o `manage.py` insere
`src/` no `sys.path`. Comandos de Docker apontam para o arquivo:
`docker compose -f config/docker-compose.yml ...`.

### Regras

- **View fina, modelo/serviço gordo.** View recebe request, chama serviço, devolve
  resposta. Regra de negócio não mora em view nem em template.
- Um app, uma responsabilidade. Se você está prestes a importar tudo de todo mundo, a
  fronteira está errada — pergunte antes de reorganizar.
- **Dinheiro sempre `Decimal`**, nunca `float`. Comparação de faixa precisa de teste de
  fronteira no valor exato do limite.
- **Type hints** em serviço e integração; dispensável em view trivial.
- Docstring curta onde o *porquê* não é óbvio. Não documente o óbvio.
- Comentário explica decisão, não mecânica.
- `select_related`/`prefetch_related` em listagem — único cuidado de performance exigido
  de antemão, porque o N+1 aparece rápido na tela de dossiê.
- Migrations commitadas junto da mudança de modelo. Nunca edite migration já aplicada em
  produção. Regras do guia entram como data migration.
- Erro esperado (arquivo inválido, IA falhou, provedor fora do ar) vira mensagem clara em
  português na tela. Traceback não chega ao usuário.

### Formatação brasileira

Toda data e todo valor exibidos seguem o padrão nacional: **`31/07/2026`** e
**`R$ 1.234,56`** — separador de milhar por ponto, decimal por vírgula, sempre duas casas.
Data com hora: `31/07/2026 14:30`.

Use um **filtro de template único** para cada caso (`|moeda`, `|data_br`), definido uma vez
em `templatetags`. Não formate valor no meio da view, não use `f"R$ {valor}"` espalhado
pelo código e não confie no locale do servidor, que pode variar entre a EC2 e a máquina
local. Na entrada de dados, aceite o que o usuário digitar no padrão brasileiro e converta
para `Decimal` num único ponto do código.

### Identidade visual

O sistema será visto pelo Clube. "Apresentável" aqui significa **coerente**, não elaborado.

- Defina paleta, tipografia e escala de espaçamento como **variáveis CSS** em um único
  arquivo, e use só elas. Nada de cor ou tamanho escrito direto no meio de um componente.
- Paleta sóbria e institucional, com neutros dominando e cor reservada para estado
  (pendente, aprovado, reprovado) — o sistema é ferramenta de trabalho, não vitrine.
  **Não use as cores do Corinthians**: é sistema da ASAROCK para gerir o fundo, e imitar a
  identidade do clube confunde de quem é a ferramenta.
- Estado precisa ser distinguível **sem depender só de cor** (ícone ou texto junto do
  badge). Parte dos usuários não distingue vermelho de verde, e é uma tela de aprovar
  e reprovar.
- Uma única tabela, um único formulário, um único badge de status, reutilizados. Se você
  está escrevendo o terceiro estilo de tabela, pare e reutilize o primeiro.
- Densidade alta: são usuários que passam o dia na ferramenta. Prefira listagem compacta
  e legível a cartões grandes e espaçados.

### Testes

Cobertura total não é meta nesta fase. Teste **obrigatoriamente**:

- **enquadramento**: cada critério da matriz, com teste de fronteira nos limites
  (R$ 5.000,00, R$ 10.000,00, R$ 20.000,00, R$ 199.999,99 / R$ 200.000,00);
- **geração de etapas** a partir do enquadramento, incluindo o waiver e os fluxos que
  pulam Compliance e Risco;
- **exigência documental** por enquadramento e cálculo de vigência (90 dias do comprovante
  de endereço);
- **transições de estado**, inclusive as inválidas;
- **parsing e validação da resposta da IA**, com resposta fixa gravada, sem chamar a API;
- **controle de acesso por papel**, em especial o que o papel `clube` **não** pode ver.

Nenhum teste chama serviço externo de verdade. Sempre a implementação falsa.

### Git

- Mensagem em português, imperativo: `adiciona enquadramento de aluguel de espaco`.
- Commit pequeno e coeso. Não misture refatoração com funcionalidade.
- Não commite `.env`, documento, `__pycache__`, `.venv`.

---

## 9. Regras de trabalho — obrigatórias

### 9.1 Comandos do Django são do responsável, não seus

**Nunca execute** `makemigrations`, `migrate`, `startapp`, `startproject`, `createsuperuser`,
`collectstatic`, `flush`, `loaddata`, `dbshell`, nem qualquer comando que altere banco,
estrutura de arquivos do projeto ou estado de ambiente.

Esses comandos são importantes demais para rodarem sem supervisão. O procedimento é:

1. Você escreve o código (inclusive o conteúdo de arquivos que um `startapp` geraria).
2. Você **para** e avisa, em português, exatamente qual comando precisa ser executado,
   em qual ordem, e o que se espera como resultado.
3. O responsável roda no terminal dele e devolve a saída.
4. Você segue a partir da saída real — não presuma que deu certo.

Vale igualmente para `docker compose up/down`, `pip install`, comandos de deploy e
qualquer coisa que toque a AWS. Ler arquivo, escrever arquivo, rodar `pytest` e `ruff`
sobre código local: liberado.

### 9.2 Documentar ao final de toda troca importante

Decisão tomada, regra descoberta, escopo alterado, suposição confirmada ou descartada:
**atualize o markdown na mesma sessão**, antes de encerrar. Onde:

- Decisão de arquitetura ou de negócio → `AGENTS.md`, seção pertinente **e** uma linha no
  registro de decisões (§7), numerada na sequência.
- Comando novo, mudança de ambiente, estado do projeto ou pendência → `CLAUDE.md`.
- Regra de compliance/alçada → `AGENTS.md` §4, sempre citando o guia como origem.

O objetivo é que uma sessão futura, sem nenhum histórico de conversa, consiga continuar o
trabalho lendo só os dois arquivos. Se algo importante só existe no histórico do chat,
está perdido. Documentação desatualizada é pior que ausente: se você mudou o
comportamento, corrija o texto que o descrevia.

### 9.3 Testar antes de qualquer deploy

Nada vai para a EC2 sem `pytest` verde. O procedimento:

1. Rodar a suíte completa e mostrar a saída real.
2. Falhou? Corrigir antes de qualquer conversa sobre deploy. Não existe "deploy mesmo
   com um teste quebrado" sem autorização explícita do responsável.
3. Rodar `ruff check` e `ruff format`.
4. Só então descrever os passos de deploy — para o responsável executar (§9.1).

Se você alterou comportamento coberto por teste, o teste é atualizado no mesmo commit.
Nunca apague nem marque `skip` num teste para fazer a suíte passar; isso é defeito
escondido, não teste corrigido.

---

## 10. Comportamento esperado do agente

- **Pergunte quando a resposta muda o resultado.** Regra de negócio (alçada, documento
  obrigatório, quem aprova o quê, o que o Clube pode ver) é do responsável pelo projeto,
  não sua. Detalhe de implementação é seu — decida e siga.
- **Não invente regra de compliance.** Se não está no guia nem neste documento, pergunte.
  Alçada errada é o pior defeito possível neste sistema: aprova o que não deveria.
- **Não expanda escopo.** Estamos em MVP, com um enquadramento ativo. Viu melhoria fora do
  pedido? Mencione em uma linha e siga com o que foi pedido.
- **Não invente contrato de API externa**, sobretudo da Trillia (§5.2).
- **Não relaxe §5.1 nem §6** por conveniência.
- **Relate o que de fato aconteceu.** Teste falhou, diga que falhou e mostre a saída.
  Pulou uma parte, diga qual e por quê.
- Ao terminar, informe em português o que mudou e o que ficou pendente.
