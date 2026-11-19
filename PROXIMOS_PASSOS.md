# PROXIMOS_PASSOS

> Visão curta e viva. O detalhamento histórico (P-01…P-18, gates, riscos) fica em
> `docs/execucao/PROXIMOS_PASSOS.md`; a análise de defeitos, em `ANALISE_PROJETO.md`.

## P0 — Quebrado/travado

## P1 — Falta para lançar (MVP)

- P-11 (A2): `modo_aprendizado` nasce ligado por padrão e rebaixa VERMELHO para AMARELO; obra nova deveria nascer bloqueando (`docs/execucao/PROXIMOS_PASSOS.md`)
- P-08 (A4): idempotência ignora `tipo`, então devolução da mesma chave retorna a conferência original
- P-09 (A3): override humano deixa `status_calculado` e `status_efetivo` incoerentes
- P-07 (A1): SSRF via redirect em `foto_url`

## P2 — Melhoria

- Fatores de conversão de cimento (28 sacos/m³, 1400 kg/m³) estão como constantes em `normalizacao_cimento.py`; ler da tabela `normalizacao_materiais` por obra/fornecedor
- Sem equivalência para `m²`, `L` e `lata` (tinta, argamassa): hoje ficam "não comparável" e vão para conferência manual
- Limiar de tolerância de quantidade de cimento/bloco (2% e 10%) está duplicado nos dois comparadores; centralizar
- Duas tabelas de unidades (`correlacao.chave_base` e `conferente`) ainda coexistem; unificar evitando o import circular
- P-12 fila presa em `processando`, P-13 deprecações do `fpdf2` (55 warnings na suíte), P-17 erro de banco 500→503, P-03 gate de licença

## Feito

- 2026-11-18 — Suíte de integração executada contra PostgreSQL 16 (container `stellspy-pg`, porta 55432): 176 passam, 0 pulados. Suíte completa: 436 passam, 0 pulados
- 2026-11-18 — Aço: `quantidade_recebida_em_metros` passa a aceitar toneladas, PC/PCS/PCT, MT/M1, minúsculas e `metros_por_barra` nulo (usa 12 m); unidade desconhecida segue gerando AMARELO. +5 testes (260 passam)
- 2026-11-18 — Conferência de cimento/bloco normaliza unidade antes de comparar (1400 kg = 28 sacos = 1 m³); unidade sem conversão segura vira AMARELO "não comparável" em vez de percentual inventado; mensagens de quantidade agora geram a tag e o alerta `QUANTIDADE_DIVERGENTE`; dimensões de bloco comparadas por números (`19 x 19 x 39 cm` = `19x19x39`). +13 testes (255 passam)
