# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-04. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE B — integração ao Supabase oficial (`akvbtceshpsvsuacueaq`).**
Sprint 4 homologada localmente sobre o próprio stack Supabase (PostgreSQL 17.11).
O destravamento remoto avançou até onde não depende da senha administrativa:
projeto, Auth, REST e Storage respondem; a role operacional **não existe** no
projeto remoto e o único bloqueio restante é a senha real do usuário
`postgres.<ref>` (ver Bloqueios).

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

## Pendente

- Substituir **apenas** a senha-modelo de `SUPABASE_DB_ADMIN_URL` pela senha real
  de `postgres.<ref>` (painel → Database → Connection string → Session pooler).
- Rodar diagnóstico remoto, revisar divergências e aplicar as migrations pendentes.
- Rodar `hml_staging.py --acao tudo` no projeto oficial e reexecutar para idempotência.
- Homologação funcional HTTP + PWA contra o banco oficial (o fluxo já passa localmente).
- Sprint 5: coletar e anonimizar fotografias do recebimento real; depois anotar,
  treinar e avaliar — nenhum modelo entra no produto sem os portões de
  `exp_vc02` (métricas + validação humana).
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Diagnóstico remoto | senha real de `postgres.akvbtceshpsvsuacueaq` dentro de `SUPABASE_DB_ADMIN_URL` (o valor atual é `[SENHA_POSTGRES]`). Colocar em `backend/.env`, nunca no chat |
| Mutações remotas | sem a credencial acima não há como criar a role, aplicar as 30 migrations, criar o bucket ou provar RLS no projeto oficial |
| Suíte de integração nesta sessão | Docker Desktop parado; os 177 testes de integração exigem o container PostgreSQL em 55432 (evidência anterior segue válida) |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |
| Sprint 5 dados | ≥ 60 obras / ≥ 600 fotos rotuladas; sem isso, não há métrica honesta |

## Último commit de entrega

`6263fb0` — fix(diagnostico): valida URL-modelo e verifica env sem expor segredos.
(Atualizações de bookkeeping deste arquivo não contam.)

## Próxima ação automática

1. Conferir a configuração local sem expor segredos:

   ```
   cd backend && python scripts/verificar_env_supabase.py
   ```

   Hoje: `1 bloqueio` — `SUPABASE_DB_ADMIN_URL` com placeholder.

2. Assim que a senha real estiver no `.env`, rodar o diagnóstico read-only:

   ```
   cd backend && python scripts/diagnostico_supabase.py
   ```

3. Se `migrations_pendentes` contiver arquivos, revisar o diff e só então aplicar
   com o runner lendo o próprio `.env` (sem exportar segredo no shell):

   ```
   cd backend && python scripts/apply_migrations.py --env-file .env
   ```

   Nenhuma operação destrutiva é autorizada.
