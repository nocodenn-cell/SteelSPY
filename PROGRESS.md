# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-03. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE B — homologação no Supabase staging.** Ferramenta pronta e provada localmente;
execução remota **bloqueada** por credenciais (ver Bloqueios).

## Concluído

| Fase | Entrega | Evidência |
|------|---------|-----------|
| Sprint 3 (A) | PWA, auth, pedidos, NF-e, conciliação, recebimento parcial, evidências, dossiê, RBAC/RLS | merge `7e76713` em `origin/main`; suíte 446 passed |
| VC-01 (C) | protótipo de contagem com recusa, laudo e avaliação | commit `d181779`; `docs/vc01/RELATORIO_VC01.md` — **NO-GO** para contagem automática |
| HML (B) | `backend/scripts/hml_staging.py`: diagnóstico read-only, semeadura HML idempotente e prova de isolamento com a role da aplicação | execução local contra `stellspy_demo`: 12/12 PASS, re-execução sem duplicar |

## Pendente

- Executar `hml_staging.py` no staging (`akvbtceshpsvsuacueaq`) e produzir a matriz PASS/FAIL.
- Homologação funcional HTTP + PWA contra o staging.
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Staging stellSPY | `DATABASE_URL` do pooler e `STELLSPY_APP_PASSWORD` (não colar no chat; usar `.devtmp/staging.env`, já ignorado pelo Git) |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |

## Último commit

`d181779` — feat(vc01): protótipo de contagem de vergalhões com recusa e avaliação.

## Próxima ação automática

Rodar o diagnóstico read-only no staging assim que a credencial existir:

```
cd backend && python scripts/hml_staging.py --acao diagnostico
```

Se `schema_migrations` estiver atrás do branch, parar e registrar — migração remota exige
autorização explícita.
