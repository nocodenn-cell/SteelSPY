-- Fase 0 / M13 — fecha o contrato do tenant em obras
--
-- Passo 3 de 3 do expand-contract: NOT NULL + foreign key.
-- A FK usa ON DELETE RESTRICT: apagar uma construtora com obras deve ser um
-- ato deliberado, nunca um efeito colateral.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM obras WHERE tenant_id IS NULL) THEN
    RAISE EXCEPTION
      'obras com tenant_id NULL — rode o backfill (M12) antes de fechar o contrato';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_obras_tenant'
  ) THEN
    ALTER TABLE obras
      ADD CONSTRAINT fk_obras_tenant
      FOREIGN KEY (tenant_id) REFERENCES construtoras (id) ON DELETE RESTRICT;
  END IF;
END $$;

ALTER TABLE obras ALTER COLUMN tenant_id SET NOT NULL;
