# PLANO DE EXECUÇÃO — FASE 0 (Fundação)

> **Status de verificação deste documento:** análise estática. **Nada foi executado.**
> O shell desta sessão falha na preparação do sandbox
> (`SetNamedSecurityInfoW failed (Win32 5): grantWrite(C:\Naturecode\stellSPY)`), portanto
> **não há resultado de `pytest`, `git status`, `pip freeze` nem `docker`**. Toda métrica marcada
> como *estática* foi obtida por leitura e busca textual; toda métrica marcada como *pendente*
> exige execução e **não deve ser citada como se existisse**.

---

## 1. Baseline do sistema atual

### 1.1 O que está provado (evidência estática)

| Métrica | Valor | Método de verificação |
|---------|-------|----------------------|
| Arquivos Python em `backend/app` | 32 | `glob` recursivo |
| Linhas em `backend/app` | ≈ 4.223 | soma das leituras linha a linha |
| Endpoints HTTP | **8** | 7 decoradores `@router.*` + `GET /health` |
| Tabelas de domínio | **7** | `obras`, `especificacoes`, `nfe_logs`, `nfe_itens`, `fila_nfe`, `sinonimos`, `normalizacao_materiais` |
| Migrações SQL | **9** | `supabase/migrations/*.sql` |
| Variáveis de ambiente lidas | **38** | `os.getenv` + `_env_int/_env_bool` |
| Arquivos de teste | 15 (14 + `conftest.py`) | `glob` |
| Funções de teste | **65** | `grep '^def test_'` |
| Casos de teste (após parametrização) | **69** | 65 − 2 parametrizadas + 6 casos (3+3) |
| Testes que usam `TestClient` / banco | **0** | `grep -i testclient\|psycopg` nos testes |
| Dependências com teto de versão | **0 de 7** | `requirements.txt` usa `>=` em todas |
| Tabelas sem uso no código | **2** | `sinonimos`, `normalizacao_materiais` |

### 1.2 O que está pendente (precisa de execução)

| Métrica | Comando exato | Por que importa |
|---------|---------------|-----------------|
| Testes passando/falhando | `cd backend; python -m pytest -q` | Baseline de regressão da Fase 0 |
| Contagem coletada | `python -m pytest --collect-only -q \| tail -1` | Confirmar 69 |
| Cobertura atual | `python -m pytest --cov=app --cov-report=term-missing` | Cobertura de `domain/` |
| Versões instaladas | `pip freeze > baseline_requirements_freeze.txt` | Reprocessar lock |
| Estado do Git | `git status --porcelain` | Confirmar árvore limpa antes de migrar |
| Docker disponível | `docker --version` | Decide estratégia de Postgres em container |
| Postgres local | `psql --version` | Alternativa ao Docker |
| Tamanho real do banco | `SELECT pg_size_pretty(pg_database_size(current_database()))` | Decide se backfill é online ou em janela |

> **Regra de honestidade:** nenhum item de §1.2 pode virar "concluído" sem a saída do comando anexada
> ao registro da fase.

### 1.3 Inventário de endpoints (contrato a preservar byte a byte)

| Método | Rota | Arquivo | Dependência de auth |
|--------|------|---------|---------------------|
| GET | `/health` | `main.py:28` | nenhuma |
| POST | `/auth/pwa/login` | `auth_pwa.py:35` | API key da obra |
| GET | `/auth/pwa/session` | `auth_pwa.py:70` | cookie |
| POST | `/auth/pwa/logout` | `auth_pwa.py:84` | — |
| POST | `/conferir` | `conferencia.py:154` | obra (cookie ou header) |
| GET | `/conferir/{id}/laudo.pdf` | `conferencia.py:292` | obra do log |
| GET | `/conferir/{id}/divergencias.pdf` | `conferencia.py:377` | obra do log |
| POST | `/override/{id}` | `conferencia.py:450` | obra do log |

**Critério de compatibilidade:** o corpo de resposta de cada rota é idêntico antes e depois da Fase 0,
exceto por campos **aditivos**. Qualquer remoção de campo = quebra de contrato = bloqueio de merge.

---

## 2. Estratégia de migração sem reescrever o núcleo

### 2.1 Princípio

O núcleo (`domain/conferente.py`) **não é tocado** na Fase 0. A Fase 0 só adiciona:

1. tabelas novas (`construtoras`, `usuarios`, `obra_usuarios`);
2. uma coluna nova em `obras` (`tenant_id`);
3. uma role de banco nova;
4. policies de RLS.

Nenhuma coluna existente é alterada ou removida. Nenhuma função existente muda de assinatura.

### 2.2 Ordem das migrações (todas aditivas, todas reversíveis)

| Ordem | Arquivo proposto | Conteúdo | Reversível por |
|-------|------------------|----------|----------------|
| M1 | `20261110xxxxxx_construtoras.sql` | `CREATE TABLE construtoras` + índice `uq_construtoras_cnpj` | `DROP TABLE` |
| M2 | `20261110xxxxxx_obras_tenant.sql` | `ALTER TABLE obras ADD COLUMN tenant_id UUID` (NULL) | `DROP COLUMN` |
| M3 | `20261110xxxxxx_backfill_tenant.sql` | Insere construtora padrão; `UPDATE obras SET tenant_id = <default> WHERE NULL` | `UPDATE … SET tenant_id = NULL` |
| M4 | `20261110xxxxxx_obras_tenant_nn.sql` | `ALTER COLUMN tenant_id SET NOT NULL` + FK + índice | `DROP NOT NULL` |
| M5 | `20261110xxxxxx_usuarios.sql` | `usuarios`, `obra_usuarios` | `DROP TABLE` |
| M6 | `20261110xxxxxx_rls.sql` | `ENABLE ROW LEVEL SECURITY` + policies | `DISABLE RLS` |

> **Por que M2–M4 separadas:** em tabela pequena (hoje) caberia numa só. Separar preserva a disciplina
> *expand–contract* e permite que M3 (backfill) rode como job, não como DDL. Se o banco tiver
> `obras` > 100 mil linhas, M3 **obrigatoriamente** vira job em lote.

### 2.3 Decisão sobre a construtora padrão (ponto sensível)

`construtoras.cnpj` deveria ser `NOT NULL`, mas **não conhecemos o CNPJ do operador atual** — e
`obras.cnpj_destinatario` é o CNPJ da obra (destinatário da NF), não da construtora. Inventar um CNPJ
seria criar dado falso.

| Item | Decisão |
|------|---------|
| Construtora padrão | 1 linha: `nome = 'Migração — preencher'`, `cnpj = NULL`, `plano = 'piloto'` |
| Constraint | `cnpj` **nullable na M1**; vira `NOT NULL` na M8 (após preenchimento manual) |
| Tarefa manual | Preencher `nome` e `cnpj` reais antes de criar a segunda construtora |
| Bloqueio | **Não** criar 2ª construtora com a padrão incompleta (ver `MATRIZ_GO_NO_GO.md`, G0.4) |

### 2.4 Backfill

```sql
-- ILUSTRATIVO — não executar
-- M3
WITH nova AS (
  INSERT INTO construtoras (nome, plano)
  VALUES ('Migração — preencher', 'piloto')
  RETURNING id
)
UPDATE obras SET tenant_id = (SELECT id FROM nova) WHERE tenant_id IS NULL;
```

Em uma transação única, para tabelas pequenas. Para grandes: `INSERT` da construtora, depois
`UPDATE … WHERE tenant_id IS NULL` em lotes de 5.000 com commit por lote (idempotente por natureza,
pois o filtro é `IS NULL`).

### 2.5 Isolamento — o detalhe que costuma quebrar

Três armadilhas conhecidas, todas evitáveis:

**a) Role `postgres` ignora RLS.**
Hoje a conexão usa a role da `DATABASE_URL` (tipicamente `postgres`), que tem `BYPASSRLS`. RLS
seria decorativa. É preciso criar `stellspy_app`:

```sql
-- ILUSTRATIVO
CREATE ROLE stellspy_app LOGIN PASSWORD '...' NOBYPASSRLS NOINHERIT;
GRANT CONNECT ON DATABASE ... TO stellspy_app;
GRANT USAGE ON SCHEMA public TO stellspy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO stellspy_app;
```

E, se a role de app for **dona** das tabelas, RLS continua ignorada, a menos que se use
`ALTER TABLE ... FORCE ROW LEVEL SECURITY`. Aplicar `FORCE` nas 7 tabelas + nas novas.

**b) `SET LOCAL` precisa acontecer antes da primeira query.**
Com SQLAlchemy, um `SET LOCAL app.tenant_id` executado "em algum lugar" não garante ordem. Solução:
listener em `after_begin` no `Session`, lendo o tenant do `session.info`:

```python
# ILUSTRATIVO — app/db.py (evolução, não substituição)
@event.listens_for(Session, "after_begin")
def _aplicar_tenant(session, transaction, connection):
    tid = session.info.get("tenant_id")
    if tid:
        connection.exec_driver_sql("SET LOCAL app.tenant_id = %s", (str(tid),))
```

**c) O login acontece antes de existir tenant.**
`POST /auth/pwa/login` recebe `obra_id` e precisa ler `obras` — mas `obras` está sob RLS e não há
tenant na sessão ainda. Solução: **função `SECURITY DEFINER` estreita**, que devolve só o necessário:

```sql
-- ILUSTRATIVO
CREATE FUNCTION auth_lookup_obra(p_obra_id UUID)
RETURNS TABLE (obra_id UUID, tenant_id UUID, api_key_hash TEXT)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT id, tenant_id, api_key_hash FROM obras WHERE id = p_obra_id;
$$;
REVOKE ALL ON FUNCTION auth_lookup_obra(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_lookup_obra(UUID) TO stellspy_app;
```

Sem isso, a Fase 0 "funciona em teste e falha em produção" — sintoma clássico.

### 2.6 Rollback

| Nível | Ação | Tempo |
|-------|------|-------|
| Antes do deploy | Nada a fazer (migrações não aplicadas) | 0 |
| Após M1–M2 | `DROP TABLE construtoras; ALTER TABLE obras DROP COLUMN tenant_id;` | minutos |
| Após M4 | `ALTER TABLE obras ALTER COLUMN tenant_id DROP NOT NULL;` + remover FK | minutos |
| Após M6 (RLS) | `ALTER TABLE … DISABLE ROW LEVEL SECURITY;` — app volta a ler sem filtro | minutos |
| Após aplicação em produção | **Rollback de código primeiro** (deploy anterior), migração depois | < 30 min |

Nenhuma migração da Fase 0 apaga dado. É por isso que ela pode ser aplicada com segurança.

---

## 3. Identidade, usuários e autorização

### 3.1 Modelo mínimo (ver DDL em `MODELO_DE_DADOS.md`)

`construtoras` (tenant) → `usuarios` (com `tenant_id`) → `obra_usuarios` (vínculo + papel na obra).

Escolha deliberada: **`papel_global` define o teto; `obra_usuarios.papel` define o alcance.**
Um `fiscal` global não enxerga a obra em que não foi vinculado.

### 3.2 Matriz de autorização (fonte única de verdade)

| Ação | admin_tenant | engenheiro | fiscal | auditor |
|------|:---:|:---:|:---:|:---:|
| Criar obra | ✅ | ⬜ | ⬜ | ⬜ |
| Editar especificação | ✅ | ✅ | ⬜ | ⬜ |
| Criar recebimento | ✅ | ✅ | ✅ | ⬜ |
| Anexar evidência | ✅ | ✅ | ✅ | ⬜ |
| Revisar contagem | ✅ | ✅ | ✅ | ⬜ |
| Override (VERMELHO→VERDE) | ✅ | ✅ | ⬜ | ⬜ |
| Solicitar retenção | ✅ | ✅ | ⬜ | ⬜ |
| Exportar dossiê | ✅ | ✅ | ⬜ | ✅ |
| Gerenciar usuários | ✅ | ⬜ | ⬜ | ⬜ |

Implementação em **um único módulo** (`app/deps.py` → `require(papel)`), nunca espalhada. Um teste por
célula da matriz, parametrizado (a matriz tem 36 células → 36 casos).

### 3.3 Transição da autenticação atual

| Hoje | Fase 0 |
|------|--------|
| `obras.api_key` em texto plano | `obras.api_key_hash` (HMAC-SHA256 com `PWA_SESSION_SECRET`), coluna nova; `api_key` legada mantida só para as obras migradas |
| Cookie `stellspy_pwa` com `{obra_id}` | Mesmo cookie, claims adicionais `{sub, tenant, role, obra_id}` |
| `verificar_acesso_obra` compara chave | Mantida a função, agora resolvendo por hash; assinatura **não muda** |

Isso preserva `auth_obra.py` e `pwa_session.py` (não reescrever). A verificação de hash entra dentro de
`verificar_api_key_obra`, com fallback temporário em texto plano enquanto houver obra legada.

---

## 4. Testes com PostgreSQL em container

### 4.1 Opções e decisão

| Opção | Pré-requisito | Prós | Contras |
|-------|---------------|------|---------|
| **A. testcontainers-python** | Docker | Postgres efêmero por sessão; CI igual ao dev | +1 dependência de dev; exige Docker |
| **B. docker compose (`docker-compose.test.yml`)** | Docker | Sem dependência Python nova; reproduzível | Precisa orquestrar `up/down` no Makefile |
| **C. Postgres local + `TEST_DATABASE_URL`** | Postgres instalado | Zero Docker; funciona hoje | Ambiente divergente; risco de rodar contra base errada |
| D. SQLite em memória | nenhum | Rápido | **Inútil aqui**: não tem RLS, `jsonb`, `INET`, `SKIP LOCKED` |

**Decisão proposta:** **C como padrão de desenvolvimento** (infra disponível, sem instalar nada) e
**B no CI** (reprodutível). `testcontainers` (A) fica como opção se Docker já existir.

**Guarda obrigatória para a opção C:** o fixture deve recusar rodar se `TEST_DATABASE_URL` não
contiver `_test` no nome do banco. Sem isso, alguém aponta para produção e a suíte apaga `nfe_logs`.

### 4.2 Fixtures necessárias

| Fixture | Escopo | O que faz |
|---------|--------|-----------|
| `db_vazia` | session | Aplica as 9 migrações existentes + novas em banco limpo |
| `db_limpa` | function | Trunca tabelas de domínio (não as de migração) |
| `tenant_a`, `tenant_b` | function | Duas construtoras completas |
| `cliente_a`, `cliente_b` | function | `TestClient` com cookies distintos |
| `obra_a`, `obra_b` | function | Obras vinculadas a tenants distintos |

### 4.3 Testes obrigatórios de isolamento

| # | Teste | Asserção |
|---|-------|----------|
| I1 | `GET` de recurso do tenant B com sessão do tenant A | `404` (não `403` — não vazar existência) |
| I2 | `POST /conferir` com `obra_id` do tenant B | `404` |
| I3 | Query direta sem `SET LOCAL` | **0 linhas** (RLS ativa) |
| I4 | Query direta com `tenant_id` errado no `SET LOCAL` | **0 linhas** |
| I5 | Role de app tem `BYPASSRLS`? | `false` (consulta em `pg_roles`) |
| I6 | Remover a policy → teste I3 **falha** (teste de mutação) | falha esperada |

I6 é o que diferencia "testei" de "acredito que testei".

---

## 5. Critérios de aceite da Fase 0

Nenhum item pode ser marcado sem evidência anexada (saída de comando, print, ou teste verde em CI).

| ID | Critério | Evidência exigida | Bloqueia |
|----|----------|-------------------|----------|
| AC0.1 | `pytest` verde no CI com as 9 migrações aplicadas do zero | log do CI | merge |
| AC0.2 | 69 casos do baseline continuam passando (nada regrediu) | diff do relatório | merge |
| AC0.3 | Contrato das 8 rotas inalterado (snapshot JSON) | arquivo `tests/snapshots/*.json` | merge |
| AC0.4 | Testes I1–I6 verdes | log | merge |
| AC0.5 | Migrações idempotentes: rodar 2× não gera erro | log | merge |
| AC0.6 | Role `stellspy_app` sem `BYPASSRLS` | saída de `SELECT rolbypassrls FROM pg_roles` | merge |
| AC0.7 | `POST /auth/pwa/login` funciona **antes** de qualquer `SET LOCAL` | teste verde | merge |
| AC0.8 | Nenhuma dependência AGPL/GPL no `requirements.txt` | `LICENSING_GATE.md` §4 | merge |
| AC0.9 | Cobertura de `app/domain/` ≥ 80% | relatório de cobertura | release |
| AC0.10 | Construtora padrão com `cnpj` preenchido **antes** da 2ª construtora | consulta SQL | 2º tenant |

---

## 6. Decomposição de tarefas e esforço

| # | Tarefa | Depende de | dd (S=0,5 · M=1–2 · L=3–6) |
|---|--------|-----------|------|
| F0.1 | Baseline executável (§1.2) + freeze de dependências | — | S |
| F0.2 | Correções A1, A2, A6, M1 do diagnóstico | — | 4 |
| F0.3 | CI: pytest + build CSS + gate de licença | F0.1 | 1 |
| F0.4 | M1–M4: construtoras + `tenant_id` + backfill | F0.1 | 2 |
| F0.5 | Role `stellspy_app` + `FORCE RLS` + listener `after_begin` | F0.4 | 2 |
| F0.6 | `auth_lookup_obra` (SECURITY DEFINER) + login por hash | F0.5 | 2 |
| F0.7 | M5: `usuarios` + `obra_usuarios` + claims no cookie | F0.4 | 2 |
| F0.8 | `deps.py` + `require(papel)` + 36 casos da matriz | F0.7 | 2 |
| F0.9 | Fixtures Postgres + testes I1–I6 | F0.5 | 3 |
| F0.10 | Correção A3 (override consistente) | F0.7 | 2 |
| F0.11 | Correção A4 (idempotência com `tipo`) | F0.4 | 1 |
| F0.12 | Correção A5 (normalização de unidade) | — | 2 |
| F0.13 | M6: policies finais + revisão | F0.9 | 1 |
| | **Total** | | **≈ 24 dd** |

Folga recomendada: +30% → **~31 dd** (≈ 6 semanas para 1 pessoa).

---

## 7. O que **não** entra na Fase 0

| Fora | Motivo |
|------|--------|
| Upload de evidência | É a Fase 1 (`PLANO_PIPELINE_EVIDENCIAS.md`) |
| Visão computacional | Trilha B |
| Refatorar `conferente.py` | Proibido pela diretriz; não há justificativa |
| Trocar SQLAlchemy por ORM | Sem ganho; risco alto |
| Reescrever `pwa_session.py` | Basta adicionar claims |
| Mover migrações para Supabase CLI | Sem ganho nesta fase |
| Rotacionar a API key legada | Só após hash existir em todas as obras |

---

## 8. Dependências externas da Fase 0

| Dependência | Tipo | Status |
|-------------|------|--------|
| Postgres acessível para testes | infra | **pendente de verificação** |
| Docker (se opção A/B) | infra | **pendente de verificação** |
| Acesso ao banco de produção **para leitura** (contagem de linhas) | acesso | pendente |
| CNPJ real da construtora piloto | dado | pendente (bloqueia AC0.10, não bloqueia F0) |
| Aprovação do plano de migração | decisão | **necessária antes de F0.4** |
