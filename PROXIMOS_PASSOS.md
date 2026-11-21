# PROXIMOS_PASSOS

> Visão curta e viva. O detalhamento histórico (P-01…P-18, gates, riscos) fica em
> `docs/execucao/PROXIMOS_PASSOS.md`; a análise de defeitos, em `ANALISE_PROJETO.md`.

## P0 — Quebrado/travado

## P1 — Falta para lançar (MVP)

- **Integração `claude/integracao-auditoria-2026-11-21`: aguardar aprovação antes de push, PR ou merge.** Nada foi enviado ao remoto. Detalhes em `docs/AUDITORIA_REVALIDACAO_2026-11-21.md` §12.
- **Validar a ordem da migração `20261114120000_fila_reaper.sql`** num banco descartável que já tenha `20261121120000`–`20261121140000` aplicadas (ela entra fora de sequência). Antes de qualquer aplicação em produção.
- **Decidir a agregação do override:** `54a7b21` ficou de fora porque `52fee46` (P-09) já cobre o mesmo achado com outro desenho (`VERDE` e `vermelhos_aceitos` em vez de `ACEITO_OVERRIDE` e `aceitos_por_override`). Confirmar o desenho escolhido.
- **P-11.2 — auditoria de obras com `modo_aprendizado = TRUE` — BLOQUEADA (sem acesso de leitura ao banco de produção).**
  - Causa: nesta sessão não há acesso ao banco de produção do SteelSPY. Na conta Supabase conectada, os projetos `jinlong` e `jinlong-homolog-palm` não têm a tabela `obras`, e o staging está inativo. O banco de teste local não respondeu (Docker com erro 500 no daemon).
  - Pronto: `docs/execucao/AUDITORIA_MODO_APRENDIZADO.sql`, somente leitura (`SET TRANSACTION READ ONLY`, termina em `ROLLBACK`), com 4 blocos: contagem de obras; por obra (conferências, rebaixadas, abertas, overrides); divergências não resolvidas por tipo; impacto nos últimos 90 dias. Não foi executado: a validação de sintaxe falhou por indisponibilidade do banco de teste.
  - Para desbloquear: rodar o script num usuário somente leitura no banco de produção e enviar a saída (ou os CSVs). Sem isso, nenhum número é conhecido.
  - Análise de risco, sem dados ainda:
    - Manter TRUE: NFs tecnicamente VERMELHAS entram como AMARELO e a entrada não é bloqueada. Não há registro obrigatório de decisão humana para essas NFs, então material não conforme pode entrar sem responsável.
    - Mudar para FALSE: em obra em implantação, o fiscal passa a ver muitos VERMELHOS e pode travar o fluxo. A mudança só vale para conferências novas; as antigas não mudam.
    - Não há coluna de prazo para o modo de aprendizado. Não dá para saber se uma obra o ligou de propósito e até quando.
  - Recomendação preliminar, em lote: obras sem nenhuma conferência podem passar a FALSE sem impacto histórico. Obras com conferências e rebaixamentos recentes precisam de decisão individual, com o responsável da obra. Não recomendo UPDATE em lote sem a saída do script.

## P2 — Melhoria

- Teste de corrida de idempotência: o tempo de setup do banco varia de 3 s a 160 s entre execuções isoladas. Investigar (suspeita: migrações completas a cada execução) antes de usar a suíte como gate de CI
- `M4` ainda parcial: limite de `/conferir` por obra e `correlation_id`
- Trazer `b87aed2` (testes de bordas com PostgreSQL: `/conferir`, `/override`, PDFs, fila) da branch `claude/steelspy-project-analysis-dec4d1`, após revisão
- Remover o container de validação `stellspy-pg-migr-validacao-20261121` (porta 55440) quando não for mais necessário
- Fatores de conversão de cimento (28 sacos/m³, 1400 kg/m³) estão como constantes em `normalizacao_cimento.py`; ler da tabela `normalizacao_materiais` por obra/fornecedor
- Sem equivalência para `m²`, `L` e `lata` (tinta, argamassa): hoje ficam "não comparável" e vão para conferência manual
- Limiar de tolerância de quantidade de cimento/bloco (2% e 10%) está duplicado nos dois comparadores; centralizar
- P-12 fila presa em `processando`, P-13 deprecações do `fpdf2` (55 warnings na suíte), P-17 erro de banco 500→503, P-03 gate de licença

## Feito

- 2026-11-21 — Integração em `claude/integracao-auditoria-2026-11-21`: A6 (`DATABASE_URL` obrigatória em produção e `.env` carregado), M4 parcial (`/health` responde 503 quando o banco cai), M9 (laudo só pela API, sem redirect nem bucket público), M1 (reaper `fila_reaper_travadas` e exceção em `buscar_xml` não prendem a linha). Migração `20261114120000_fila_reaper.sql`. Suíte completa com PostgreSQL: 505 passam, 0 pulados
- 2026-11-21 — Teste de corrida de idempotência estabilizado sem best-effort: a barreira fica antes da checagem de idempotência (as N requisições disputam o índice único) e espera 30 s sem ignorar falha; os testes de integração usam `127.0.0.1` (no Windows, `localhost` esperava ~21 s por conexão em IPv6). Mutação sem rollback no `IntegrityError` faz o teste falhar. 10 de 10 execuções isoladas passam. Suíte: 494 passam, 0 pulados
- 2026-11-21 — P-11 (padrão do modo de aprendizado): o padrão do código (`ConfigObraConferente` e fallback) passa a `FALSE`, igual ao padrão do banco da migração 20261103150300. Obras existentes não são alteradas. Suíte: 494 passam, 0 pulados
- 2026-11-21 — CSV semanal ganha a coluna `itens_vermelhos_aceitos` ao fim (colunas anteriores mantêm a posição). Vazia quando a NF nunca foi aceita por override. Suíte: 493 passam, 0 pulados
- 2026-11-21 — Fila de retentativa com `tipo`: `fila_nfe` passa a ser única por (obra, chave, tipo); `fila_reivindicar_lote` devolve `tipo`; o worker completa a conferência certa (devolução não toca na entrada pendente). Migração `20261121140000`, não aplicada em produção. Suíte: 491 passam, 0 pulados. Mutação (callback sempre `entrada`) fez o teste falhar
- 2026-11-21 — P-09 (override inconsistente): o aceite marca `nfe_itens.override_aplicado` (o `status_item` técnico continua VERMELHO); `itens_resumo` passa a bater com VERDE, guardando a contagem anterior em `vermelhos_aceitos`; o dashboard projeta VERDE para item aceito; o replay de `/conferir` devolve `status` efetivo, `status_tecnico` e `override`. Migração `20261121130000`, não aplicada em produção. Suíte: 489 passam, 0 pulados. Mutação (sem marcar itens) fez o teste falhar
- 2026-11-21 — P-08 (idempotência ignora `tipo`): a unicidade de `nfe_logs` passa a ser `(obra_id, chave_acesso, tipo)`. A busca de idempotência de `/conferir` filtra por `tipo`, então devolução com a mesma chave da entrada vira conferência própria e a entrada não é mais sobrescrita. Migração `20261121120000` (não aplicada em produção). Suíte: 488 passam, 0 pulados. Mutação (sem o filtro por `tipo`) fez 2 testes falharem
- 2026-11-21 — P-07 (SSRF em `foto_url`): redirects não são mais seguidos automaticamente; cada salto é validado (https, porta 443, hostname) e o DNS precisa resolver só para endereços públicos. A conexão vai ao IP validado, com SNI e Host do hostname, o que fecha DNS rebinding. Proxy do ambiente ignorado. +43 testes (redirect malicioso, IP privado, IPv4 mapeado, DNS misto, rebinding, URL inválida, tamanho). Mutação confirmou os testes. Suíte: 484 passam, 0 pulados
- 2026-11-19 — `correlacao.chave_base`: sacos e toneladas convergem para kg (mesma conversão da conferência); pedido em sacos casa com NF em kg. Corrigido bug: o saldo era mantido em kg cru e a soma faturada misturava kg com metros. Sem bitola, linha em sacos/t só casa com item de mesma categoria detectada. m³ segue base própria (densidade depende do material). Suíte completa: 441 passam, 0 pulados (265 unitários + 176 de integração contra PostgreSQL)
- 2026-11-18 — Suíte de integração executada contra PostgreSQL 16 (container `stellspy-pg`, porta 55432): 176 passam, 0 pulados. Suíte completa: 436 passam, 0 pulados
