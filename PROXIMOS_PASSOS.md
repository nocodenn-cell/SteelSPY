# PROXIMOS_PASSOS

> Visão curta e viva. O detalhamento histórico (P-01…P-18, gates, riscos) fica em
> `docs/execucao/PROXIMOS_PASSOS.md`; a análise de defeitos, em `ANALISE_PROJETO.md`.

## P0 — Quebrado/travado

- **Role da `DATABASE_URL` de produção (plano, passo 2): pendente de resposta do usuário.** Se a role for `postgres` (com `BYPASSRLS`), o RLS não protege a API e a afirmação de isolamento multiempresa fica suspensa. Trocar a credencial por `stellspy_app` é ação de produção, fora da sprint. Detalhes em `docs/AUDITORIA_REVALIDACAO_2026-11-21.md` §13.4.

## P1 — Falta para lançar (MVP)

- **Revisar e fazer merge do PR #3 (`claude/integracao-auditoria-2026-11-21`) no `main`: aguardando aprovação do usuário.** Nada foi mesclado. A integração está pronta para revisão (ver §13 da auditoria).
- **Bucket público de laudos: ação operacional do usuário**, fora da sprint. A sprint não resolve LGPD sozinha.
- **M7 no CI:** `.github/workflows/testes.yml` roda só o pytest. Incluir `npm run test` e `npm run build:css` no pipeline.
- **Validar a ordem da migração `20261114120000_fila_reaper.sql`** antes de aplicar em produção (ela entra fora de sequência com `20261121*`). Em banco novo, na ordem pelo nome, a aplicação passou.
- **Ícones do PWA:** os PNGs em `pwa/assets/icons/` são provisórios (cor sólida). Trocar pela arte da marca.
- **P-11.2 — auditoria de obras com `modo_aprendizado = TRUE` — BLOQUEADA (sem acesso de leitura ao banco de produção).**
  - Pronto: `docs/execucao/AUDITORIA_MODO_APRENDIZADO.sql`, somente leitura (`SET TRANSACTION READ ONLY`, termina em `ROLLBACK`). Não foi executado.
  - Para desbloquear: rodar o script num usuário somente leitura no banco de produção e enviar a saída. Sem isso, nenhum número é conhecido.
  - Recomendação preliminar, em lote: obras sem nenhuma conferência podem passar a FALSE sem impacto histórico. Obras com conferências e rebaixamentos recentes precisam de decisão individual. Não recomendo UPDATE em lote sem a saída do script.

## P2 — Melhoria

- Teste de corrida de idempotência: o tempo de setup do banco varia (3 s a 160 s; 119 s na última sprint). Investigar antes de usar a suíte como gate de CI.
- Limite de `/conferir` por obra (M4) e de login são em memória por processo: com N workers o teto efetivo é N × limite. Trocar por Redis ou tabela no Postgres se houver mais de uma instância.
- B14 residual: a espera de retentativa do WhatsApp é limitada a 10 s, mas ainda ocupa a thread do `BackgroundTasks`. Retentativa assíncrona ou fila.
- M3 (dicionário de sinônimos): decidido não implementar agora; a tabela `sinonimos` segue sem uso. Reabrir só com demanda.
- Trazer `b87aed2` (testes de bordas com PostgreSQL) da branch `claude/steelspy-project-analysis-dec4d1`, após revisão
- Remover o container de validação `stellspy-pg-migr-validacao-20261121` (porta 55440) quando não for mais necessário
- Fatores de conversão de cimento (28 sacos/m³, 1400 kg/m³) estão como constantes em `normalizacao_cimento.py`; ler da tabela `normalizacao_materiais` por obra/fornecedor
- Sem equivalência para `m²`, `L` e `lata` (tinta, argamassa): hoje ficam "não comparável" e vão para conferência manual
- Limiar de tolerância de quantidade de cimento/bloco (2% e 10%) está duplicado nos dois comparadores; centralizar
- P-12 fila presa em `processando` (reaper já integrado; revisar), P-17 erro de banco 500→503, P-03 gate de licença

## Feito

- 2026-11-28 — Sprint de fechamento do PR #3: B12 (migração `20261127120000` com unicidade de especificação por bitola; aborta com duplicatas) e B14 (espera de retentativa do WhatsApp limitada a 10 s). Suíte: 539 passam, 0 pulados (PostgreSQL 16 novo)
- 2026-11-28 — PWA: esperado e recebido por item (B4), ícones 192 e 512 no manifest (B6), `npm run test` com 8 testes reais (M7). Commit `110f46e`
- 2026-11-28 — Limpeza: `utcnow` (B7), fpdf2 sem `ln=`/`dest=` e sem negrito falso (B8), chave `conclusao` com alias de leitura (B10), dia de São Paulo no dashboard (B13), espaçamento, docstring, checklist de migrações, CSS base e retirada do dicionário de sinônimos da documentação (B1, B2, B3, B11, M3). Commits `5b59981`, `a1fe72d`, `6bb3696`
- 2026-11-28 — Segurança e custo: teto de consultas pagas por obra em `/conferir` (M4, 429 com `Retry-After`) e `X-Correlation-ID` (M4); CGNAT `100.64.0.0/10` bloqueado em `foto_url` (B9). Commit `3a7b1bd`
- 2026-11-21 — Integração em `claude/integracao-auditoria-2026-11-21`: A6 (`DATABASE_URL` obrigatória em produção e `.env` carregado), M4 parcial (`/health` responde 503 quando o banco cai), M9 (laudo só pela API, sem redirect nem bucket público), M1 (reaper `fila_reaper_travadas` e exceção em `buscar_xml` não prendem a linha). Migração `20261114120000_fila_reaper.sql`. Suíte completa com PostgreSQL: 505 passam, 0 pulados
- 2026-11-21 — Teste de corrida de idempotência estabilizado sem best-effort: a barreira fica antes da checagem de idempotência e espera 30 s sem ignorar falha; os testes de integração usam `127.0.0.1` (no Windows, `localhost` esperava ~21 s por conexão em IPv6). Suíte: 494 passam, 0 pulados
- 2026-11-21 — P-11 (padrão do modo de aprendizado): o padrão do código passa a `FALSE`, igual ao padrão do banco da migração 20261103150300. Obras existentes não são alteradas. Suíte: 494 passam, 0 pulados
- 2026-11-21 — CSV semanal ganha a coluna `itens_vermelhos_aceitos` ao fim (colunas anteriores mantêm a posição). Suíte: 493 passam, 0 pulados
- 2026-11-21 — Fila de retentativa com `tipo`: `fila_nfe` passa a ser única por (obra, chave, tipo); o worker completa a conferência certa. Migração `20261121140000`, não aplicada em produção. Suíte: 491 passam, 0 pulados
- 2026-11-21 — P-09 (override inconsistente): o aceite marca `nfe_itens.override_aplicado`; `itens_resumo` passa a bater com VERDE; o replay de `/conferir` devolve `status`, `status_tecnico` e `override`. Migração `20261121130000`, não aplicada em produção. Suíte: 489 passam, 0 pulados
