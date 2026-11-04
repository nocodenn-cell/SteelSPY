# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-04. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE B — integração ao Supabase oficial (`akvbtceshpsvsuacueaq`).**
Sprint 4 homologada localmente sobre o próprio stack Supabase (PostgreSQL 17.11).
O projeto remoto foi alcançado e identificado, mas a autenticação administrativa
foi **recusada pelo pooler** em 2026-11-04 (`password authentication failed`).
Nenhuma migration, role ou bucket remoto foi criado: a execução parou antes de
qualquer escrita (ver Bloqueios). Enquanto o acesso remoto está bloqueado, as 30
migrations foram revalidadas do zero em PostgreSQL 16.15 e 17.11 locais, com
prova de RLS pela role operacional e Storage real no Supabase local.

## Concluído

| Fase | Entrega | Evidência |
|------|---------|-----------|
| Sprint 3 (A) | PWA, auth, pedidos, NF-e, conciliação, recebimento parcial, evidências, dossiê, RBAC/RLS | merge `7e76713` em `origin/main`; suíte 446 passed |
| VC-01 (C) | protótipo de contagem com recusa, laudo e avaliação | commit `d181779`; `docs/vc01/RELATORIO_VC01.md` — **NO-GO** para contagem automática |
| HML (B) | `backend/scripts/hml_staging.py`: diagnóstico read-only, semeadura HML idempotente e prova de isolamento com a role da aplicação | `stellspy_demo`: 12/12 PASS; reexecução sem duplicar |
| Oficial (B) | projeto Supabase confirmado (`sb-project-ref: akvbtceshpsvsuacueaq`) e declarado oficial | cabeçalho do gateway + decisão do proprietário (2026-11-03) |
| Oficial (B) | banco vazio → 30 migrations → role `stellspy_app` → prova RLS | PostgreSQL 16.15 e 17.11 locais: 30/30 aplicadas; HML 12/12 PASS nas duas versões |
| Oficial (B) | Storage privado de evidências (bucket `evidencias`, chave por tenant/obra) | `armazenamento.py` + migração M30; 18 testes unitários + teste real contra o Storage do Supabase local |
| Oficial (B) | diagnóstico read-only e trava do runner contra role operacional | `scripts/diagnostico_supabase.py`, `apply_migrations.validar_role_migracao` |
| Oficial (B) | `DATABASE_URL` da aplicação separada da URL administrativa | `backend/.env.example`, `docs/CHECKLIST_GOLIVE_SUPABASE.md` |
| Sprint 4 (B) | stack Supabase local (`supabase/config.toml`, portas 544xx) com as 30 migrações e bucket privado | PG 17.11; 20 tabelas com RLS + FORCE; `evidencias public=false` |
| Sprint 4 (B) | suíte de integração inteira contra o banco do Supabase local com a role operacional | **177 passed** (RLS multiempresa, auth/sessão/CSRF/RBAC, pedidos, NF-e, recebimento parcial, evidências, dossiê) |
| Sprint 4 (B) | suíte completa do backend | **476 passed** (inclui Storage real e E2E API → bucket privado → download) |
| Sprint 5 (prep) | contratos executáveis de dataset e métricas, sem modelo | `backend/exp_vc02/` + 21 testes; `docs/sprint5/PLANO_SPRINT5.md` |
| Sprint 5 (prep) | suíte completa após a preparação | **497 passed** (495 no CI + 2 marcados `supabase_local`) |
| Sprint 4 (B) | prova HML no Supabase local | diagnóstico + semeadura + **12/12 PASS** com `stellspy_app` |
| Sprint 4 (B) | compatibilidade do runner com admin não-superuser | M15 verifica atributos em vez de `ALTER ROLE` (no Supabase `postgres` tem BYPASSRLS, mas não é superuser) |
| Destravamento (B) | verificador de configuração sem expor segredos | `scripts/verificar_env_supabase.py`: 1 bloqueio (senha admin), 2 avisos; `.env` confirmado no `.gitignore` |
| Destravamento (B) | diagnóstico deixa de quebrar com URL-modelo | `problema_na_url_postgres` valida antes do parser; 17 testes do diagnóstico verdes |
| Destravamento (B) | identidade e serviços remotos confirmados (read-only) | `/auth/v1/settings`, `/rest/v1/` e `/storage/v1/bucket` → 200 com `sb-project-ref: akvbtceshpsvsuacueaq`; buckets remotos: `[]` |
| Destravamento (B) | rede do pooler e ausência da role operacional | DNS + TCP `aws-0-us-east-2.pooler.supabase.com:5432` OK; login `stellspy_app.<ref>` → `user not found in the database` |
| Destravamento (B) | configuração local corrigida | senha da role gerada com 43 caracteres; `DATABASE_URL` aponta para pooler real:5432; `EVIDENCIAS_STORAGE=supabase` |
| Destravamento (B) | schema remoto ainda vazio | PostgREST devolve `PGRST205` para `schema_migrations`, `construtoras`, `obras` e `evidencias`; as 30 migrations serão inicialização aditiva, não alteração de dados existentes |
| Destravamento (B) | configuração local aprovada | `verificar_env_supabase.py` → 0 bloqueios, 2 avisos; URL administrativa com senha percent-encoded |
| Destravamento (B) | projeto remoto identificado no diagnóstico | `akvbtceshpsvsuacueaq`, pooler `aws-0-us-east-2`, TCP OK; conexão parou em autenticação |
| Destravamento (B) | autenticação administrativa recusada | pooler de sessão (5432) e de transação (6543) devolvem `password authentication failed`; nenhuma escrita remota |
| Destravamento (B) | regravação segura da senha | `scripts/configurar_senha_admin.py` lê no prompt oculto, percent-encoda e testa a conexão; 3 testes |
| Destravamento (B) | validadores recusam senha sem codificação | `@`, `:`, `/`, `?`, `#`, `[`, `]` exigem percent-encoding; 26 testes dos helpers verdes |
| Validação local (B) | 30 migrations do zero em PostgreSQL 16.15 | suíte de integração **177 passed** (recria schema e aplica 30/30); suíte completa **511 passed, 2 skipped** |
| Validação local (B) | 30 migrations do zero em PostgreSQL 17.11 isolado | container descartável em 55433: `apply_migrations.py` → **30 aplicadas**; 30 versões únicas; role `stellspy_app` (`super=f bypassrls=f createrole=f createdb=f login=t`); 23 tabelas, 20 RLS + 20 FORCE + 20 políticas; `storage` ausente (M30 no-op) |
| Validação local (B) | isolamento RLS com a role operacional no PG 17 | sem `app.tenant_id`: 0 linhas; tenant A vê só A; tenant B vê só B; B não enxerga obra de A |
| Validação local (B) | Storage real contra o Supabase local | `pytest -m supabase_local` → **2 passed** (upload/leitura/duplicado/remoção + API → bucket privado → download) |

## Pendente

- Regravar a senha correta de `postgres.<ref>` com
  `python scripts/configurar_senha_admin.py` (prompt oculto; não vai para o histórico).
- Repetir o diagnóstico remoto e aplicar as 30 migrations pendentes.
- Rodar `hml_staging.py --acao tudo` no projeto oficial e reexecutar para idempotência.
- Homologação funcional HTTP + PWA contra o banco oficial (o fluxo já passa localmente).
- Sprint 5: coletar e anonimizar fotografias do recebimento real; depois anotar,
  treinar e avaliar — nenhum modelo entra no produto sem os portões de
  `exp_vc02` (métricas + validação humana).
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Autenticação administrativa | o pooler recusa a senha atual de `postgres.akvbtceshpsvsuacueaq` (`password authentication failed`). Confira/redo o valor no painel (Settings → Database) e regrave com `scripts/configurar_senha_admin.py`; nunca no chat |
| Mutações remotas | sem a autenticação acima não há como criar a role, aplicar as 30 migrations, criar o bucket ou provar RLS no projeto oficial |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |
| Sprint 5 dados | ≥ 60 obras / ≥ 600 fotos rotuladas; sem isso, não há métrica honesta |

## Último commit de entrega

`35a5ca3` — fix(config): exige percent-encoding na senha e grava sem expor.
(Atualizações de bookkeeping deste arquivo não contam.)

## Próxima ação automática

1. Regravar a senha administrativa correta no prompt oculto (ela não aparece
   no terminal nem no histórico):

   ```
   cd backend && python scripts/configurar_senha_admin.py
   ```

   Hoje a senha gravada é recusada pelo pooler; o helper já testa a conexão.

2. Conferir a configuração e rodar o diagnóstico read-only:

   ```
   cd backend && python scripts/verificar_env_supabase.py
   cd backend && python scripts/diagnostico_supabase.py
   ```

3. Se `migrations_pendentes` contiver arquivos, revisar o diff e só então aplicar
   com o runner lendo o próprio `.env` (sem exportar segredo no shell):

   ```
   cd backend && python scripts/apply_migrations.py --env-file .env
   ```

   Nenhuma operação destrutiva é autorizada.
