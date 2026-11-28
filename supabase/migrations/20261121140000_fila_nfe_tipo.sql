-- P-08 (continuação): a fila de retentativa passa a distinguir `tipo`.
--
-- Antes, fila_nfe era única por (obra, chave). Com entrada e devolução na mesma
-- chave, as duas retentativas disputavam a mesma linha, e o worker não sabia qual
-- conferência completar. Agora a linha da fila é (obra, chave, tipo).
--
-- A função de claim devolve `tipo` junto. Ela é recriada porque RETURNS TABLE
-- não pode ser alterado por CREATE OR REPLACE. Não é aplicada em produção por esta
-- entrega.

ALTER TABLE fila_nfe ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'entrada'
  CHECK (tipo IN ('entrada', 'devolucao', 'ajuste'));

ALTER TABLE fila_nfe DROP CONSTRAINT IF EXISTS fila_nfe_obra_id_chave_acesso_key;
ALTER TABLE fila_nfe
  ADD CONSTRAINT fila_nfe_obra_chave_tipo_key UNIQUE (obra_id, chave_acesso, tipo);

DROP FUNCTION IF EXISTS fila_reivindicar_lote(INT);

CREATE FUNCTION fila_reivindicar_lote(p_limite INT DEFAULT 50)
RETURNS TABLE (
  id                    UUID,
  tenant_id             UUID,
  obra_id               UUID,
  chave_acesso          VARCHAR,
  tipo                  TEXT,
  tentativas            INT,
  notificado_aguardando BOOLEAN
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  WITH candidatos AS (
    SELECT f.id AS fid
    FROM fila_nfe f
    WHERE f.status = 'pendente'
      AND f.proxima_tentativa <= NOW()
    ORDER BY f.proxima_tentativa
    FOR UPDATE SKIP LOCKED
    LIMIT p_limite
  )
  UPDATE fila_nfe f
     SET status = 'processando',
         updated_at = NOW()
    FROM candidatos c
   WHERE f.id = c.fid
  RETURNING f.id, f.tenant_id, f.obra_id, f.chave_acesso::VARCHAR,
            f.tipo, f.tentativas, f.notificado_aguardando;
END $$;

REVOKE ALL ON FUNCTION fila_reivindicar_lote(INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila_reivindicar_lote(INT) TO stellspy_app;

COMMENT ON FUNCTION fila_reivindicar_lote(INT) IS
  'Claim atômico de fila entre tenants (FOR UPDATE SKIP LOCKED). Devolve tenant_id e tipo para o worker abrir contexto e completar a conferência certa.';
