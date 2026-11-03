-- API Key por obra (piloto): header X-API-KEY deve coincidir com obras.api_key
ALTER TABLE obras ADD COLUMN IF NOT EXISTS api_key TEXT;

UPDATE obras
SET api_key = replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '')
WHERE api_key IS NULL OR trim(api_key) = '';

ALTER TABLE obras ALTER COLUMN api_key SET NOT NULL;

ALTER TABLE obras ALTER COLUMN api_key SET DEFAULT (
  replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_obras_api_key ON obras (api_key);

COMMENT ON COLUMN obras.api_key IS 'Segredo por obra; enviar em header X-API-KEY (comparação em tempo constante na API)';

-- Idempotência: UNIQUE(obra_id, chave_acesso) já está na criação de nfe_logs (core_schema).
COMMENT ON TABLE nfe_logs IS
  'override_info: auditoria de override. Idempotência de negócio: UNIQUE(obra_id, chave_acesso) — um log por NF na obra.';
