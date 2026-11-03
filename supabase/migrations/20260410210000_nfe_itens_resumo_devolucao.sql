-- Itens normalizados por linha da NF + resumo global + vínculo NF devolução
CREATE TABLE nfe_itens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nfe_log_id UUID NOT NULL REFERENCES nfe_logs (id) ON DELETE CASCADE,
  item_numero INT NOT NULL CHECK (item_numero >= 1),
  material_recebido TEXT,
  bitola_recebida DOUBLE PRECISION,
  marca_recebida TEXT,
  quantidade_recebida DOUBLE PRECISION,
  unidade_recebida TEXT,
  status_item TEXT NOT NULL CHECK (status_item IN ('VERDE', 'AMARELO', 'VERMELHO')),
  divergencias JSONB NOT NULL DEFAULT '[]'::jsonb,
  mensagem_item TEXT,
  especificacao_id UUID REFERENCES especificacoes (id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (nfe_log_id, item_numero)
);

CREATE INDEX idx_nfe_itens_log ON nfe_itens (nfe_log_id);

ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS resumo_global TEXT;
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS itens_resumo JSONB;
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS nf_original_id UUID REFERENCES nfe_logs (id) ON DELETE SET NULL;
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'entrada'
  CHECK (tipo IN ('entrada', 'devolucao', 'ajuste'));

CREATE INDEX idx_nfe_logs_nf_original ON nfe_logs (nf_original_id) WHERE nf_original_id IS NOT NULL;

COMMENT ON COLUMN nfe_logs.resumo_global IS 'Texto curto para fiscal/WhatsApp; detalhe em nfe_itens';
COMMENT ON COLUMN nfe_logs.itens_resumo IS 'JSON: {total, verdes, amarelos, vermelhos}';
COMMENT ON COLUMN nfe_logs.status_conferencia IS 'Status global = pior entre itens (VERDE/AMARELO/VERMELHO/PENDENTE)';
COMMENT ON COLUMN nfe_logs.tipo IS 'entrada=NF de compra; devolucao=NF que referencia nf_original_id';
