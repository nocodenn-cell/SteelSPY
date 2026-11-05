# Checklist — Supabase oficial do SteelSPY

Projeto oficial: **SteelSPY** — `akvbtceshpsvsuacueaq`
URL: `https://akvbtceshpsvsuacueaq.supabase.co`

Este é o único projeto Supabase do SteelSPY. Não usar projetos de outros produtos
(Venddi, Jinlong, FABRYON, GEO Portal) nem trocar a `DATABASE_URL` para outro ref.

---

## 0. Credenciais (nunca no chat, nunca no Git)

Copie para `backend/.env` (já ignorado). O chat e o repositório nunca recebem
senha nem `service_role`.

| Variável | Onde obter | Uso |
|----------|------------|-----|
| `SUPABASE_DB_ADMIN_URL` | Project Settings → Database → Connection string → **Session pooler** (`postgres.<ref>`) | somente migrations e diagnóstico |
| `STELLSPY_APP_PASSWORD` | escolhida por você, ≥ 12 caracteres | senha da role operacional `stellspy_app` |
| `DATABASE_URL` | mesma tela, usuário `stellspy_app.<ref>` (Supavisor usa `<role>.<tenant>`) | processo da API, sujeito a RLS |
| `SUPABASE_URL` | Project Settings → API | Storage/laudo |
| `SUPABASE_ANON_KEY` | Project Settings → API (publishable) | cliente, se usado |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API (secret) | **só servidor** (`EVIDENCIAS_STORAGE=supabase`) |
| `DASHBOARD_DATABASE_URL` | role `stellspy_dashboard` criada pela migration 31 (somente leitura, presa a um tenant), **não** a role da API nem `postgres` | dashboard Streamlit |
| `STELLSPY_DASHBOARD_PASSWORD` | escolhida por você, ≥ 12 caracteres | senha da role `stellspy_dashboard` no executor de migrations |
| `DASHBOARD_TENANT_ID` | UUID da construtora do piloto | tenant explícito do dashboard |
| `DASHBOARD_PASSWORD` | dedicada ao painel, ≥ 12 caracteres | login do dashboard; sem ela o painel não abre |

- [ ] `DATABASE_URL` usa `stellspy_app.<ref>`, **nunca** `postgres.<ref>`.
- [x] `DASHBOARD_DATABASE_URL` usa `stellspy_dashboard.<ref>` (migration 31), não `postgres`/owner e não `stellspy_app` — validado em 2026-11-05.
- [ ] `DASHBOARD_TENANT_ID` aponta para a construtora do piloto (hoje HML Alfa, provisório).
- [ ] `SUPABASE_DB_ADMIN_URL` fica fora do processo da API.
- [ ] Nenhuma chave `service_role` em variável `NEXT_PUBLIC_*`, PWA ou log.

Estado em 2026-11-04 (`backend/.env`, verificado sem exibir valores):

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` e `PWA_SESSION_SECRET`: reais e válidos.
- `STELLSPY_APP_PASSWORD`: gerada localmente com 43 caracteres (≥ 12).
- `DATABASE_URL`: role operacional no pooler real, porta 5432.
- `SUPABASE_DB_ADMIN_URL`: senha regravada com `python scripts/configurar_senha_admin.py`
  e **conexão administrativa OK** em 2026-11-04 (sem exibir o valor).
- Em 2026-11-05: migration 31 aplicada no projeto oficial (**31/31**),
  `STELLSPY_DASHBOARD_PASSWORD` (43 chars) e `DASHBOARD_PASSWORD` (32 chars)
  geradas localmente, `DASHBOARD_DATABASE_URL` e `DASHBOARD_TENANT_ID` definidos
  — valores nunca exibidos nem versionados.

---

## 1. Confirmar o projeto

- [x] `curl -sI https://akvbtceshpsvsuacueaq.supabase.co/rest/v1/ | grep sb-project-ref`
      deve responder `sb-project-ref: akvbtceshpsvsuacueaq` (401 sem `apikey` é o esperado).
- [x] Região = trecho do host do pooler (`aws-0-us-east-2.pooler.supabase.com`).
- [x] Versão do PostgreSQL e PostGIS vêm do diagnóstico abaixo (PG **17.11**; PostGIS ausente).

---

## 2. Diagnóstico read-only (antes de qualquer escrita)

```bash
cd backend
python scripts/diagnostico_supabase.py            # lê backend/.env
```

Grava `.devtmp/supabase_oficial_diag.json` (ignorado) e mostra um resumo com:
ref, região, versão do PostgreSQL/PostGIS, extensões, schemas, tabelas, RLS/Force,
policies, roles, `schema_migrations`, buckets e Auth. A conexão é aberta em
transação `READ ONLY`; nada é criado ou alterado.

- [x] `projeto_confere: true`
- [x] `tabelas_esperadas_ausentes: []` (após as migrations)
- [x] `app_sem_bypassrls: true`
- [x] `tenant_sem_rls: []`
- [x] `migrations_pendentes` conhecido: projeto novo ⇒ 30 pendentes; depois, 0

---

## 3. Migrações (31 arquivos, mesma trilha do repositório)

Não existe um segundo sistema de migração: `backend/scripts/apply_migrations.py`
aplica `supabase/migrations/*.sql` em ordem, uma transação por arquivo, e registra
em `schema_migrations`. O runner **recusa** rodar como `stellspy_app`.

```bash
cd backend
# lê SUPABASE_DB_ADMIN_URL e STELLSPY_APP_PASSWORD do .env local (ignorado)
python scripts/apply_migrations.py --env-file .env
```

- [x] Pooler em modo **sessão** (porta 5432): a senha da role é configurada por sessão.
- [x] Projeto novo: 30 pendentes, todas aplicadas (0 → 30/30, 2026-11-04 16:51 UTC).
- [ ] Migration **31** (`20261104170000_dashboard_role.sql`): pendente no remoto;
      localmente entra na suíte de integração. Cria `stellspy_dashboard`
      (`NOLOGIN` sem senha, `NOSUPERUSER`, `NOBYPASSRLS`, `NOINHERIT`), concede
      apenas `SELECT` em `construtoras`, `obras`, `nfe_logs`, `nfe_itens` e
      `especificacoes`.
- [x] Projeto com histórico: só as pendentes rodam; não há `DROP` nem `TRUNCATE`.
- [x] Reexecutar: `pendentes: 0` (idempotente) — repetir após a 31.

A migração 30 cria o bucket privado `evidencias`. Em PostgreSQL puro (sem schema
`storage`) ela apenas registra e segue. A migration 31 é *fail-closed*: sem
`STELLSPY_DASHBOARD_PASSWORD` (≥ 12 caracteres), a role fica `NOLOGIN`.

A migração 15 reconhece quando a role `stellspy_app` já existe: em vez de tentar
`ALTER ROLE ... NOSUPERUSER` (que exige superuser), ela **verifica** que a role
não tem `SUPERUSER` nem `BYPASSRLS` e falha se tiver. Isso é necessário porque o
`postgres` do Supabase tem `BYPASSRLS`, mas não é superuser.

---

## 4. Prova de isolamento multiempresa

Depois das migrações, com a role operacional:

```bash
HML_SENHA='<senha-hml-≥12>' python scripts/hml_staging.py --acao tudo \
  --admin-url "$SUPABASE_DB_ADMIN_URL" \
  --app-url "postgresql://stellspy_app.<ref>:<senha-app>@aws-0-<região>.pooler.supabase.com:5432/postgres" \
  --prefixo hml-oficial-2026-11-03
```

- [x] 12/12 checks PASS (B não vê A, updates cruzados afetam 0 linhas).
- [x] Reexecução com o mesmo prefixo não duplica nada (mesmos IDs, 3 usuários, 2 construtoras).
- [ ] Limpeza só com `--acao limpar --confirmar-limpeza` e prefixo `hml-*`
      (não executada: os dados sintéticos permanecem até decisão explícita).

Teste feito com `service_role` **não** vale como prova de isolamento.

---

## 5. Storage privado

- [x] Bucket `evidencias` existe e é **privado** (`public = false`, 12 MiB).
- [x] `EVIDENCIAS_STORAGE=supabase` e `EVIDENCIAS_BUCKET=evidencias` no servidor.
- [x] Chaves começam por `tenant_id/obra_id/evidencia_id/…` (auditável por construtora).
- [x] Upload grava original + normalizado, cada um com SHA-256 próprio.
- [x] Download passa pela API, que confere o hash antes de servir.
- [x] Nenhuma URL pública de fotografia (rota pública devolve 400 e não entrega bytes).

O bucket `laudos` (PDF) é opcional; sem ele o laudo é devolvido inline. Se for
criado, prefira privado com URL assinada — link público de dossiê é decisão de
produto, não default.

---

## 6. Smoke test da API

```bash
curl -s -X POST "$BASE/conferir" \
  -H "Content-Type: application/json" -H "X-API-KEY: $API_KEY" \
  -d "{\"obra_id\":\"$OBRA_ID\",\"chave_acesso\":\"$CHAVE44\"}"
```

- [ ] JSON com `status` e `nfe_log_id`.
- [ ] `GET $BASE/conferir/<id>/laudo.pdf` devolve PDF.
- [ ] Upload de evidência devolve 201 e o download confere o hash.

---

## 7. Invariantes de segurança

- [ ] `SKIP_API_KEY=0` em qualquer ambiente real.
- [x] `PWA_SESSION_SECRET` longo e aleatório (64 caracteres).
- [x] `CORS_ALLOW_ORIGINS` do piloto local:
      `http://localhost:8080,http://127.0.0.1:8080`.
- [ ] `CORS_ALLOW_ORIGINS` de produção com o domínio HTTPS exato do PWA (sem `*`).
- [x] Role `stellspy_app`: `NOSUPERUSER`, `NOBYPASSRLS`, sem `CREATEROLE`.
- [x] RLS habilitada e `FORCE` nas tabelas com `tenant_id` (20/20 + 20 políticas).
- [ ] Role `stellspy_dashboard`: `NOBYPASSRLS`, sem escrita, `SELECT` em 5 tabelas
      (teste local `test_dashboard_rls.py`; falta aplicar a 31 no remoto).
- [ ] Sem `service_role` em código de cliente.
- [ ] Chave que apareceu em chat/issue deve ser rotacionada no painel.
- [ ] `python scripts/auditar_publicacao.py` → **0 bloqueios** antes do deploy
      (varre `.env` e arquivos versionados atrás de segredo real, sem imprimir valor).

---

## 8. Evidência local já obtida (Sprint 4)

Executado no stack Supabase local (`supabase start`, PostgreSQL 17.11, portas 544xx),
com as 30 migrações e a role operacional — falta repetir no projeto remoto:

| Verificação | Resultado |
|-------------|-----------|
| `schema_migrations` | 30/30 aplicadas |
| Tabelas com RLS + `FORCE` | 20 |
| Políticas RLS | 20 |
| Role `stellspy_app` | `NOBYPASSRLS`, `NOSUPERUSER` |
| Bucket `evidencias` | privado (`public=false`), 12 MiB, JPEG/PNG |
| Suíte de integração | 177 passed (RLS, auth, pedidos, NF-e, recebimento, evidências, dossiê) |
| Suíte completa do backend | 497 passed (495 no CI + 2 marcados `supabase_local`; inclui 21 da preparação da Sprint 5) |
| Storage real (upload/leitura/duplicado/remoção) | 1 passed contra a API local |
| E2E API → Storage privado → download com hash | 1 passed (original byte a byte, isolamento entre construtoras) |
| HML `--acao tudo` | 12/12 PASS com `stellspy_app` |

No banco remoto, repetir as seções 1–6 e marcar cada item.

---

## 9. Histórico do bloqueio administrativo (superado em 2026-11-04)

Registro do estado anterior ao destravamento; **não é o estado atual** (ver seção 11):

| Verificação | Resultado |
|-------------|-----------|
| Identidade do projeto | `/auth/v1/settings`, `/rest/v1/` e `/storage/v1/bucket` → **200** com `sb-project-ref: akvbtceshpsvsuacueaq` |
| Auth | habilitado; `disable_signup=false` |
| Buckets remotos | `[]` — o bucket `evidencias` ainda não existe (M30 cria) |
| Pooler | DNS resolve e TCP `aws-0-us-east-2.pooler.supabase.com:5432` responde em ~0,25 s |
| Role `stellspy_app` | **ausente** — login devolve `user not found in the database` |
| Schema remoto | nenhuma tabela do SteelSPY exposta: `schema_migrations`, `construtoras`, `obras` e `evidencias` → `404 PGRST205`; 0/30 migrations (inicialização aditiva) |
| Autenticação administrativa | **recusada** em 5432 e 6543: `password authentication failed for user "postgres"` |
| Migrations remotas | **0 aplicadas**; execução interrompida antes de qualquer escrita |
| Suíte unitária após as correções | **325 passed** |
| Testes dos helpers (diagnóstico, runner, senha) | **26 passed** |

Destrave (sem colar segredo no chat):

```bash
cd backend
# 1) regrave a senha correta no prompt oculto; o helper percent-encoda e testa
python scripts/configurar_senha_admin.py

# 2) confirme a configuração e rode o diagnóstico read-only
python scripts/verificar_env_supabase.py   # precisa terminar sem BLOQUEADO
python scripts/diagnostico_supabase.py     # gera .devtmp/supabase_oficial_diag.json

# 3) revisado o relatório e confirmado que só há migrations pendentes:
python scripts/apply_migrations.py --env-file .env
```

O runner prefere `SUPABASE_DB_ADMIN_URL` a `DATABASE_URL` e recusa URL com
placeholder antes de abrir conexão; a senha da role vem de
`STELLSPY_APP_PASSWORD` no mesmo arquivo.

Depois do diagnóstico, o plano de migrations só é executado se a diferença for
aditiva. `apply_migrations.py` recusa rodar como `stellspy_app`; a role é criada
pela M15 e recebe a senha da M23 a partir de `STELLSPY_APP_PASSWORD`.

---

## 10. Revalidação local das 30 migrations (2026-11-04)

Executada enquanto o acesso administrativo remoto está bloqueado. **Não substitui
a homologação remota**; serve para provar que o pacote de migrations está
completo e que a role operacional isola tenants corretamente.

| Verificação | Resultado |
|-------------|-----------|
| PostgreSQL 16.15 (`stellspy-pg`, 55432) — suíte de integração | **177 passed, 1 deselected**; o conftest recria `public` e aplica 30/30 |
| PostgreSQL 16.15 — suíte completa | **511 passed, 2 skipped** (os 2 marcados `supabase_local`) |
| PostgreSQL 17.11 isolado (`stellspy-pg17`, 55433) — banco vazio | `apply_migrations.py` → **30 aplicadas**, 30 versões únicas |
| Atributos da role `stellspy_app` | `super=f`, `bypassrls=f`, `createrole=f`, `createdb=f`, `login=t` |
| RLS no PG 17 | 23 tabelas em `public`; **20 RLS + 20 FORCE + 20 políticas** |
| Schema `storage` no PG puro | ausente; M30 é no-op (o bucket só nasce no Supabase) |
| Isolamento com `stellspy_app` | sem `app.tenant_id` → 0 linhas; tenant A → só A; tenant B → só B; B consultando a obra de A → 0 |
| Supabase local (API 54421, PG 54422) | `pytest -m supabase_local` → **2 passed**: ciclo real no bucket privado e API → bucket → download com hash |
| Limpeza | container descartável `stellspy-pg17` removido após a coleta; nenhum outro stack tocado |

O que ainda depende do remoto: criar role, aplicar as 30 migrations, criar o
bucket `evidencias`, repetir a prova de RLS/isolamento e a HML no projeto
`akvbtceshpsvsuacueaq`.

---

## 11. Homologação remota concluída (2026-11-04)

Senha administrativa regravada pelo proprietário (`conexão administrativa: OK`).
Todas as operações abaixo foram no projeto oficial `akvbtceshpsvsuacueaq`,
sem push, deploy ou operação destrutiva.

| Verificação | Resultado real |
|-------------|----------------|
| Identidade | `projeto_confere: true`, ref `akvbtceshpsvsuacueaq`, pooler `aws-0-us-east-2`, PostgreSQL **17.11** |
| Migrations | `apply_migrations.py --env-file .env` → **30 aplicadas** (0 → 30/30, 2026-11-04 16:51 UTC); reexecução → **0 pendentes** |
| Tabelas | 23 em `public`; 19/19 esperadas presentes |
| RLS / FORCE / políticas | **20 / 20 / 20**; `tenant_sem_rls: []`, `sem_force_rls: []` |
| Role operacional | `stellspy_app` → `super=f`, `bypassrls=f`, `createrole=f`, `createdb=f`, `login=t` |
| Login da aplicação | `DATABASE_URL` como `stellspy_app.<ref>` conecta; sem `app.tenant_id` enxerga **0** construtoras |
| Bucket | `evidencias` privado (`public=false`), limite **12 MiB**, 0 políticas em `storage.objects` (proposital) |
| Storage real | ciclo upload/leitura/duplicado/remoção → **1 passed**; rota pública devolve 400 e não entrega bytes |
| HML sintética | 2 construtoras, 3 usuários, 1 pedido e 1 NF-e → **12/12 PASS** |
| HML idempotente | segunda execução com mesmo prefixo: mesmos IDs, **12/12 PASS**, sem duplicar |
| E2E HTTP oficial | login → upload **201** → download normalizado/original **200**; original byte a byte; SHA-256 normalizado e original conferem; cross-tenant **404** |
| Suíte completa | **514 passed, 2 skipped** |

Dados sintéticos que permanecem no projeto oficial (nenhuma limpeza executada):
duas construtoras `hml-*`, três usuários `@staging.invalid`, o pedido/NF-e
sintéticos e uma evidência de homologação. A remoção exige autorização explícita
e pode esbarrar na FK `evidencias.tenant_id` (`ON DELETE RESTRICT`).

Pendências que não bloqueiam a homologação: `CORS_ALLOW_ORIGINS` vazio, PWA em
navegador/aparelho real, rotação da senha administrativa após a janela e decisão
sobre os dados HML.

---

## 12. Sprint 5 — operação de campo (2026-11-04)

Correções de integração entre PWA, API e banco, sem alterar migrations nem dados
remotos. Detalhes em `docs/sprint5/RELATORIO_SPRINT5_OPERACIONAL.md`.

| Verificação | Resultado |
|-------------|-----------|
| Conferência por chave com sessão de usuário | passou a enviar CSRF e tratar 401 pelo cliente comum do PWA |
| Rotas do PWA × ações do backend | `pedido` → `ver_recebimento`, `fotos` → `ver_evidencia`, `conferir` → `criar_recebimento` |
| Recebimento idempotente | `id_cliente` sobrevive a reload via `sessionStorage`; retry devolve o mesmo registro |
| Evidência idempotente | chave estável por arquivo na tela; mesmo retry não duplica |
| Fluxo ponta a ponta | pedido → NF-e → recebimento → foto → conciliação → dossiê (JSON/PDF) coberto por teste de integração |
| Isolamento no fluxo completo | construtora vizinha recebe **404** para pedido, entrega, foto e conteúdo |
| Hash da evidência | `X-Conteudo-Sha256` e SHA-256 dos bytes conferem no download |
| Dashboard | exige `DASHBOARD_DATABASE_URL` e `DASHBOARD_PASSWORD` (≥ 12); com a role da API (RLS) para com mensagem explícita; sem senha falha fechado |
| PWA — testes unitários | `npm test` — 16 passed |
| Backend — suíte completa | ver `PROGRESS.md` (execução final desta entrega) |
| Celular real / câmera | **pendente de execução física** — roteiro em `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md` |

Nenhuma migration foi criada ou aplicada nesta etapa; o schema oficial segue
30/30. Nenhum dado sintético remoto foi removido e nada foi enviado ao Git remoto.
