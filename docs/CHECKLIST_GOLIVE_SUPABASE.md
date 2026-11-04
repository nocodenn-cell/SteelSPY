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

- [ ] `DATABASE_URL` usa `stellspy_app.<ref>`, **nunca** `postgres.<ref>`.
- [ ] `SUPABASE_DB_ADMIN_URL` fica fora do processo da API.
- [ ] Nenhuma chave `service_role` em variável `NEXT_PUBLIC_*`, PWA ou log.

---

## 1. Confirmar o projeto

- [ ] `curl -sI https://akvbtceshpsvsuacueaq.supabase.co/rest/v1/ | grep sb-project-ref`
      deve responder `sb-project-ref: akvbtceshpsvsuacueaq` (401 sem `apikey` é o esperado).
- [ ] Região = trecho do host do pooler (`aws-0-<região>.pooler.supabase.com`).
- [ ] Versão do PostgreSQL e PostGIS vêm do diagnóstico abaixo.

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

- [ ] `projeto_confere: true`
- [ ] `tabelas_esperadas_ausentes: []`
- [ ] `app_sem_bypassrls: true`
- [ ] `tenant_sem_rls: []`
- [ ] `migrations_pendentes` conhecido (projeto novo ⇒ todas as 30)

---

## 3. Migrações (30 arquivos, mesma trilha do repositório)

Não existe um segundo sistema de migração: `backend/scripts/apply_migrations.py`
aplica `supabase/migrations/*.sql` em ordem, uma transação por arquivo, e registra
em `schema_migrations`. O runner **recusa** rodar como `stellspy_app`.

```bash
cd backend
export SUPABASE_DB_ADMIN_URL='postgresql://postgres.akvbtceshpsvsuacueaq:...@aws-0-<região>.pooler.supabase.com:5432/postgres'
export STELLSPY_APP_PASSWORD='<senha-≥12>'

python scripts/apply_migrations.py --url "$SUPABASE_DB_ADMIN_URL"
```

- [ ] Pooler em modo **sessão** (porta 5432): a senha da role é configurada por sessão.
- [ ] Projeto novo: 30 pendentes, todas aplicadas.
- [ ] Projeto com histórico: só as pendentes rodam; não há `DROP` nem `TRUNCATE`.
- [ ] Reexecutar: `pendentes: 0` (idempotente).

A migração 30 cria o bucket privado `evidencias`. Em PostgreSQL puro (sem schema
`storage`) ela apenas registra e segue.

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

- [ ] 12/12 checks PASS (B não vê A, updates cruzados afetam 0 linhas).
- [ ] Reexecução com o mesmo prefixo não duplica nada.
- [ ] Limpeza só com `--acao limpar --confirmar-limpeza` e prefixo `hml-*`.

Teste feito com `service_role` **não** vale como prova de isolamento.

---

## 5. Storage privado

- [ ] Bucket `evidencias` existe e é **privado** (`public = false`).
- [ ] `EVIDENCIAS_STORAGE=supabase` e `EVIDENCIAS_BUCKET=evidencias` no servidor.
- [ ] Chaves começam por `tenant_id/obra_id/evidencia_id/…` (auditável por construtora).
- [ ] Upload grava original + normalizado, cada um com SHA-256 próprio.
- [ ] Download passa pela API, que confere o hash antes de servir.
- [ ] Nenhuma URL pública de fotografia.

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
- [ ] `PWA_SESSION_SECRET` longo e aleatório (≥ 32 bytes).
- [ ] `CORS_ALLOW_ORIGINS` com origens exatas.
- [ ] Role `stellspy_app`: `NOSUPERUSER`, `NOBYPASSRLS`, sem `CREATEROLE`.
- [ ] RLS habilitada e `FORCE` nas tabelas com `tenant_id`.
- [ ] Sem `service_role` em código de cliente.
- [ ] Chave que apareceu em chat/issue deve ser rotacionada no painel.

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
| Suíte completa do backend | 497 passed (inclui 21 da preparação da Sprint 5) |
| Storage real (upload/leitura/duplicado/remoção) | 1 passed contra a API local |
| E2E API → Storage privado → download com hash | 1 passed (original byte a byte, isolamento entre construtoras) |
| HML `--acao tudo` | 12/12 PASS com `stellspy_app` |

No banco remoto, repetir as seções 1–6 e marcar cada item.
