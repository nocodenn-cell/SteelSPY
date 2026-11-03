-- Sprint 2 / M26 — Idempotência de evidência: operação ≠ arquivo
--
-- O índice anterior era `(obra_id, sha256)`: a mesma imagem nunca podia existir
-- duas vezes na obra. Isso resolvia idempotência de retry, mas impedia um caso
-- legítimo — o fiscal fotografa o mesmo material em dois recebimentos — e não
-- deixava rastro quando alguém reutilizava uma foto antiga como prova nova.
--
-- Agora há três identidades distintas, e cada uma tem seu mecanismo:
--
--   operação de upload  -> `idempotency_key` (gerada pelo cliente)
--   arquivo             -> `sha256` / `sha256_original` (imutável)
--   prova do recebimento -> `(recebimento_id, sha256)` único
--
-- Reutilização entre recebimentos diferentes passa a ser permitida, mas
-- **sinalizada**: `reutilizada_de` aponta para a primeira evidência da obra com
-- aquele conteúdo e `sinalizacao_fraude` fica verdadeiro. O produto não bloqueia
-- — ele mostra. Quem decide é o humano, com o dado na mão.

DROP INDEX IF EXISTS uq_evidencias_obra_sha;

ALTER TABLE evidencias
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS reutilizada_de UUID REFERENCES evidencias (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS sinalizacao_fraude BOOLEAN NOT NULL DEFAULT FALSE;

-- Retry da mesma operação: devolve a evidência já criada.
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidencias_idempotencia
  ON evidencias (obra_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND removido_em IS NULL;

-- Uma foto por recebimento. O mesmo arquivo em outro recebimento é permitido,
-- mas conta como reutilização.
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidencias_recebimento_sha
  ON evidencias (recebimento_id, sha256)
  WHERE recebimento_id IS NOT NULL AND removido_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_evidencias_sha_obra
  ON evidencias (obra_id, sha256) WHERE removido_em IS NULL;

COMMENT ON COLUMN evidencias.idempotency_key IS
  'Chave da operação de upload, gerada no dispositivo. Reenvio com a mesma chave devolve a evidência existente.';
COMMENT ON COLUMN evidencias.reutilizada_de IS
  'Primeira evidência da obra com o mesmo conteúdo. Preenchido quando a imagem é reaproveitada em outro recebimento.';
COMMENT ON COLUMN evidencias.sinalizacao_fraude IS
  'Verdadeiro quando o mesmo arquivo já existia na obra em outro recebimento ou contexto. Não bloqueia; sinaliza.';
