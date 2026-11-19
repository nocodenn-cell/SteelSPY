# PROXIMOS_PASSOS

> Visão curta e viva. O detalhamento histórico (P-01…P-18, gates, riscos) fica em
> `docs/execucao/PROXIMOS_PASSOS.md`; a análise de defeitos, em `ANALISE_PROJETO.md`.

## P0 — Quebrado/travado

## P1 — Falta para lançar (MVP)

- Aplicar o mesmo tratamento de unidade ao aço: `quantidade_recebida_em_metros` (`app/domain/conferente.py`) não conhece `TON`, `PC` nem `SC`, e unidade desconhecida vira AMARELO genérico; reaproveitar `chave_base` de `correlacao.py`
- Executar a suíte de integração (`backend/tests/integration`) contra PostgreSQL real: nesta sessão só os 255 testes unitários rodaram, sem banco
- P-11 (A2): `modo_aprendizado` nasce ligado por padrão e rebaixa VERMELHO para AMARELO; obra nova deveria nascer bloqueando (`docs/execucao/PROXIMOS_PASSOS.md`)
- P-08 (A4): idempotência ignora `tipo`, então devolução da mesma chave retorna a conferência original
- P-09 (A3): override humano deixa `status_calculado` e `status_efetivo` incoerentes
- P-07 (A1): SSRF via redirect em `foto_url`

## P2 — Melhoria

- Fatores de conversão de cimento (28 sacos/m³, 1400 kg/m³) estão como constantes em `normalizacao_cimento.py`; ler da tabela `normalizacao_materiais` por obra/fornecedor
- Sem equivalência para `m²`, `L` e `lata` (tinta, argamassa): hoje ficam "não comparável" e vão para conferência manual
- Limiar de tolerância de quantidade de cimento/bloco (2% e 10%) está duplicado nos dois comparadores; centralizar
- P-12 fila presa em `processando`, P-13 deprecações do `fpdf2` (55 warnings na suíte), P-17 erro de banco 500→503, P-03 gate de licença

## Feito

- 2026-11-18 — Conferência de cimento/bloco normaliza unidade antes de comparar (1400 kg = 28 sacos = 1 m³); unidade sem conversão segura vira AMARELO "não comparável" em vez de percentual inventado; mensagens de quantidade agora geram a tag e o alerta `QUANTIDADE_DIVERGENTE`; dimensões de bloco comparadas por números (`19 x 19 x 39 cm` = `19x19x39`). +13 testes (255 passam)
