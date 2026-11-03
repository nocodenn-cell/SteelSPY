-- Evita reenvio do mesmo relatório no mesmo dia lógico (chave + timestamp)
ALTER TABLE obras ADD COLUMN IF NOT EXISTS relatorio_ultimo_periodo_chave TEXT;
ALTER TABLE obras ADD COLUMN IF NOT EXISTS relatorio_ultimo_envio_em TIMESTAMPTZ;

COMMENT ON COLUMN obras.relatorio_ultimo_periodo_chave IS
  'Chave do último envio (ex.: steelspy:v1:7d:2026-04-13:BR); repetir mesmo dia = skip';
COMMENT ON COLUMN obras.relatorio_ultimo_envio_em IS 'Momento UTC do último envio com sucesso';
