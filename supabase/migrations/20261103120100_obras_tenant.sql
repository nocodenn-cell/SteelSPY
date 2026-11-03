-- Fase 0 / M11 — tenant_id em obras (expand)
--
-- Passo 1 de 3 do expand-contract:
--   M11 (aqui)  adiciona a coluna NULLABLE + índice
--   M12         faz o backfill para a construtora padrão
--   M13         aplica NOT NULL + foreign key
--
-- Separar permite que o backfill rode como job em bases grandes, sem segurar
-- um ACCESS EXCLUSIVE prolongado.

ALTER TABLE obras ADD COLUMN IF NOT EXISTS tenant_id UUID;

CREATE INDEX IF NOT EXISTS idx_obras_tenant ON obras (tenant_id);

COMMENT ON COLUMN obras.tenant_id IS
  'Construtora (tenant) dona da obra. Base do isolamento por RLS.';
