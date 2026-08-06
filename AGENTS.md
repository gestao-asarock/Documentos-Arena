# AGENTS.md — Portal de Documentação do FII ARENA

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

> ### 🎯 Prioridade em vigor: o fluxo primeiro, a integração depois
>
> **Decisão do responsável em 04/08/2026 (D42). Vale sobre qualquer outra sugestão de
> ordem de trabalho.**
>
> O foco é **100%** em deixar o fluxo interno funcional e robusto — cadastro, kit,
> triagem, pareceres, contrato, estados, permissões, telas. Só depois disso entram as
> integrações externas: **IA documental, API de compliance (Trillia) e Serasa**.
>
> Por quê: integração é a parte que mais muda e a que menos controlamos — contrato de
> API, cota, preço, disponibilidade. Amarrar o fluxo a ela antes de o fluxo estar firme
> significa refazer os dois. Um fluxo sólido com decisão manual **já é demonstrável**;
> uma integração sobre fluxo instável não é.
>
> Na prática, enquanto esta prioridade valer:
>
> - Não abra frente nova de integração externa, nem "só o esqueleto".
> - Achou um problema de fluxo no meio de outra coisa? Ele tem precedência.
> - Trabalho de integração já feito fica **em branch**, não na `main` (§9.4).
> - As interfaces em `integracoes/` continuam valendo como desenho (§5): quando a vez
>   delas chegar, o fluxo não deve precisar mudar para recebê-las.

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

**Cada área tem função própria e tela própria** (D34). Não são variações de "quem pode
aprovar": são etapas diferentes do processo, e o menu de cada usuário mostra só o que ele
faz. Tela de outra área responde **403**, não some apenas do menu.

| Papel | Quem | Faz | Telas |
|---|---|---|---|
| `administrador` | ASA | tudo, mais gestão de usuários e da tabela de regras | todas |
| `crm` | ASA | **triagem** dos documentos e **análise de crédito** (Serasa); registra boletagem | Triagem, Crédito |
| `compliance` | ASA | **due diligence** das pessoas envolvidas; pode ajudar na triagem | Triagem, Due diligence |
| `juridico` | ASA | **revisão dos contratos** — e só isso | Jurídico |
| `clube` | Corinthians | **envia** perfis e documentos, reenvia o que for recusado, **acompanha** o fluxo; decide apenas a assinatura | Perfis, Contratos |

O Clube **não interfere**: não aprova documento, não decide etapa de análise, não acessa
fila de trabalho interna. Ele envia, corrige o que voltar e acompanha.

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
usuário **não pode** ver pareceres internos, comentários internos, fila de trabalho de
outra área, nem o resultado bruto da consulta de compliance.

**O que ele vê é a esteira do time, não a própria caixa de entrada** (D35): perfil e
contrato abertos por qualquer pessoa da casa — inclusive pela ASAROCK, em nome dele —
aparecem para ele. Registro de alguém fora da casa, não. **Ver não é agir**: cancelar e
excluir seguem restritos a quem abriu o registro ou a alguém interno.

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
baixáveis, e coleta **o relatório da análise em PDF** mais o veredito de risco. A
integração com a Trillia entra depois, se e quando for contratada (§5.2, §7 D22).

A tela do parecer tem duas partes, nesta ordem: **Relatório** (um ou mais PDFs) e
**Conclusão** (veredito obrigatório, justificativa opcional). Ver D50.

O que o relatório precisa cobrir — é conteúdo do documento, não campo de tela:

| Frente | O que a análise precisa apurar |
|---|---|
| Situação cadastral | CPF regular / CNPJ ativo; para PJ, CNAE compatível com o que está sendo contratado |
| Processos | judiciais e administrativos, separados por esfera: cível, criminal, trabalhista, fiscal e execuções |
| Sanções e listas restritivas | ONU, OFAC, União Europeia; e as nacionais: CEIS, CNEP, CEPIM, inidôneos do TCU, "lista suja" do trabalho escravo, CADIN |
| PEP | pessoa exposta politicamente: o titular, sócios, administradores, beneficiário final **e** familiares/relacionados próximos |
| Bloqueios e restrições | indisponibilidade de bens, restrições cadastrais |
| Mídia adversa (webcheck) | busca por palavras-chave (fraude, lavagem, corrupção, crime ambiental...) com registro dos termos usados e do que foi encontrado |
| Beneficiário final e grupo econômico | para PJ: quem controla de fato, e o grupo ao qual pertence |
| Sócios | as mesmas checagens acima replicadas nos sócios relevantes, quando PJ |
| Parte relacionada | vínculo com o Fundo, o Clube ou a gestora, conflito de interesse |

Notas de implementação:

- O veredito é **humano e obrigatório**. Sem veredito não há habilitação.
- **Sem relatório anexado não há veredito**: a conclusão é recusada (D50).
- Risco alto não bloqueia automaticamente: escala a decisão. Quem pode liberar apesar de
  risco alto é regra de governança — **pergunte, não invente** (§10).
- Os relatórios ficam presos ao parecer e a conclusão fica versionada na auditoria.
- Prazo de validade da análise: campo no modelo, **valor a definir com o compliance**
  (§7, D19). A praxe de mercado é 12 meses, com reavaliação por evento — mudança
  societária, por exemplo.
- Comunicação de operação suspeita ao COAF/UIF tem prazo legal (hoje, 24 horas). O sistema
  **não** faz essa comunicação; deve apenas registrar se ela foi feita e quando.

### 4.8 Análise de crédito (Fase 1, etapa 7)

Mesmo formato do compliance, inclusive na tela (D50): análise manual, **relatório em PDF**
obrigatório, veredito de risco (baixo/moderado/alto) e justificativa opcional. Fonte
prevista é o **Serasa**, ainda não confirmada, e a etapa só existe **quando a matriz do
guia a exige** para aquele enquadramento (§4.4).

O que o relatório precisa apurar: consulta de crédito (score e fonte), restrições,
protestos e negativações, pendências financeiras, capacidade de pagamento e — só para PJ,
onde o enquadramento exigir — balanço, DRE e faturamento.

Roda **depois** do compliance, não em paralelo: não se gasta análise de crédito em quem
vai ser barrado antes (§7, D23).

### 4.9 Análise contratual (Fase 2, etapas 10 a 12)

**O contrato circula em duas peças** (verificado em contratos reais do fundo, D31):

- **Contrato-mãe** — *Instrumento Particular de Cessão Onerosa de Uso de Espaço*. Modelo
  base, **igual em todas as operações do mesmo tipo**, sem nenhum dado de cliente: onde
  entraria a identificação está escrito `[QUALIFICAÇÃO DA PARTE PREVISTA NO TERMO DE
  ADESÃO]`. Vem em PDF porque não deve ser editado.
- **Termo de Adesão** — o que muda a cada operação: nome, CPF, RG, endereço, telefone,
  e-mail, data, horário, valor e vencimento. Vem em DOCX porque é preenchido a cada caso.
  **É gerado pelo Clube**, não pelo sistema.

As partes são **três**: o Fundo (ARENA FII, representado pela Genial) cede e recebe; o
Corinthians entra como *interveniente anuente*, na condição de operador da arena; e o
Cliente é a contraparte.

**A análise jurídica do piloto é conferência de campos**, não leitura de cláusulas: o
Termo de Adesão precisa repetir exatamente o que foi registrado na operação — nome,
CPF/CNPJ, RG, endereço, valor, data e horário. Divergência em qualquer um deles muda o
negócio. O contrato-mãe não é reanalisado a cada operação; ele só é confrontado com o
modelo quando a contraparte apresenta **documento próprio** em vez do padrão.

Atenção a uma cláusula: **alteração de data implica multa de 50%** do valor. Por isso a
data é campo de conferência obrigatória, com o alerta na tela.

Os campos conferidos ficam em `operacoes/conferencia.py`, formatados no padrão brasileiro
— comparar `R$ 1.500,00` com `1500.00` atrapalha justamente quem confere.

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

**O dossiê do contrato** (`operacoes/dossie.py`) reúne, numa tela só, tudo que foi
verificado: documentos do perfil, due diligence, crédito, documentos do contrato e as
etapas decididas — cada item abrindo para o detalhe. É o que o Clube vê antes de assinar
e o que sustenta a operação numa auditoria. O mesmo resumo aparece no perfil, ao lado de
cada contrato.

**O download só é liberado quando todas as etapas anteriores à assinatura passaram**
(`pronto_para_assinatura`). A etapa de assinatura em si permanece pendente: é ela que o
Clube cumpre ao baixar, assinar e devolver.

### 4.11 Entidades principais

- **`Contraparte`** — o terceiro (PF ou PJ). **Não é usuário do sistema.** Dona do dossiê
  cadastral e da habilitação, reutilizada entre contratos.
- **`Habilitacao`** — o resultado da Fase 1 para uma contraparte: pareceres de compliance
  e de crédito, veredito de risco, quem conferiu, data e validade.
- **`ParecerCompliance`** / **`ParecerCredito`** — o relatório em PDF (`RelatorioParecer` e
  `RelatorioCredito`) mais o veredito de risco, nas duas etapas (§4.7, §4.8, D50).
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
- **Nenhuma etapa é decidida com documentação incompleta.** O fluxo é linear: sem os
  documentos exigidos enviados **e aprovados**, `decidir_etapa` recusa e diz o que falta.
  Não basta esconder o botão — analisar o que não existe é o defeito, não o clique.

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

> **D36 a D41 estão reservadas** para a triagem por IA, que vive na branch
> `feat/triagem-ia` e ainda não foi integrada à `main` (§9.4). Não reutilize esses
> números: a branch já os usa, e renumerar depois quebraria as referências no código.

- **D42 — O fluxo vem antes da integração.** Decisão de 04/08/2026, detalhada em §1.
  Toda energia vai para o fluxo interno ficar funcional e robusto; IA documental,
  Trillia e Serasa entram **depois**, um de cada vez. Integração é o que mais muda e o
  que menos controlamos — construir o fluxo em cima dela é refazer os dois. Trabalho de
  integração já pronto fica em branch, fora da `main`, até a vez dele chegar.
- **D43 — Cadastro do perfil é todo obrigatório, com duas exceções nomeadas.** Decisão de
  04/08/2026. Campo opcional no cadastro vira pendência descoberta lá na frente, na
  triagem ou no compliance, quando corrigir custa uma volta inteira. Exceções: o
  **complemento** do endereço (a maioria não tem — exigir só produz "n/a") e os campos que
  **só existem para pessoa física** (data de nascimento e RG), escondidos e dispensados
  quando o documento é CNPJ. Quem decide PF ou PJ é o CPF/CNPJ digitado, na tela e no
  `clean` do formulário — o usuário nunca escolhe. **A exceção é dita na tela**: os dois
  campos levam o asterisco e a ajuda "obrigatório para pessoa física, não se aplica a
  CNPJ", e ao digitar um CNPJ um aviso ocupa o lugar deles. Campo que some sem explicação
  parece defeito do sistema.
- **D44 — O endereço se preenche sozinho ao completar o CEP.** Refina D24 no lado da tela.
  A busca dispara no oitavo dígito, sem exigir que a pessoa clique fora do campo; os
  campos do endereço ficam escondidos até a consulta e só então aparecem preenchidos, com
  o foco no **número**. O botão "Preencher endereço" continua na tela para repetir a busca
  e para abrir os campos à mão quando o CEP não é encontrado ou o ViaCEP não responde —
  nunca há beco sem saída. Sem JS os campos já vêm visíveis do servidor.
- **D45 — Identidade do Clube, em escala de cinza.** Decisão de 04/08/2026, que
  **reverte** a regra anterior de §8 ("não use as cores do Corinthians"). O sistema é
  operado pelo Clube e visto por ele; vestir a casa do cliente é o esperado. Mas **preto e
  branco puros não**: `#000` sobre `#fff` cansa em jornada inteira e achata a hierarquia
  entre título, texto e apoio. Os neutros são grafite (`#2b2e33`) e quase-branco
  (`#f4f5f6`). **As cinco famílias de estado continuam coloridas e intocadas** — com o
  resto em cinza elas ficam ainda mais legíveis, e é o único lugar do sistema com cor
  saturada. Como a cor deixou de distinguir link de texto, **link do corpo leva
  sublinhado, sempre**.
- **D46 — O brasão é ativo derivado, não o arquivo entregue.** O original é um JPEG cujo
  "quadriculado de transparência" são pixels de verdade: aplicado direto, vira um
  tabuleiro cinza no cabeçalho e na aba. `docs/marca/gerar.py` recorta o fundo e produz
  `src/static/img/marca.png` e `favicon.ico`. Fonte e script ficam versionados; **não edite
  os derivados à mão** — troque o original e rode o script.
- **D47 — Editar o cadastro reinicia a validação, e perfil validado não se edita.**
  Decisão de 04/08/2026. Os dados declarados são a **base da conferência**: a triagem
  compara o RG e o comprovante contra eles. Mudá-los depois faz o parecer atestar coisa
  diferente da que foi analisada. Portanto:
  - **Perfil validado (`HABILITADA`) ou cancelado não pode ser alterado.** Ele já pode
    estar sustentando contrato. Corrigir dado de contraparte validada exige uma
    revalidação explícita, que ainda não existe — pergunte antes de inventar.
  - **O CPF/CNPJ nunca é editável**, em nenhum estado. É a identidade da contraparte e a
    chave do reaproveitamento do dossiê entre perfis e contratos; trocá-lo mudaria a
    pessoa por baixo de tudo que já aponta para ela. Digitou errado: cancele e cadastre.
  - **Só os campos que os documentos comprovam** reiniciam a validação — nome, RG,
    nascimento e endereço (`CAMPOS_PROVADOS_POR_DOCUMENTO`). E-mail e telefone salvam
    direto: nenhum documento os atesta, e refazer compliance por um telefone é custo sem
    ganho.
  - **Reiniciar não apaga arquivo.** Documento aprovado volta a `ENVIADO` e reentra na
    fila da triagem; pareceres concluídos voltam a rascunho **com o texto e as evidências
    de pé**, para quem revisar corrigir em vez de redigitar nove blocos.
  - **A gravação passa por uma tela de confirmação**, no servidor, não por um
    `window.confirm`. Ela mostra **o que muda** (campo, como está, como fica) e **o que
    isso desfaz**, em números: de que etapa o perfil sai, quantos documentos perdem a
    aprovação, quais pareceres voltam a rascunho. Exige marcar a ciência para seguir, e
    "Voltar e corrigir" devolve o formulário com o que foi digitado. Confirmação de efeito
    grande é etapa do fluxo, não caixa de diálogo do navegador: precisa funcionar sem JS,
    ser legível e caber na auditoria. Alteração só de contato grava direto, sem essa tela.
  - A alteração fica **marcada na contraparte** (`data_alteracao_cadastral`,
    `alterada_por`, `campos_alterados`) — é o que explica na triagem por que um documento
    já aprovado voltou para a fila. `data_atualizacao` não serve: ela muda a cada `save()`.
- **D48 — Data de emissão obrigatória onde ela define validade, e alerta de prazo.**
  Decisão de 04/08/2026. Quando o tipo tem `exige_data_emissao`, o envio **não passa sem
  a data** — sem ela um comprovante de residência de três anos entrava como se estivesse
  em dia, e a vigência do dossiê virava ficção. Data no futuro é recusada. Documento **fora
  do prazo é aceito**, com alerta forte no envio e na tela: barrar deixaria o Clube sem
  caminho, e quem decide se aceita assim mesmo é a triagem. O prazo vem de
  `TipoDocumento.dias_validade` (90 dias para comprovante de residência) — **nunca escreva
  90 no código**. **Isto vale para o kit cadastral, não para o documento de contrato**
  (ajuste de 05/08/2026): o documento do contrato nasce agora, para este contrato, então a
  emissão é sempre hoje e não alimenta cálculo nenhum. `EnvioDocumentoContratoForm` não tem
  o campo; a vigência que interessa ali é a do contrato, decidida na revisão jurídica.
- **D49 — Travessão e ponto médio não entram na interface.** Decisão de 04/08/2026.
  Nada de `—` nem de `·` em texto que chega à tela: título, rótulo, `help_text`, `__str__`,
  mensagem, nome de tipo em tabela. Use pontuação comum, que diz o mesmo: dois pontos para
  identificar (`Perfil #5: Fulano`), vírgula ou ponto e vírgula dentro da frase, parênteses
  para aposto, barra entre cidade e UF, `|` em título de aba. Para **valor vazio**, hífen
  (`-`). Docstring e comentário ficam de fora: são texto para quem lê o código.
  `tests/test_templates.py` varre os templates e, pelo `ast`, as strings do Python que não
  são docstring — o que passa a valer também para o código que ainda não existe.
- **D60 — Nome do arquivo entregue é legível; o nome no storage continua UUID.** Decisão de
  06/08/2026. O download da etapa de assinatura entregava `a3f9c1...pdf`, e na pasta de
  quem coleta assinaturas vinte contratos viravam vinte arquivos indistinguíveis, que só se
  identificam abrindo um a um.
  - **As duas coisas não são a mesma.** O nome **no storage** é UUID porque caminho
    adivinhável é vazamento (§5.4, D28) e isso não muda. O nome **de entrega** é montado na
    hora do download, em `operacoes.dossie.nome_do_contrato`, e só existe no
    `Content-Disposition`: `contrato-8-aluguel-de-espaco-fornecedora-ficticia-2026-04-10.pdf`.
  - **O número do contrato é o que distingue**; tipo, contraparte e data são o que faz o
    nome ser lido sem abrir o arquivo. A data é a do evento, ou a de criação quando o
    enquadramento não tem evento.
  - **Sem CPF/CNPJ e sem o código da contraparte** (D59). O nome do arquivo atravessa a
    fronteira do sistema junto com o PDF: vai para pasta compartilhada, anexo de e-mail e
    backup de estação de trabalho. O que sai daqui é o mínimo (§6).
  - **No S3 quem renomeia é o bucket.** A URL assinada serve o objeto pelo nome da chave,
    então a view pede `ResponseContentDisposition` na assinatura. Sem isso o navegador
    salvaria o UUID mesmo com o nome montado do lado do Django.
  - Os outros downloads (`baixar_documento`, `baixar_relatorio`) já entregavam pelo
    `nome_original`, que é o nome com que o arquivo foi enviado. Ficam como estão.
- **D59 — Código público da contraparte, derivado do CPF/CNPJ.** Decisão de 06/08/2026.
  A contraparte ganha um identificador de doze caracteres (`K7M4-2QX9-BT5R`) para aparecer
  na tela no lugar de um número sequencial.
  - **É HMAC, não hash.** Hash puro do CPF não protegeria nada: o espaço de CPF válido é da
    ordem de 10^9 e uma tabela pré-calculada o reverte em segundos. Com **chave secreta**
    (`HASH_KEY`, no `.env`) essa tabela não existe. E isto **não é anonimização**: dois
    registros com o mesmo código são visivelmente a mesma pessoa, que é a propriedade
    desejada. O que se evita é o caminho de volta ao CPF.
  - **Fica na `Contraparte`, não no perfil.** O código é função do CPF/CNPJ, então dois
    perfis da mesma pessoa calculariam o mesmo valor e nenhum `unique` sobreviveria a isso.
    Some-se que o perfil é descartável (D57 permite recadastrar depois de cancelar, D58
    permite apagar o cancelado) enquanto a contraparte é durável, e que **contrato aponta
    para contraparte, nunca para perfil**. Perfil e contrato seguem com o `pk` sequencial,
    que é número de protocolo e não tem problema a resolver.
  - **Doze caracteres, 60 bits, base32 de Crockford** (sem I, L, O e U, que se confundem
    com 1 e 0 ao ditar). Com cem mil contrapartes a colisão fica na casa de 10^-9, e ainda
    assim seria detectada pelo `unique=True`, nunca silenciosa. Oito caracteres já dariam
    colisão perceptível; dezesseis ninguém dita ao telefone.
  - **A chave nunca rotaciona.** Girá-la trocaria o código de todas as contrapartes. Ela é
    separada da `SECRET_KEY` justamente porque aquela **pode** ser girada. Como o valor
    fica **gravado** na coluna, perder a chave custa só a capacidade de recalcular, não os
    códigos já emitidos. `HASH_KEY` vazia derruba a inicialização: com chave nula o HMAC
    continuaria funcionando e os códigos voltariam a ser deriváveis por qualquer um.
  - **Onde aparece:** detalhe do perfil, telas e filas de compliance e de crédito, e o
    Admin. **E se procura por ele** nas duas listas e no Admin, aceitando com hífen e em
    minúscula: exibir um identificador que ninguém consegue buscar seria meia
    funcionalidade. O tamanho separa código de documento, então CPF (11) e CNPJ (14) nunca
    caem na cláusula do código.
- **D58 — Poderes de correção do administrador.** Decisão de 06/08/2026, logo depois do
  D57. Fechar o cadastro duplicado tapou um bug e, com ele, a única saída que existia para
  dado errado em perfil já validado: editar estava travado pelo D47, cadastrar de novo
  passou a estar travado pelo D57, e cancelar e refazer devolve o mesmo dado, agora
  validado outra vez. Sem saída nenhuma, a próxima correção sairia por `UPDATE` no banco,
  que não passa por auditoria. O administrador (papel `administrador` ou superusuário)
  recebe duas saídas, e nenhuma delas é parte do fluxo:
  - **Apagar registro, só o que já está cancelado.** Vale para perfil e para contrato.
    Exigir o cancelamento antes não é burocracia: é o que obriga a passar pelas guardas do
    cancelamento, que recusam encerrar registro com contrato em andamento. Sem isso,
    apagar viraria atalho para furar aquelas regras.
  - **Editar cadastro que o fluxo travou**, inclusive perfil validado ou cancelado, e
    **sem reiniciar a validação**. O padrão é esse porque o caso de uso é engano de
    digitação, não invalidar análise que já correu. Quando a intenção for a oposta, uma
    caixa na tela pede a revalidação e aí a confirmação do D47 aparece normalmente.
  - **O que a exclusão leva junto.** Perfil é folha: nada aponta para ele, e a contraparte,
    o dossiê, os documentos e a habilitação **ficam** (são dela, não do cadastro, D29).
    Contrato é diferente: `EtapaAprovacao` é `CASCADE`, então **somem as etapas e o texto
    do parecer de cada decisão já tomada**. Isso é perda real e assumida; a tela conta
    quantos pareceres vão embora antes do clique. O parecer de crédito sobrevive, só perde
    o vínculo (`SET_NULL`), e os documentos também, porque são da contraparte.
  - **A trilha fica, e é o que sobra.** O evento é gravado **antes** da exclusão, com ação
    nova `EXCLUSAO_REGISTRO`, e a descrição precisa bastar sozinha: depois dela não há mais
    objeto para o `GenericForeignKey` apontar. Nenhum registro de auditoria é apagado (§6).
  - **Editar sem revalidar também vira evento**, com nome e sobrenome, e a marca de
    alteração cadastral aparece no detalhe. Documento aprovado passando a atestar dado
    diferente do que foi conferido é exatamente o tipo de coisa que não pode acontecer
    calado.
- **D57 — Um perfil por CPF/CNPJ.** Decisão de 06/08/2026. Nada impedia cadastrar duas
  vezes a mesma contraparte, e o segundo cadastro nascia **validado de graça**: a
  habilitação é da contraparte e era reaproveitada inteira (D19, D29). Ficavam duas
  esteiras para a mesma pessoa, com o mesmo dossiê, e nenhuma das duas dizia que a outra
  existia. Pior, o cadastro novo **sobrescrevia** nome, endereço e RG de uma contraparte já
  validada, sem confirmação, sem auditoria e sem reiniciar a validação: era a porta lateral
  do D47, que bloqueia a edição justamente nesse caso.
  - O cadastro passa a ser **barrado na entrada** quando já existe perfil ativo com aquele
    documento. A tela nomeia o perfil existente e leva até ele: para atualizar dados ou
    trocar documento, o caminho é o perfil que já existe.
  - **Perfil cancelado não barra.** Perfil cancelado não se edita (`pode_ser_editada`), e
    bloquear nele deixaria o documento sem caminho nenhum, nem cadastro novo nem correção
    do antigo. Cancelar e refazer continua sendo fluxo válido.
  - **O bloqueio olha a base inteira, a tela não.** `perfil_ativo_de` ignora visibilidade,
    ou bastaria não enxergar o perfil para duplicá-lo. Nomear o perfil na tela é decisão
    separada: só quando quem cadastra pode mesmo abri-lo, senão o aviso vazaria a
    existência de um registro que ela não pode listar e o link daria 404 (D35). Hoje
    `criado_dentro_da_casa` deixa todo usuário da casa ver o que a casa cadastrou, então na
    prática o aviso quase sempre traz o número; o caminho mudo existe para não depender
    disso continuar verdade.
  - `obter_ou_criar_contraparte` **não reescreve mais** contraparte que já existe: preenche
    o que estava em branco e atualiza o contato (que nenhum documento atesta). O que os
    documentos comprovam só muda pela edição do perfil, que confirma o efeito e reinicia a
    validação (D47).
  - A base tinha duplicatas de antes da regra. `python manage.py perfis_duplicados` mantém
    um perfil por contraparte e **cancela** os demais, com motivo gravado; nada é apagado.
    Sem `--aplicar` ele só relata. O comando não passa por `Solicitacao.cancelar`, de
    propósito: aquele método recusa cancelar perfil de contraparte com contrato em
    andamento, guarda que protege o **último** perfil, não o duplicado. O contrato aponta
    para a contraparte, nunca para o perfil.
  - O que o comando **não** resolve, e avisa: as filas de compliance e de crédito leem
    `Habilitacao`, não `Solicitacao`. Habilitação aberta por um perfil duplicado continua na
    fila depois de o perfil ser cancelado. Mexer nela seria inventar um parecer, então fica
    para a área.
- **D56 — Lista é ferramenta de trabalho: abas, filtros, ordenação e paginação.** Decisão de
  05/08/2026. As duas telas de entrada eram uma tabela única, sem recorte: funcionava com
  trinta registros e deixava de funcionar com trezentos, porque quem procurava um caso
  específico rolava a página e quem precisava saber **o que travou** não tinha como
  perguntar. Passam a ter: **abas por tipo de contrato** (só em Contratos), com contagem que
  respeita os demais filtros, para a soma das abas bater com a tela; **filtros** de situação,
  etapa da vez, faixa de valor, faixas de data (cadastro, evento e última movimentação),
  "sem movimento há N dias", enquadramento, documentação, quem cadastrou, tipo de pessoa e
  parte relacionada; **busca** por nome, CPF/CNPJ e número do registro, com autocomplete de
  contraparte; **ordenação** por clique no cabeçalho; e **paginação de 25**.
  Quatro regras não negociáveis:
  1. **O recorte parte do que o usuário já vê.** Todo filtro se aplica sobre
     `operacoes_visiveis_para` / `solicitacoes_visiveis_para`, nunca sobre o modelo. Filtrar
     não pode ser porta lateral para alcançar registro de outro time (D35).
  2. **Nada de filtro em Python.** Tudo o que recorta é coluna do banco. Decidir em memória
     obrigaria a carregar a lista inteira a cada página, que é o problema que se quer
     resolver, e faria a contagem descrever a página em vez da lista.
  3. **A ordem vem de lista branca.** `arena.listagem.ordenar` só aceita as chaves que a tela
     declarou; o resto da URL cai no padrão em silêncio. Sem isso, qualquer campo do modelo
     (e das tabelas ligadas) vira ordenável pela barra de endereço. O desempate final é
     sempre o id, ou duas linhas iguais trocam de lugar entre páginas e um registro some.
  4. **O estado do filtro fica na URL, e só nela.** Nada de lembrar por usuário: a URL é
     compartilhável, o botão "voltar" desfaz, e ninguém entra numa lista já recortada sem
     saber por quê.
  Duas propriedades passaram a existir **também em SQL**, e isso é dívida assumida:
  `Operacao.etapa_atual` (`operacoes/consultas.com_etapa_atual`) e
  `Solicitacao.situacao_da_validacao` (`solicitacoes/consultas.com_validacao`). São a mesma
  regra escrita duas vezes; `test_etapa_atual_anotada.py` e `test_validacao_anotada.py`
  comparam os dois caminhos e reprovam se discordarem. Ao mexer numa, mexa na outra.
  O filtro de **documentação** do contrato não recalcula a exigência documental: "falta
  documento" é o próprio `AGUARDANDO_DOCUMENTOS`, porque quem já fez essa conta foi a máquina
  de estados. As demais opções olham os documentos vinculados ao contrato.
  **O htmx entrou na `main`** por causa do autocomplete (2.0.4, servido de
  `src/static/js/`, nunca de CDN), fechando a pendência que estava aberta. As sugestões saem
  de `buscar_contrapartes_visiveis`, que deriva a permissão dos registros visíveis: sugerir
  um nome que a pessoa não pode listar já vazaria que a contraparte existe. A lista de
  destino sai de um mapa fixo (`LISTAS_COM_BUSCA`), nunca da URL.
  **A linha da tabela de lista ficou mais alta** (`.tabela--lista`, 56px): linha fina
  espremia perfil e contrato num rodapé de planilha, e o que está ali é o cadastro de uma
  pessoa e um contrato assinado. As tabelas de etapas e de conferência seguem compactas,
  porque ali comparar linhas vizinhas é o trabalho.
  **Ajuste de acabamento (mesma data), depois de ver a barra rodando.** Três coisas saíram
  dela:
  - **Campo de formulário não pertence a `.formulario`.** Toda a estilização de `input`,
    `select` e `textarea` estava presa a esse seletor, e a barra de filtros, que é outro
    contêiner, caiu no padrão cru do navegador: borda fina, canto reto, 24px de altura.
    Parecia página sem CSS, e era. As regras passaram a `:is(.formulario, .filtros)`, com a
    lista de contêineres num lugar só. **Tela nova que colete dado entra nessa lista**, em
    vez de copiar as regras ou de vestir o contêiner de `.formulario` só pelo estilo.
  - **Dois raios, por escala.** `--raio` subiu para 8px (controle, botão, pastilha) e entrou
    `--raio-caixa`, de 12px, para superfície grande: cartão, painel de filtros, tabela de
    lista e login. Canto quase reto num painel de 1200px lê como acabamento pela metade; o
    raio de um botão, aplicado àquela largura, some.
  - **Altura de controle é 44px**, e o rótulo do filtro tem o mesmo peso do rótulo de
    formulário. Densidade não pode custar a sensação de que o controle é clicável.
  **Segundo ajuste (mesma data): o painel virou dois, e a data ganhou calendário.**
  - **"Mais filtros" e "Filtros por data" abrem separados.** São oito campos de tempo, e
    quase todos ficam vazios na maioria dos dias: no meio dos demais, dobravam a altura da
    barra e escondiam o que se usa toda hora. `FiltroBase` os separa em `campos_gerais` e
    `campos_de_data`, e **"sem movimento há N dias" vai com as datas** (`campos_de_tempo`):
    é recorte de tempo como qualquer outro, e separá-lo das faixas obrigaria a procurar em
    dois lugares. Cada painel **abre sozinho quando tem filtro em vigor** e mostra a
    contagem, para ninguém precisar caçar de onde veio o recorte.
  - **O campo de data é texto com máscara e calendário, os dois.** A digitação continua
    valendo pelo motivo de D24: o seletor nativo não aceita data colada, e quem trabalha
    copiando dado de outra tela ficava sem caminho. Mas digitar nem sempre é o mais rápido,
    e o clique passou a existir: `formulario.js` põe ao lado do campo um
    `input[type="date"]` **sem `name`**, invisível, que só abre o calendário nativo
    (`showPicker()`), e escreve de volta em dd/mm/aaaa. Quem envia continua sendo o texto:
    um segundo campo com o mesmo `name` sobrescreveria o que foi digitado. O
    `input[type=date]` some por **opacidade, não por `display: none`** (assim escondido o
    `showPicker()` do Chrome levanta erro), e sem JavaScript sobra o campo de texto inteiro.
    Vale para **todo** campo `data-mascara="data"` do sistema, não só para os filtros.
  - **Correção junto:** `campos_avancados` passou a excluir também `campos_fora_da_contagem`.
    O tipo de contrato aparecia três vezes na mesma página com o mesmo `name` (aba, campo
    escondido e select do painel), e o select sobrescrevia a aba escolhida.
- **D55 — Documento fora do prazo avisa, não barra: quem decide é a triagem.** Decisão de
  05/08/2026, a partir de um caso real. Um comprovante de residência de 189 dias foi
  enviado (com o alerta de D48), o CRM o conferiu e **aprovou de propósito** — era um caso
  retroativo, já ocorrido, e o comprovante da época serve. Mesmo assim o documento voltou
  para "precisa de correção", em vermelho, com o rótulo "Aprovado" ao lado: `esta_vigente`
  exigia estar dentro do prazo, então o dossiê desfazia em silêncio o parecer que acabara
  de ser dado, e o perfil não saía da triagem. **O vencimento é insumo da decisão, não a
  decisão.** Aprovar um documento já vencido grava `prazo_dispensado` em
  `DocumentoCadastral`, e `esta_vigente` passa a ser "aprovado, e dentro do prazo **ou**
  dispensado". A dispensa é do ato de conferir: documento que vence **depois** de aprovado
  continua virando pendência (é o que sustenta a revalidação de D19), e rejeitar limpa a
  marca, para que uma nova aprovação avalie o prazo de novo. Antes da decisão o documento
  vencido fica **em análise**, não em "precisa de correção" — chamá-lo de problema
  antecipava o parecer de quem tria. O aviso continua em toda parte: no envio, na tela de
  conferência (dizendo que aprovar aceita assim mesmo) e junto do documento aprovado
  ("aceito fora do prazo"). Nada disso vale para o **kit vencer por tempo** depois de
  habilitada a contraparte: ali quem manda é D19 e o prazo da habilitação (P5).
- **D54 — Ler o documento e levá-lo para assinar são downloads diferentes.** Decisão de
  05/08/2026. A tela de assinatura passou a listar os **documentos enviados pelo Clube**,
  baixáveis como foram enviados (`operacoes:baixar_documento`). Esse caminho é de leitura e
  **não cumpre etapa alguma**; quem cumpre a etapa 5 continua sendo `baixar_para_assinatura`,
  que converte o DOCX em PDF e registra quem levou o contrato e quando (D33). Manter os dois
  no mesmo botão obrigava a cumprir a etapa só para conferir o que estava sendo assinado.
  A lista traz **duas seções**: os documentos deste contrato e o **kit cadastral do perfil**,
  que é da contraparte e vale para os contratos seguintes (D29) — quem assina precisa poder
  ver com quem está contratando, não só o termo. Por isso `baixar_documento` confere que o
  arquivo é **da contraparte daquele contrato**, e não que pertence ao contrato;
  `baixar_para_assinatura` continua restrito aos arquivos do contrato. Os dois vão para a
  auditoria (§5.4, §6).
- **D53 — Aprovar a revisão jurídica exige conferir todos os campos.** Decisão de
  05/08/2026. As caixas do "o que conferir" eram enfeite: não iam no formulário e ninguém
  as validava, então dava para aprovar sem olhar campo nenhum — e a tela ainda dizia que
  elas "não são salvas". Agora vão como `confere=<chave>` e o **servidor** recusa a
  aprovação enquanto faltar alguma, nomeando o que falta. Cada `CampoConferencia` tem
  `chave` própria (não índice: a lista muda de tamanho conforme a operação tem data,
  horário ou RG). **Reprovar não exige marcação alguma** — reprova-se justamente porque um
  campo não confere. As marcações não são persistidas: elas provam o gesto no momento da
  decisão, e o que fica registrado é o parecer.
- **D52 — Cada área decide no posto de trabalho dela, não na tela da operação.** Decisão de
  05/08/2026. A revisão jurídica ganhou tela própria (`/juridico/<id>/`), no molde da
  triagem do CRM: o documento baixável ao lado dos campos a conferir, e o parecer logo
  abaixo. A tela da operação é **painel de acompanhamento** — mostra onde o contrato está e
  aponta o caminho ("Abrir revisão jurídica"), mas não decide por ninguém. O formulário
  genérico de decisão continua ali para as etapas que ainda não têm tela própria; quando
  ganharem, saem de lá também. Download do arquivo confere que ele é **daquele contrato** e
  vai para a auditoria (§5.4, §6).
- **D51 — O documento do contrato não passa por triagem: quem o confere é a revisão
  jurídica.** Decisão de 05/08/2026, a partir de um impasse real. As etapas do contrato
  exigiam documentação **aprovada** para poder ser decididas, mas nenhuma área tinha a
  atribuição de aprovar o Termo de Adesão: a triagem (etapa 1) chega cumprida da
  habilitação, e a conferência do termo é literalmente o trabalho da etapa 4. O contrato
  travava dizendo "aguardando conferência" para todo mundo, inclusive jurídico e
  administrador, e sumia da `fila_juridica`. Agora o que destrava as etapas é
  `Operacao.documentacao_entregue` (nada faltando, nada recusado), e **aprovar a revisão
  jurídica aprova os documentos que ela acabou de conferir** — sem isso eles ficariam
  "enviados" para sempre e a assinatura, que exige `documentacao_completa`, nunca abriria.
  Recusar devolve o contrato para `AGUARDANDO_DOCUMENTOS`. O que a linearidade impede
  continua valendo: revisar contrato **inexistente** (§4.7, §4.9).
- **D50 — A due diligence é o relatório, não um formulário de nove campos.** Decisão de
  05/08/2026. O analista já produz o relatório fora daqui; redigitá-lo bloco a bloco na
  tela não acrescentava dado nenhum e alongava a página. Saíram os nove campos de
  "Verificações" e o "Termos pesquisados"; a **justificativa virou opcional**, porque o
  documento anexado já sustenta o veredito. O que entrou: **Relatório**, um ou mais PDFs
  (só PDF — print de tela não é relatório), **acima** da Conclusão na tela, sem campo
  "Bloco". **Sem pelo menos um relatório anexado, `concluir_parecer` recusa o veredito** —
  decisão sem lastro documental não fecha. **O crédito (§4.8) seguiu o mesmo desenho** em
  05/08/2026: saíram os cinco blocos e a caixa "registrado em nome do time" (sempre
  verdadeira enquanto Risco não for usuário — D9; o campo continua no modelo). Relatório
  anexado por engano se remove enquanto o parecer é rascunho; concluído, não sai, porque
  virou o lastro do veredito (§6). Migrations `compliance/0002` e `credito/0004` apagam as
  colunas de texto: reverter recria os campos vazios.
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
- **D35 — O Clube enxerga a esteira do time, não a própria caixa de entrada.**
  Resposta à antiga pergunta P4. A queryset do papel `clube` inclui tudo que foi aberto
  por alguém **da casa** — ASAROCK ou Clube —, e não apenas o que o usuário logado criou.
  Motivo concreto: perfil ou contrato cadastrado pela ASAROCK (inclusive pelo
  administrador, para corrigir algo à mão) sumia da tela do Clube, que não tinha como
  saber que existia nem como operá-lo. O filtro está em `contas/consultas.py` e cobre
  explicitamente o superusuário, que costuma não ter grupo nenhum.
  **Ver não é agir:** cancelar e excluir continuam restritos a quem abriu o registro, ou
  a alguém interno (`permissoes.eh_dono_ou_interno`). Enviar documento é liberado ao
  time, porque enviar é a função do Clube e o perfil é do time.
  O filtro **falha fechado**: papel externo futuro que não esteja em `PAPEIS_DA_CASA`
  não passa a ver nada por descuido. Segue valendo que o Clube não vê parecer interno,
  fila de trabalho nem resultado bruto de compliance — isso é barrado por papel na view.
- **D34 — Uma área, uma função, uma tela.** CRM: triagem + crédito, em filas separadas.
  Compliance: due diligence (e triagem, se quiser ajudar) — **não faz crédito**, porque
  são análises distintas. Jurídico: só revisão de contratos, com fila própria. Clube:
  envia e acompanha (§4.2). O menu reflete isso, e as views recusam quem não é da área.
- **D32 — DOCX aceito só nos documentos de contrato.** O Termo de Adesão vem em Word;
  o kit cadastral continua PDF/JPG/PNG, porque ninguém tem RG em Word. A validação
  confere o conteúdo: zip qualquer não passa por DOCX — precisa ter `word/document.xml`.
- **D33 — Conversão DOCX → PDF com LibreOffice headless.** Instalado na imagem
  (`libreoffice-writer`), é o padrão para conversão fiel e roda no EC2. Nenhuma
  alternativa em Python puro preserva a formatação de um contrato. Quando o executável
  não existe — Windows de desenvolvimento —, a conversão **falha com aviso**: nunca
  entregue um `.docx` dizendo que é PDF. O resultado é guardado em
  `ArquivoDocumento.pdf_convertido` e reaproveitado nos downloads seguintes.
- **D31 — Contrato = modelo base + Termo de Adesão.** O modelo é fixo por tipo de
  operação; o termo, gerado pelo Clube, carrega os dados do caso. A análise jurídica do
  piloto confere se o termo reflete a operação (§4.9). O sistema **não gera** o termo.
- **D29 — Perfil da contraparte separado do contrato.** O cadastro (`Solicitacao`) reúne
  só o que é da pessoa: identificação, contato, endereço e os **documentos base** por
  PF/PJ. Nada de evento, data ou valor — esses são do contrato. Validado o perfil, ele
  serve a **quantos contratos vierem**, enquanto os documentos estiverem vigentes.
  Documentos complementares exigidos por um enquadramento também ficam guardados no
  perfil e podem ser reaproveitados em contratos futuros do mesmo tipo.
- **D30 — Existe uma análise de crédito, e ela é do perfil.** A esteira do perfil é
  documentos → conferência → due diligence → **crédito** → validado; sem crédito o perfil
  não vira contrato. A análise é **da pessoa** (score, restrições, protestos), sem valor
  de referência. **O contrato não a refaz**: a etapa 3 nasce como "cumprida na
  habilitação", junto com triagem e due diligence. Se for preciso reavaliar — porque o
  valor pulou de faixa, por exemplo —, isso é uma **revalidação do perfil**, não uma
  etapa do contrato. Ao contrato restam a revisão jurídica e a assinatura.
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

Toda data, todo valor e todo CPF/CNPJ exibidos seguem o padrão nacional: **`31/07/2026`**,
**`R$ 1.234,56`** — separador de milhar por ponto, decimal por vírgula, sempre duas casas —
e **`589.747.908-90`** / **`00.000.000/0001-91`**. Data com hora: `31/07/2026 14:30`.

O documento é **guardado só com dígitos**, de propósito: é assim que se procura e se
compara sem depender de quem digitou com ponto. A pontuação é assunto de exibição.

Use um **filtro de template único** para cada caso (`|moeda`, `|data_br`, `|cpf_cnpj`),
definido uma vez em `templatetags`. Quando o valor é montado em Python para uma tela de
conferência (`operacoes/conferencia.py`, `analise/views.py`), **chame o mesmo filtro como
função** — nunca reescreva o formato. Não formate valor no meio da view, não use
`f"R$ {valor}"` espalhado
pelo código e não confie no locale do servidor, que pode variar entre a EC2 e a máquina
local. Na entrada de dados, aceite o que o usuário digitar no padrão brasileiro e converta
para `Decimal` num único ponto do código.

### Identidade visual

O sistema será visto pelo Clube. "Apresentável" aqui significa **coerente**, não elaborado.

- Defina paleta, tipografia e escala de espaçamento como **variáveis CSS** em um único
  arquivo, e use só elas. Nada de cor ou tamanho escrito direto no meio de um componente.
- Paleta sóbria, com neutros dominando e cor reservada para estado (pendente, aprovado,
  reprovado) — o sistema é ferramenta de trabalho, não vitrine. Os neutros são o **preto e
  branco do Clube em escala de cinza**, e o brasão aparece no cabeçalho e no login
  (D45) — decisão de 04/08/2026, que **substitui** a regra anterior de não usar a
  identidade do Corinthians.
- **Cor de estado vem de um mapa único**, em `operacoes/templatetags/situacao.py`, e são
  **cinco famílias, nunca mais**:

  | Família | Cor | Quando |
  |---|---|---|
  | `sucesso` | verde | terminou bem, ou já é válido (aprovado, concluído, perfil validado) |
  | `erro` | vermelho | terminou mal (cancelado, recusado, reprovado, falha) |
  | `atencao` | âmbar | travado esperando correção (pendência, documento vencido) |
  | `andamento` | azul | em curso, seguindo o fluxo |
  | `neutro` | cinza | não se aplica (dispensado, registrado externamente) |

  Nunca escreva `estado--<cor>` decidindo a cor no template: use
  `{% include "operacoes/_situacao.html" %}`. **Status novo entra no mapa** — há teste que
  falha se algum ficar de fora, porque foi assim que "Perfil validado" e "Cancelado"
  acabaram com a cor de "em andamento".
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

### 9.4 Integração fica em branch enquanto a prioridade for o fluxo

Enquanto D42 valer (§1), a `main` carrega **o fluxo**, e cada integração externa vive na
sua própria branch até ser chamada. Nada de deixar meia integração na `main` "só para não
perder": ela vira peso morto que todo mundo precisa entender e nenhum teste exercita de
verdade.

Branches em espera hoje:

| Branch | O que traz | Estado |
|---|---|---|
| `feat/triagem-ia` | Triagem de identificação e comprovante por IA, com evidência visual e conferência campo a campo pelo CRM. Decisões D36 a D41. | Completa e testada (314 testes verdes na época), **fora da `main`** |

Ao retomar uma dessas branches: rebase sobre a `main` do momento, rode a suíte inteira, e
só então converse sobre merge. Se algo daquela branch for **correção de fluxo** e não
integração — o caso do `STATUS_EM_ANALISE` em `feat/triagem-ia` —, isso pode e deve vir
para a `main` antes, num commit próprio e separado.

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
