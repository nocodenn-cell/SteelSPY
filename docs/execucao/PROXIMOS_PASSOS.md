# PRÓXIMOS PASSOS

> Ordem de execução derivada do estado real medido em `STATUS_EXECUCAO.md`.
> Cada ação tem verificação objetiva. Nada avança sem aprovação quando indicado.

---

## 1. Bloco A — Destravar (fazer agora)

### P-01 · `.gitignore` na raiz + commit inicial

| Campo | Valor |
|-------|-------|
| Por que | **Zero commits.** Sem ponto de restauração, qualquer alteração é irreversível |
| O que | Criar `.gitignore` (node_modules, `__pycache__`, `.pytest_cache`, `.venv`, `.env`, `*.pyc`); `git add` do estado atual; commit `chore: baseline congelado (69 testes verdes)` |
| Esforço | 15 min |
| Risco | Baixo — não altera código, só cria histórico |
| Verificação | `git log --oneline` mostra 1 commit; `git status` limpo; `git ls-files pwa/node_modules` **vazio** |
| Gate | **G-04** — exige autorização |
| Estado | `BLOQUEADO` |

### P-02 · Declarar `tzdata` em `requirements.txt`

| Campo | Valor |
|-------|-------|
| Por que | Suíte não coleta em ambiente limpo (`ZoneInfoNotFoundError`) — **confirmado por execução** |
| O que | Adicionar `tzdata>=2024.1` ao `requirements.txt` (ou condicional a Windows) |
| Esforço | 5 min |
| Verificação | Remover `tzdata` do `.venv`, reinstalar a partir do `requirements.txt`, rodar `pytest` → 69/69 |
| Gate | **G-05** — exige autorização (mudança de dependência do produto) |
| Estado | `BLOQUEADO` |

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

> **Autorizar P-01 e P-02.** São 20 minutos de trabalho, não alteram código de produto, e são a
> diferença entre um repositório que pode ser evoluído com segurança e um que não pode.

Sem elas:
- não há como reverter uma alteração da Fase 0;
- o projeto não roda em máquina limpa;
- qualquer trabalho futuro fica em cima de areia.
