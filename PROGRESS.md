# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-03. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE B — integração ao Supabase oficial (`akvbtceshpsvsuacueaq`).**
Bootstrap, RLS e Storage privado provados localmente; diagnóstico remoto
**bloqueado** por credenciais (ver Bloqueios).

## Concluído

| Fase | Entrega | Evidência |
|------|---------|-----------|
| Sprint 3 (A) | PWA, auth, pedidos, NF-e, conciliação, recebimento parcial, evidências, dossiê, RBAC/RLS | merge `7e76713` em `origin/main`; suíte 446 passed |
| VC-01 (C) | protótipo de contagem com recusa, laudo e avaliação | commit `d181779`; `docs/vc01/RELATORIO_VC01.md` — **NO-GO** para contagem automática |
| HML (B) | `backend/scripts/hml_staging.py`: diagnóstico read-only, semeadura HML idempotente e prova de isolamento com a role da aplicação | `stellspy_demo`: 12/12 PASS; reexecução sem duplicar |
| Oficial (B) | projeto Supabase confirmado (`sb-project-ref: akvbtceshpsvsuacueaq`) e declarado oficial | cabeçalho do gateway + decisão do proprietário (2026-11-03) |
| Oficial (B) | banco vazio → 30 migrations → role `stellspy_app` → prova RLS | PostgreSQL 16.15 e 17.11 locais: 30/30 aplicadas; HML 12/12 PASS nas duas versões |
| Oficial (B) | Storage privado de evidências (bucket `evidencias`, chave por tenant/obra) | `armazenamento.py` + migração M30; 16 testes unitários + integração PostgreSQL |
| Oficial (B) | diagnóstico read-only e trava do runner contra role operacional | `scripts/diagnostico_supabase.py`, `apply_migrations.validar_role_migracao` |
| Oficial (B) | `DATABASE_URL` da aplicação separada da URL administrativa | `backend/.env.example`, `docs/CHECKLIST_GOLIVE_SUPABASE.md` |

## Pendente

- Preencher `backend/.env` com `SUPABASE_DB_ADMIN_URL`, `DATABASE_URL` (role app),
  `STELLSPY_APP_PASSWORD`, `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
- Rodar diagnóstico remoto, revisar divergências e aplicar as migrations pendentes.
- Rodar `hml_staging.py --acao tudo` no projeto oficial e reexecutar para idempotência.
- Homologação funcional HTTP + PWA contra o banco oficial.
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Diagnóstico remoto | `SUPABASE_DB_ADMIN_URL` + `SUPABASE_SERVICE_ROLE_KEY` em `backend/.env` (não colar no chat; arquivo ignorado) |
| Region/versão remota | só são conhecidas após a conexão (pooler revela a região no host) |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |

## Último commit

`6c2476e` — feat(hml): ferramenta de homologação com dados sintéticos e prova de isolamento.

## Próxima ação automática

Assim que `backend/.env` existir:

```
cd backend && python scripts/diagnostico_supabase.py
```

Se `migrations_pendentes` contiver arquivos, revisar o diff e só então aplicar
com `apply_migrations.py --url "$SUPABASE_DB_ADMIN_URL"`. Nenhuma operação
destrutiva é autorizada.
