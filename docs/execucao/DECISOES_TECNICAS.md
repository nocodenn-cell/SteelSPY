# DECISÕES TÉCNICAS (ADR) — Sprint de Engenharia 0

> Registro de decisões arquiteturais e operacionais desta sprint. Formato: contexto → decisão →
> consequência → alternativa rejeitada.
>
> **Escopo:** apenas decisões tomadas nesta sprint. Decisões de produto anteriores (RF-DETR
> Apache-2.0, proibição de YOLO, gate comercial) permanecem válidas em
> `docs/roboflow/` e `docs/comercial/`.

---

## ADR-001 — Executar operações bloqueadas pelo sandbox **com autorização explícita**

**Status:** APROVADO pelo usuário (aprovação concedida no decorrer da sprint)

**Contexto.** O `pwsh` falhava antes de executar qualquer comando
(`SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)`). Após reparo de ACL (ver `EVIDENCIAS.md`
E1), o shell passou a executar, mas **escritas em subpastas do workspace continuam negadas**: a
concessão de escrita do sandbox (`S-1-4-…`) foi aplicada apenas à raiz, sem herança, e o processo
confinado carrega SID restrito.

**Decisão.** Para as operações que o confinamento bloqueia (criar `.venv`, instalar dependências,
acessar Docker), executar **fora do confinamento**, com aprovação pontual do usuário, uma operação por
vez, com justificativa em linguagem simples.

**Consequência.**
- ✅ Baseline obtido; ambiente reproduzível.
- ✅ Nenhum controle de segurança contornado: a elevação é solicitada, não presumida.
- ⚠️ Cada comando de escrita exige aprovação — custo de fricção aceito.
- ⚠️ O reparo de ACL alterou permissão do diretório raiz, **com backup e comando de reversão
  registrados** (`C:\Naturecode\dsh-acl-reports\`).

**Alternativa rejeitada.** Rodar o script de diagnóstico elevado (UAC/`runas`) — proibido pelo
procedimento e desnecessário: o problema não era privilégio, era `WRITE_OWNER` ausente.

---

## ADR-002 — Ambiente isolado em `backend/.venv`, nunca no Python global

**Status:** IMPLEMENTADO e TESTADO

**Contexto.** O Python global tinha 7 pacotes (só `pillow` relevante). Instalar as 33 dependências
globalmente contaminaria outros projetos da máquina.

**Decisão.** Criar `backend/.venv` e instalar ali as dependências **declaradas pelo projeto**.

**Consequência.**
- ✅ Isolamento; reversível apagando a pasta.
- ✅ `backend/.gitignore` já contém `.venv/` — não polui o repositório.
- ✅ `pip freeze` congelado em `baseline_freeze.txt` (33 pacotes) para reprodutibilidade.

**Alternativa rejeitada.** `pip install --user` ou global — não reversível de forma limpa.

---

## ADR-003 — `tzdata` entra como *workaround de ambiente*, não como correção de código

**Status:** TESTADO (workaround) · correção em `requirements.txt` **BLOQUEADA aguardando aprovação**

**Contexto.** A suíte não coleta (`ZoneInfoNotFoundError`). `tzdata` não está declarado.

**Decisão.** Instalar `tzdata` **apenas no `.venv`** para obter o baseline. **Não** alterar
`requirements.txt` nesta sprint, porque alterar dependência do produto exige aprovação e a sprint está
na etapa de baseline (A/B do plano de execução).

**Consequência.**
- ✅ Baseline obtido (69/69).
- ⚠️ O repositório continua não executável out-of-the-box — **defeito registrado, não corrigido**.
- ⚠️ Quem clonar e rodar `pytest` verá a mesma falha até P-01 ser aprovado.

**Por que não corrigir agora.** Alterar `requirements.txt` é mudança de produto. A regra da missão é
não ultrapassar gates de autorização. Registrar o defeito com prova é mais valioso do que corrigi-lo
sem autorização.

---

## ADR-004 — PostgreSQL de teste em container efêmero com imagem **já local**

**Status:** PLANEJADO (viabilidade TESTADA)

**Contexto.** `psql` não existe na máquina. Docker existe e funciona (fora do confinamento), engine
linux. Imagens `postgres:16-alpine`, `postgres:17-alpine` e `postgres:17` **já estão baixadas**.

**Decisão.**
1. Testes de integração da Fase 0 usam **container efêmero**, criado e destruído pelo fixture.
2. Imagem `postgres:16-alpine` (já presente) — **sem download**, sem custo.
3. Nome exclusivo: `stellspy-test-pg`; porta alta e isolada (ex.: 55432).
4. **Nunca** reutilizar containers de outros projetos em execução na máquina.

**Consequência.**
- ✅ RLS, `jsonb`, `INET`, `SKIP LOCKED` funcionam de verdade — SQLite não serviria.
- ✅ Custo R$ 0 e nenhum download.
- ⚠️ Requer execução fora do confinamento (named pipe).
- ⚠️ **Risco registrado:** a máquina hospeda `venddi-pg` e uma pilha `supabase_*_venddi-*` de outro
  projeto. Os fixtures devem operar apenas no container próprio; qualquer comando destrutivo deve
  validar o nome do container antes de executar.

**Alternativa rejeitada.** SQLite em memória — não implementa RLS nem `FORCE ROW LEVEL SECURITY`, o que
tornaria os testes de isolamento da Fase 0 **falsos positivos**.

---

## ADR-005 — Nenhuma implementação da Fase 0 antes de commit inicial e `.gitignore`

**Status:** BLOQUEADO (aguarda aprovação)

**Contexto.** `git rev-parse HEAD` → `fatal: ambiguous argument 'HEAD'`. **Zero commits.** Tudo não
rastreado, incluindo `pwa/node_modules` (1.082 arquivos).

**Decisão.** Antes da primeira alteração de código:
1. criar `.gitignore` na raiz (node_modules, `__pycache__`, `.pytest_cache`, `.venv`, `.env`, `*.pyc`);
2. criar o **commit inicial** com o estado atual (baseline congelado);
3. só então iniciar Fase 0, em branch própria.

**Consequência.**
- ✅ Passa a existir ponto de restauração; cada entrega fica difiável.
- ✅ Impede commit acidental de 1.082 arquivos de dependência.
- ⚠️ Depende de autorização, porque cria histórico no repositório.

**Alternativa rejeitada.** Começar a implementar sem versionamento — qualquer erro seria irreversível,
violando "preservar o núcleo existente".

---

## ADR-006 — Não iniciar migração de banco antes de definir o teste de isolamento

**Status:** PLANEJADO

**Contexto.** A Fase 0 exige RLS + `FORCE ROW LEVEL SECURITY`, role de aplicação sem `BYPASSRLS`,
`SET LOCAL` por transação e função `SECURITY DEFINER` para o login antes de existir tenant.

**Decisão.** Escrever **primeiro** o teste de isolamento (incluindo o teste de mutação: remover a policy
→ o teste deve falhar) e só depois a migração. A migração é considerada "pronta" quando o teste que
prova sua ausência falha.

**Consequência.**
- ✅ Impede o cenário "RLS decorativa" (role dona das tabelas bypassa RLS silenciosamente).
- ✅ Torna o critério de aceite verificável, não declarativo.
- ⚠️ Ordem invertida em relação ao hábito (migrar primeiro) — exige disciplina.

**Alternativa rejeitada.** Migrar e "testar depois" — o teste tende a ser escrito para passar.

---

## ADR-007 — Reafirmação: RF-DETR Apache-2.0; Ultralytics/YOLO proibido

**Status:** APROVADO (herdado de `docs/execucao/LICENSING_GATE.md`)

**Contexto.** A missão reafirma a proibição. O gate de licenciamento ainda **não existe** como
automação (`LICENSING_GATE.md` §4 descreve o que deve ser criado).

**Decisão.** Manter a proibição; a criação do gate mecânico (3 camadas: estática, ambiente, revisão
humana) é pré-requisito da Trilha B, **não** da Fase 0.

**Consequência.**
- ✅ Nenhuma dependência de visão computacional foi adicionada nesta sprint.
- ⚠️ Enquanto o gate não existe, a proteção é processual (humana), não mecânica.

---

## ADR-008 — Basear o baseline em artefato congelado

**Status:** IMPLEMENTADO

**Decisão.** Registrar `backend/baseline_freeze.txt` (33 pacotes) e a saída do `pytest` como baseline
oficial desta sprint. Toda entrega futura compara contra esse artefato.

**Consequência.**
- ✅ Regressão detectável: qualquer queda de 69 testes é falha imediata.
- ⚠️ O congelamento inclui `tzdata` (workaround), o que deve ser anotado ao corrigir P-01.

---

## Resumo de status

| ADR | Assunto | Status |
|-----|---------|--------|
| 001 | Execução autorizada fora do confinamento | APROVADO |
| 002 | venv isolado | IMPLEMENTADO / TESTADO |
| 003 | `tzdata` como workaround | TESTADO / correção BLOQUEADA |
| 004 | PostgreSQL em container efêmero | PLANEJADO (viabilidade testada) |
| 005 | `.gitignore` + commit inicial antes da Fase 0 | **BLOQUEADO** |
| 006 | Teste de isolamento antes da migração | PLANEJADO |
| 007 | RF-DETR sim / YOLO não | APROVADO (herdado) |
| 008 | Baseline congelado | IMPLEMENTADO |

---

# ADRs — Correção P-16 (2026-11-03)

## ADR-009 — `response_model=None` na rota de laudo

**Status:** IMPLEMENTADO · TESTADO · commit `851da0a`

**Contexto.** `get_laudo_pdf` devolve dois tipos concretos: `RedirectResponse` (302, quando o PDF já
está em cache no Storage) e `Response` (bytes do PDF, quando não há Storage). A anotação de retorno
declarava `Response | RedirectResponse`. Até o FastAPI 0.161 isso era tolerado; a partir do 0.162 a
união é rejeitada como `response_model` e o import do módulo falha.

**Decisão.** Acrescentar `response_model=None` ao decorador da rota, mantendo a anotação de retorno
(ela documenta o comportamento e é correta). Nenhuma alteração no corpo da função.

**Consequência.**
- ✅ `app.main` volta a importar; a API sobe (evidência E12).
- ✅ Contrato HTTP inalterado (302 ou `application/pdf`); OpenAPI segue com 8 rotas.
- ✅ Documentação do retorno preservada no código.
- ⚠️ O padrão precisa ser lembrado: qualquer rota futura que devolva união de `Response` exigirá o
  mesmo parâmetro.

**Alternativas rejeitadas.**
| Alternativa | Por que não |
|-------------|-------------|
| Trocar a anotação por `-> Any` | Perde a documentação do retorno real |
| Remover a anotação | Mesmo problema, e piora a legibilidade |
| Fixar `fastapi<0.162` | Esconde o problema e trava a evolução da dependência |
| Retornar sempre `Response` (converter o 302) | Quebraria o contrato de redirect já exposto e testado |

---

## ADR-010 — Política de versões reproduzíveis (proposta, **não aplicada**)

**Status:** PROPOSTO · requer aprovação

**Contexto.** `requirements.txt` declara as 7 dependências com `>=` e **sem teto**. Foi exatamente isso
que produziu o P-16: o `pip install` de hoje resolveu `fastapi 0.162.0`, que rejeita uma construção
aceita pela 0.115. O mesmo vale para `fpdf2`, cujos parâmetros `ln=` e `dest=` já estão depreciados e
`dest=` será removido — uma quebra futura silenciosa na geração de PDF.

**Achados de compatibilidade medidos neste ambiente:**

| Pacote | Versão instalada | Observação |
|--------|------------------|------------|
| fastapi | 0.162.0 | exige `starlette`, `pydantic`, `annotated-doc`, `opentelemetry-api` |
| starlette | 1.10.0 | emite `StarletteDeprecationWarning`: usar `httpx` com `TestClient` está depreciado, recomenda `httpx2` |
| pydantic | 2.14.2 | ok |
| pydantic-core | 2.50.2 | ok |
| fpdf2 | 2.9.0 | `ln=` e `dest=` depreciados; **`dest=` será removido** |
| tzdata | 2026.6 | ok |

**Proposta — duas camadas:**

| Camada | Pacotes | Regra |
|--------|---------|-------|
| **Núcleo travado com teto de major** | `fastapi`, `starlette`, `pydantic`, `fpdf2` | `>=<versão testada>,<próximo major` |
| **Acompanham o upstream** | `uvicorn`, `sqlalchemy`, `httpx`, `psycopg2-binary`, `pytest` | `>=` como hoje |
| **Registro por release** | todas | `baseline_freeze.txt` atualizado a cada release = lock efetivo |

Valores sugeridos (não aplicados):

```
fastapi>=0.162.0,<1.0
starlette>=1.10.0,<2.0
pydantic>=2.14.0,<3.0
fpdf2>=2.9.0,<3.0
```

**Consequência esperada.**
- ✅ P-16 não se repete com outra dependência de framework.
- ✅ Quebra de major passa a ser decisão consciente, não acidente de `pip`.
- ⚠️ Tetos impedem correções de segurança automáticas — exige revisão trimestral.
- ⚠️ `starlette` é dependência transitiva de `fastapi`; declará-la explicitamente cria risco de
  conflito. **Recomendação:** usar apenas como *restrição* (`constraints.txt`), não em
  `requirements.txt`.

**Não aplicado nesta sprint** porque a autorização de P-16 tinha escopo limitado e a missão proíbe
"upgrades generalizados" e alterações além do escopo. Fica como P-18.

---

## Resumo de status (atualizado)

| ADR | Assunto | Status |
|-----|---------|--------|
| 001 | Execução autorizada fora do confinamento | APROVADO |
| 002 | venv isolado | IMPLEMENTADO / TESTADO |
| 003 | `tzdata` como workaround | RESOLVIDO em P-02 |
| 004 | PostgreSQL em container efêmero | PLANEJADO (viabilidade testada) |
| 005 | `.gitignore` + commit inicial | CONCLUÍDO |
| 006 | Teste de isolamento antes da migração | PLANEJADO |
| 007 | RF-DETR sim / YOLO não | APROVADO (herdado) |
| 008 | Baseline congelado | IMPLEMENTADO |
| **009** | **`response_model=None` na rota de laudo** | **IMPLEMENTADO / TESTADO** |
| **010** | **Política de versões com teto** | **PROPOSTO — aguarda aprovação** |
