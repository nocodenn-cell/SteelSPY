# PROXIMOS_PASSOS

> Visão curta e viva. O detalhamento histórico (P-01…P-18, gates, riscos) fica em
> `docs/execucao/PROXIMOS_PASSOS.md`; a análise de defeitos, em `ANALISE_PROJETO.md`.

## P0 — Quebrado/travado

## P1 — Falta para lançar (MVP)

- P-11 (A2): `modo_aprendizado` nasce ligado por padrão e rebaixa VERMELHO para AMARELO; obra nova deveria nascer bloqueando (`docs/execucao/PROXIMOS_PASSOS.md`)
- P-08 (A4): idempotência ignora `tipo`, então devolução da mesma chave retorna a conferência original
- P-09 (A3): override humano deixa `status_calculado` e `status_efetivo` incoerentes

## P2 — Melhoria

- Fatores de conversão de cimento (28 sacos/m³, 1400 kg/m³) estão como constantes em `normalizacao_cimento.py`; ler da tabela `normalizacao_materiais` por obra/fornecedor
- Sem equivalência para `m²`, `L` e `lata` (tinta, argamassa): hoje ficam "não comparável" e vão para conferência manual
- Limiar de tolerância de quantidade de cimento/bloco (2% e 10%) está duplicado nos dois comparadores; centralizar
- P-12 fila presa em `processando`, P-13 deprecações do `fpdf2` (55 warnings na suíte), P-17 erro de banco 500→503, P-03 gate de licença

## Feito

- 2026-11-21 — P-07 (SSRF em `foto_url`): redirects não são mais seguidos automaticamente; cada salto é validado (https, porta 443, hostname) e o DNS precisa resolver só para endereços públicos. A conexão vai ao IP validado, com SNI e Host do hostname, o que fecha DNS rebinding. Proxy do ambiente ignorado. +43 testes (redirect malicioso, IP privado, IPv4 mapeado, DNS misto, rebinding, URL inválida, tamanho). Mutação confirmou os testes. Suíte: 484 passam, 0 pulados
- 2026-11-19 — `correlacao.chave_base`: sacos e toneladas convergem para kg (mesma conversão da conferência); pedido em sacos casa com NF em kg. Corrigido bug: o saldo era mantido em kg cru e a soma faturada misturava kg com metros. Sem bitola, linha em sacos/t só casa com item de mesma categoria detectada. m³ segue base própria (densidade depende do material). Suíte completa: 441 passam, 0 pulados (265 unitários + 176 de integração contra PostgreSQL)
- 2026-11-18 — Suíte de integração executada contra PostgreSQL 16 (container `stellspy-pg`, porta 55432): 176 passam, 0 pulados. Suíte completa: 436 passam, 0 pulados
- 2026-11-18 — Aço: `quantidade_recebida_em_metros` passa a aceitar toneladas, PC/PCS/PCT, MT/M1, minúsculas e `metros_por_barra` nulo (usa 12 m); unidade desconhecida segue gerando AMARELO. +5 testes (260 passam)
- 2026-11-18 — Conferência de cimento/bloco normaliza unidade antes de comparar (1400 kg = 28 sacos = 1 m³); unidade sem conversão segura vira AMARELO "não comparável" em vez de percentual inventado; mensagens de quantidade agora geram a tag e o alerta `QUANTIDADE_DIVERGENTE`; dimensões de bloco comparadas por números (`19 x 19 x 39 cm` = `19x19x39`). +13 testes (255 passam)
