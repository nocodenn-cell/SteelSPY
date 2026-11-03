-- Fase 0 / M17 — tenant_id nas tabelas operacionais (expand)
--
-- Passo 1 de 3 do expand-contract, igual ao usado em `obras`:
--   M17 (aqui)  colunas NULLABLE + índices
--   M18         backfill a partir da obra dona
--   M19         NOT NULL + foreign keys
--   M20         RLS + policies
--
-- `nfe_itens` recebe `tenant_id` desnormalizado de `nfe_logs` de propósito: a
-- policy de RLS precisa comparar coluna com coluna. Se ela consultasse
-- `nfe_logs`, a própria consulta passaria por RLS e poderia entrar em recursão.
--
-- `fila_nfe` também recebe: o worker processa itens de vários tenants e precisa
-- saber de quem é cada linha antes de abrir contexto.

ALTER TABLE nfe_logs       ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE nfe_itens      ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE especificacoes ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE fila_nfe       ADD COLUMN IF NOT EXISTS tenant_id UUID;

CREATE INDEX IF NOT EXISTS idx_nfe_logs_tenant       ON nfe_logs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_nfe_itens_tenant      ON nfe_itens (tenant_id);
CREATE INDEX IF NOT EXISTS idx_especificacoes_tenant ON especificacoes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_fila_nfe_tenant       ON fila_nfe (tenant_id);

COMMENT ON COLUMN nfe_logs.tenant_id IS
  'Construtora dona da conferência. Desnormalizado de obras para o RLS não depender de JOIN.';
COMMENT ON COLUMN nfe_itens.tenant_id IS
  'Desnormalizado de nfe_logs para permitir policy sem subconsulta recursiva.';
COMMENT ON COLUMN especificacoes.tenant_id IS
  'Construtora dona da especificação. Desnormalizado de obras.';
COMMENT ON COLUMN fila_nfe.tenant_id IS
  'Construtora dona do item de fila. Permite ao worker abrir contexto por item.';
