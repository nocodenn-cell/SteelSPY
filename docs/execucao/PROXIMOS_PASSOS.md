# PRÓXIMOS PASSOS

> Ordem de execução derivada do estado real medido em `STATUS_EXECUCAO.md`.
> Cada ação tem verificação objetiva. Nada avança sem aprovação quando indicado.

---

## 1. Bloco A — Destravar (fazer agora)

### P-01 · `.gitignore` na raiz + commit inicial — ✅ **CONCLUÍDO**

| Campo | Valor |
|-------|-------|
| Por que | **Zero commits.** Sem ponto de restauração, qualquer alteração é irreversível |
| O que | `.gitignore` criado; `git add -A` do estado original; commit inicial |
| Esforço real | 15 min |
| Verificação | ✅ `git log` mostra o commit `6668591`; `git status` limpo; **0** arquivos de `node_modules`/`.venv`/`__pycache__` no índice |
| Resultado | 117 arquivos versionados · commit `6668591d1522f5edb1c94c35bc8c5ea6b9eebd3f` |
| Estado | `IMPLEMENTADO` + `TESTADO` |

### P-02 · Declarar `tzdata` em `requirements.txt` — ✅ **CONCLUÍDO**

| Campo | Valor |
|-------|-------|
| Por que | Suíte não coletava em ambiente limpo (`ZoneInfoNotFoundError`) — confirmado por execução |
| O que | `tzdata>=2024.1` acrescentado ao `requirements.txt`, com comentário de justificativa |
| Esforço real | 5 min |
| Verificação | ✅ ambiente limpo do zero, `pip install -r requirements.txt` → `tzdata 2026.6` instalado sem intervenção manual |
| Resultado | commit `979991e1e01d28546f3d37b5f2ec8feb266dcd67` (1 arquivo, +6 linhas) |
| Estado | `IMPLEMENTADO` + `TESTADO` |

### P-16 · 🔴 **NOVO — defeito bloqueante**: `app.main` não importa

| Campo | Valor |
|-------|-------|
| Descoberto em | verificação de imports da Etapa 4 do Bloco A |
| Sintoma | `FastAPIError: Invalid args for response field!` ao importar `app.main` |
| Causa | `app/routers/conferencia.py:298` — `-> Response \| RedirectResponse` em `get_laudo_pdf`; `fastapi 0.162.0` não aceita união de `Response` como response model |
| Efeito | **A API não sobe.** Invisível para os 69 testes (nenhum importa `app.main`) |
| Correção proposta | `@router.get(..., response_model=None)` no decorador; revisar `get_divergencias_pdf` (`:378`) |
| Restrição | É código de produto — **exige autorização** |
| Esforço | 15 min + 1 teste de fumaça que importe `app.main` |
| Estado | ✅ `IMPLEMENTADO` + `TESTADO` — commit `851da0a` |

**Resultado:** `app.main` importa, `uvicorn` carrega a app, `GET /health` → 200, 8 rotas no OpenAPI,
32/32 módulos importam. Suíte: **69 → 82 testes**.

### P-17 · Handler para erro de banco (500 → 503)

| Campo | Valor |
|-------|-------|
| Descoberto em | verificação de boot da P-16 |
| Sintoma | `GET /conferir/<uuid>/laudo.pdf` sem banco → `OperationalError` → **500** |
| Efeito | Cliente recebe erro genérico; monitoramento não distingue queda de banco de bug |
| Correção proposta | exception handler global para `sqlalchemy.exc.OperationalError` → 503 JSON |
| Pré-existente? | **Sim** — não foi introduzido pela P-16 |
| Esforço | 1 h |
| Estado | `PLANEJADO` |

### P-18 · Aplicar política de versões (ADR-010)

| Campo | Valor |
|-------|-------|
| O que | Teto de major para `fastapi`, `pydantic`, `fpdf2`; `starlette` em `constraints.txt` |
| Por que | Foi a ausência de teto que produziu o P-16 |
| Risco | Tetos bloqueiam correções de segurança — exige revisão trimestral |
| Estado | `PLANEJADO` — aguarda aprovação |

### P-03 · Gate mecânico de licenciamento

| Campo | Valor |
|-------|-------|
| Por que | A proibição de AGPL/YOLO hoje é processual (humana), não mecânica |
| O que | Script de 3 camadas conforme `LICENSING_GATE.md` §4; rodar em CI e local |
| Esforço | 2–3 h |
| Verificação | Adicionar `ultralytics` temporariamente em uma branch → o gate falha; remover → passa |
| Gate | Nenhum (é proteção, não feature) |
| Estado | `PLANEJADO` |

---

## 2. Bloco B — Rede de segurança antes de tocar comportamento

### P-04 · Medir cobertura

| Campo | Valor |
|-------|-------|
| O que | Adicionar `pytest-cov` a `requirements-dev.txt`; gerar relatório |
| Verificação | Relatório com % por arquivo; `app/domain/` ≥ 80% |
| Esforço | 1 h |
| Estado | `PLANEJADO` |

### P-05 · Infra de teste: PostgreSQL em container + `TestClient`

| Campo | Valor |
|-------|-------|
| O que | Fixture de container efêmero (`postgres:16-alpine`, nome `stellspy-test-pg`, porta 55432); aplica as 9 migrações; `TestClient` do FastAPI |
| Pré-requisito | ADR-004; execução fora do confinamento |
| Verificação | Banco sobe e cai por teste; migrações aplicam do zero; 1 teste de fumaça em `/health` |
| Esforço | 1 dia |
| Risco | ⚠️ **Não tocar** `venddi-pg` / `supabase_*_venddi-*` (outro projeto na máquina) |
| Estado | `PLANEJADO` |

### P-06 · Snapshot de contrato das 8 rotas

| Campo | Valor |
|-------|-------|
| O que | Congelar a resposta JSON atual de cada rota (com dados de fixture) |
| Verificação | Alterar uma resposta deliberadamente → o snapshot falha |
| Esforço | 1 dia |
| Estado | `PLANEJADO` |

---

## 3. Bloco C — Correções de defeitos confirmados

Ordem por risco decrescente. Todas exigem P-05/P-06 prontos.

| ID | Defeito | Ação | Teste que prova | Esforço | Estado |
|----|---------|------|-----------------|---------|--------|
| P-07 | A1 — SSRF via redirect em `foto_url` | `follow_redirects=False` + revalidar host por hop | redirect para IP privado é bloqueado | 2 h | `PLANEJADO` |
| P-08 | A4 — idempotência ignora `tipo` | incluir `tipo` na chave; devolução vira nova conferência | devolução da mesma chave retorna `tipo=devolucao` | 4 h | `PLANEJADO` |
| P-09 | A3 — override inconsistente | separar `status_calculado`/`status_efetivo`; propagar para `nfe_itens` | após override, leitura devolve estado coerente | 1 dia | `PLANEJADO` |
| P-10 | A5 — cimento/bloco sem normalização de unidade | usar `normalizacao_materiais` antes de comparar | 28 sacos × 1 m³ → VERDE, não VERMELHO | 1 dia | `PLANEJADO` |
| P-11 | A2 — `modo_aprendizado` default ON | default `FALSE` + migração sinalizando obras existentes | obra nova nasce bloqueando | 2 h | `PLANEJADO` |
| P-12 | M1 — fila presa em `processando` | `try/finally` por item + reaper por `claimed_em` | linha órfã volta a `pendente` | 4 h | `PLANEJADO` |
| P-13 | D-FP — `fpdf2` `ln=`/`dest=` | migrar para `new_x`/`new_y` e `pdf.output()` | 0 warnings de deprecação | 3 h | `PLANEJADO` |

---

## 4. Bloco D — Fase 0 (após autorização)

### P-14 · Implementar Fase 0

| Campo | Valor |
|-------|-------|
| Pré-requisitos técnicos | P-01 a P-06 concluídos |
| Pré-requisito de negócio | **Autorização explícita** — a recomendação anterior (`DECISAO_GO_NO_GO_COMERCIAL.md`) era validar a dor antes |
| Escopo | M1–M6 de `PLANO_EXECUCAO_FASE0.md` §2; RBAC; isolamento; teste de mutação |
| Esforço | 24 dd (+30% → 31 dd) |
| Verificação | AC0.1–AC0.10 |
| Estado | `BLOQUEADO` — gate **G-06** |

> **Conflito registrado, não resolvido:** a missão de engenharia diz "depois da aprovação, implementar
> Fase 0"; o gate comercial diz "não iniciar Fase 0 sem confirmar a dor". Os dois não são
> incompatíveis — mas a decisão é do fundador, e o custo de errar é de ~31 dias-dev. Recomendação:
> rodar P-01 a P-06 (≈ 3 dias) e, em paralelo, as 10 entrevistas (≈ 23 h, R$ 0). Só então decidir.

---

## 5. Bloco E — Trilha B (visão computacional)

| ID | Ação | Bloqueio | Estado |
|----|------|----------|--------|
| P-15 | Inspecionar árvore de dependências de `inference` (`pip download --no-deps`) | G-07 | `PLANEJADO` |
| P-16 | Configurar privacidade Roboflow + arquivar print | G-08 | `PLANEJADO` |
| P-17 | Coletar e anotar dataset (600 vergalhão + 600 sacos) | autorização de imagem | `PLANEJADO` |
| P-18 | Baseline OpenCV + treinos RF-DETR | P-15, P-16, P-17 | `PLANEJADO` |

---

## 6. Sequência recomendada (2 semanas)

```
Dia 1     P-01 (.gitignore + commit)      ← destrava tudo
Dia 1     P-02 (tzdata)                   ← repositório passa a rodar
Dia 2     P-03 (gate de licença)
Dia 3     P-04 (cobertura)
Dia 4–6   P-05 + P-06 (Postgres + contratos)
Dia 7–10  P-07 a P-13 (correções com teste)
Paralelo  Entrevistas comerciais (10)
Dia 11    Reavaliar G-06 e decidir Fase 0
```

---

## 7. Decisão imediata necessária

> ## ✅ Bloco A concluído — P-01 e P-02 executados
>
> O repositório tem histórico (`6668591`) e o projeto roda em ambiente limpo a partir das dependências
> declaradas (`979991e`). Os dois bloqueios técnicos foram eliminados.

**Estado do repositório:** `git status` limpo · 2 commits · 117 arquivos versionados.

### A decisão agora é outra: P-16

A verificação de imports da Etapa 4 revelou que **`app.main` não importa** com `fastapi 0.162.0`
(`app/routers/conferencia.py:298`). A API não sobe. Nenhum teste pega isso porque nenhum teste importa
`app.main`.

> **Autorizar P-16:** trocar a anotação de retorno de `get_laudo_pdf` por `response_model=None` no
> decorador e acrescentar **um** teste que faça `import app.main`. São ~15 minutos, é a primeira
> alteração em código de produto, e fecha o único defeito conhecido que impede o serviço de iniciar.

Sem isso:
- a Fase 0 não tem como validar nada ponta a ponta (a API não sobe);
- qualquer trabalho na Fase 1 começaria sobre um serviço que falha no boot;
- o risco "dependências sem teto" (M5) continua sem tratamento — `fastapi>=0.115.0` aceita qualquer
  versão futura.

### Observação sobre tetos de versão

O defeito P-16 é a primeira materialização do risco **M5**: `requirements.txt` usa `>=` em todas as
7 dependências, sem teto. Não recomendo fixar tudo agora (quebra reprodutibilidade por outro lado);
recomendo **congelar o par conhecido-bom** (`fastapi`, `starlette`, `pydantic`, `fpdf2`) com teto de
major na próxima decisão, e deixar o resto acompanhar.
