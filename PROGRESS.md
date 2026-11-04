# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-04. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE B — Supabase oficial homologado (`akvbtceshpsvsuacueaq`).**
O destravamento da senha administrativa foi confirmado em 2026-11-04. As 30
migrations foram aplicadas no projeto oficial (0 → 30/30), a role `stellspy_app`
foi criada sem `BYPASSRLS`, o bucket `evidencias` nasceu privado, a HML com duas
construtoras sintéticas passou 12/12 e o E2E HTTP gravou e leu uma evidência real
no Storage oficial com SHA-256 conferido. O remoto está homologado para os fluxos
cobertos; deploy/push seguem fora de escopo.

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
| Remoto (B) | configuração e conexão administrativa aprovadas | `verificar_env_supabase.py` → 0 bloqueios, 2 avisos; `diagnostico_supabase.py` conecta como `postgres.<ref>` ao projeto `akvbtceshpsvsuacueaq` (PG 17.11) |
| Remoto (B) | migrations aplicadas no projeto oficial | `apply_migrations.py --env-file .env` → **30 aplicadas** (0 → 30/30, 16:51 UTC); reexecução → **0 pendentes** |
| Remoto (B) | role operacional criada e utilizável | `stellspy_app` com `super=f bypassrls=f createrole=f createdb=f login=t`; login por `DATABASE_URL` OK; sem contexto de tenant vê 0 construtoras |
| Remoto (B) | RLS/FORCE/políticas no schema oficial | 23 tabelas em `public`, **20 com RLS + 20 FORCE + 20 políticas**; `tenant_sem_rls=[]` |
| Remoto (B) | HML com duas construtoras sintéticas | **12/12 PASS**: sem contexto 0 usuários; A vê só A; B vê só B; update/insert cruzados bloqueados; pedido e NF-e de A invisíveis para B |
| Remoto (B) | HML idempotente | segunda execução com o mesmo prefixo manteve os mesmos IDs, 3 usuários e 2 construtoras; **12/12 PASS** de novo |
| Remoto (B) | Storage oficial privado | bucket `evidencias` (`public=false`, 12 MiB); ciclo real upload/leitura/duplicado/remoção → **1 passed**; rota pública não entrega o objeto |
| Remoto (B) | E2E HTTP no banco oficial | login sintético → upload **201** → download normalizado e original **200**; bytes originais idênticos e SHA-256 normalizado/original conferem; cross-tenant **404** |
| Remoto (B) | suíte completa após as correções | **514 passed, 2 skipped** |

## Pendente

- Homologação funcional do PWA no navegador contra o banco oficial (o fluxo HTTP
  já passa; falta a interface em aparelho/navegador real).
- Definir `CORS_ALLOW_ORIGINS` com as origens exatas antes de qualquer deploy.
- Decidir o destino dos dados sintéticos HML no projeto oficial: permanecem duas
  construtoras `hml-*`, 3 usuários e uma evidência. A limpeza automática pode ser
  bloqueada pela FK de evidências; qualquer remoção exige autorização explícita.
- Rotacionar a senha administrativa usada no destravamento, por higiene, depois
  de concluída a janela de homologação.
- Sprint 5: coletar e anonimizar fotografias do recebimento real; depois anotar,
  treinar e avaliar — nenhum modelo entra no produto sem os portões de
  `exp_vc02` (métricas + validação humana).
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Deploy | fora de escopo por instrução; nada foi publicado nem enviado ao Git remoto |
| PWA em aparelho real | câmera e fluxo de campo ainda não exercitados no navegador do celular |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |
| Sprint 5 dados | ≥ 60 obras / ≥ 600 fotos rotuladas; sem isso, não há métrica honesta |

## Último commit de entrega

`ef0fe4c` — fix(hml): compara migrations pelo nome completo e filtra RLS por tenant.
(Atualizações de bookkeeping deste arquivo não contam.)

## Próxima ação automática

1. Homologar o PWA no navegador contra o banco oficial (login, obra, upload pela
   câmera, download e bloqueio cross-tenant). O E2E HTTP já passou; falta a
   interface real. Em HTTP local, subir o backend com `PWA_COOKIE_SECURE=0`
   apenas no processo de teste.
2. Definir `CORS_ALLOW_ORIGINS` com as origens exatas antes de qualquer deploy.
3. Decidir com o proprietário o destino dos dados HML sintéticos e a rotação da
   senha administrativa após a janela de homologação.
4. Sprint 5: coletar e anonimizar fotografias reais; nenhum modelo entra no
   produto sem os portões de `exp_vc02`.

Nenhuma operação destrutiva, push ou deploy é autorizada sem pedido explícito.
