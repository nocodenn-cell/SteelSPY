-- Fase 0 / M18 — backfill do tenant nas tabelas operacionais
--
-- A fonte da verdade é sempre a obra. `nfe_itens` herda do `nfe_logs`, que por
-- sua vez herda da obra — por isso a ordem importa: logs primeiro, itens depois.
--
-- Idempotente: só toca linhas com tenant_id NULL.

DO $$
DECLARE
  n_logs  INT;
  n_itens INT;
  n_specs INT;
  n_fila  INT;
BEGIN
  UPDATE nfe_logs n
     SET tenant_id = o.tenant_id
    FROM obras o
   WHERE o.id = n.obra_id
     AND n.tenant_id IS NULL;
  GET DIAGNOSTICS n_logs = ROW_COUNT;

  -- Depois dos logs, para herdar o valor já preenchido.
  UPDATE nfe_itens i
     SET tenant_id = n.tenant_id
    FROM nfe_logs n
   WHERE n.id = i.nfe_log_id
     AND i.tenant_id IS NULL;
  GET DIAGNOSTICS n_itens = ROW_COUNT;

  UPDATE especificacoes e
     SET tenant_id = o.tenant_id
    FROM obras o
   WHERE o.id = e.obra_id
     AND e.tenant_id IS NULL;
  GET DIAGNOSTICS n_specs = ROW_COUNT;

  UPDATE fila_nfe f
     SET tenant_id = o.tenant_id
    FROM obras o
   WHERE o.id = f.obra_id
     AND f.tenant_id IS NULL;
  GET DIAGNOSTICS n_fila = ROW_COUNT;

  RAISE NOTICE 'backfill: nfe_logs=% nfe_itens=% especificacoes=% fila_nfe=%',
    n_logs, n_itens, n_specs, n_fila;
END $$;
