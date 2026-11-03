-- Fase 0 / M19 — fecha o contrato: NOT NULL + foreign keys
--
-- A FK aponta para `construtoras` (não para `obras`): a obra pode ser removida
-- com CASCADE, mas o vínculo com o tenant é a garantia de isolamento e não deve
-- desaparecer por um DELETE em cascata.

DO $$
DECLARE
  faltando TEXT := '';
BEGIN
  IF EXISTS (SELECT 1 FROM nfe_logs WHERE tenant_id IS NULL) THEN
    faltando := faltando || ' nfe_logs';
  END IF;
  IF EXISTS (SELECT 1 FROM nfe_itens WHERE tenant_id IS NULL) THEN
    faltando := faltando || ' nfe_itens';
  END IF;
  IF EXISTS (SELECT 1 FROM especificacoes WHERE tenant_id IS NULL) THEN
    faltando := faltando || ' especificacoes';
  END IF;
  IF EXISTS (SELECT 1 FROM fila_nfe WHERE tenant_id IS NULL) THEN
    faltando := faltando || ' fila_nfe';
  END IF;

  IF faltando <> '' THEN
    RAISE EXCEPTION 'backfill incompleto — rode M18 antes. Tabelas: %', faltando;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_nfe_logs_tenant') THEN
    ALTER TABLE nfe_logs ADD CONSTRAINT fk_nfe_logs_tenant
      FOREIGN KEY (tenant_id) REFERENCES construtoras (id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_nfe_itens_tenant') THEN
    ALTER TABLE nfe_itens ADD CONSTRAINT fk_nfe_itens_tenant
      FOREIGN KEY (tenant_id) REFERENCES construtoras (id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_especificacoes_tenant') THEN
    ALTER TABLE especificacoes ADD CONSTRAINT fk_especificacoes_tenant
      FOREIGN KEY (tenant_id) REFERENCES construtoras (id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fila_nfe_tenant') THEN
    ALTER TABLE fila_nfe ADD CONSTRAINT fk_fila_nfe_tenant
      FOREIGN KEY (tenant_id) REFERENCES construtoras (id) ON DELETE RESTRICT;
  END IF;
END $$;

ALTER TABLE nfe_logs       ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE nfe_itens      ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE especificacoes ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE fila_nfe       ALTER COLUMN tenant_id SET NOT NULL;
