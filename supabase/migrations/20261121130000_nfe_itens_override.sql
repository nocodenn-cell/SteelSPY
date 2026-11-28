-- P-09 (A3): o aceite (override) passa a ser registrado nos itens, sem apagar a
-- severidade técnica.
--
-- Antes, o override mudava só nfe_logs.status_conferencia para VERDE. Os itens
-- continuavam VERMELHO: o dashboard contava vermelhos com a NF verde, e o resumo
-- do relatório semanal contradizia o status.
--
-- Agora:
--   * nfe_itens.status_item continua sendo o fato técnico (VERMELHO);
--   * nfe_itens.override_aplicado marca o item aceito; quem mostra o status
--     efetivo (dashboard) projeta VERDE para esses itens;
--   * nfe_logs.itens_resumo guarda a contagem técnica anterior em
--     `vermelhos_aceitos` e zera `vermelhos`, para bater com o status VERDE.
--
-- Não é aplicada em produção por esta entrega.

ALTER TABLE nfe_itens ADD COLUMN IF NOT EXISTS override_aplicado BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN nfe_itens.override_aplicado IS
  'TRUE quando um responsável aceitou a divergência deste item. status_item guarda o fato técnico; o status efetivo é VERDE quando override_aplicado.';

-- Backfill dos aceites feitos antes desta migração. A regra é a mesma do endpoint
-- de override (conferencia.py, POST /override) e do replay: a NF tem aceite quando
-- override_info->'historico' é um array não vazio; os itens VERMELHO dela recebem
-- override_aplicado. Idempotente: só altera linhas ainda não marcadas.
UPDATE nfe_itens ni
   SET override_aplicado = TRUE
  FROM nfe_logs nl
 WHERE nl.id = ni.nfe_log_id
   AND ni.status_item = 'VERMELHO'
   AND ni.override_aplicado = FALSE
   AND jsonb_typeof(nl.override_info -> 'historico') = 'array'
   AND jsonb_array_length(nl.override_info -> 'historico') > 0;
