-- Fase 0 / M20 — RLS nas tabelas operacionais + reivindicação de fila
--
-- Fecha o isolamento no dado de negócio: conferência, itens, especificações e
-- fila passam a ser invisíveis fora do tenant da transação.
--
-- Exceção deliberada e única: o worker precisa pegar trabalho de vários tenants
-- antes de saber de quem é cada linha. Para isso existe `fila_reivindicar_lote`,
-- SECURITY DEFINER, que só faz o claim e devolve o `tenant_id` junto. O worker
-- então abre o contexto e executa o resto sob RLS normalmente.

ALTER TABLE nfe_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE nfe_logs       FORCE  ROW LEVEL SECURITY;
ALTER TABLE nfe_itens      ENABLE ROW LEVEL SECURITY;
ALTER TABLE nfe_itens      FORCE  ROW LEVEL SECURITY;
ALTER TABLE especificacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE especificacoes FORCE  ROW LEVEL SECURITY;
ALTER TABLE fila_nfe       ENABLE ROW LEVEL SECURITY;
ALTER TABLE fila_nfe       FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_nfe_logs_tenant ON nfe_logs;
CREATE POLICY p_nfe_logs_tenant ON nfe_logs
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_nfe_itens_tenant ON nfe_itens;
CREATE POLICY p_nfe_itens_tenant ON nfe_itens
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_especificacoes_tenant ON especificacoes;
CREATE POLICY p_especificacoes_tenant ON especificacoes
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_fila_nfe_tenant ON fila_nfe;
CREATE POLICY p_fila_nfe_tenant ON fila_nfe
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

-- ---------------------------------------------------------------------------
-- Claim de fila multi-tenant
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fila_reivindicar_lote(p_limite INT DEFAULT 50)
RETURNS TABLE (
  id                    UUID,
  tenant_id             UUID,
  obra_id               UUID,
  chave_acesso          VARCHAR,
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
            f.tentativas, f.notificado_aguardando;
END $$;

REVOKE ALL ON FUNCTION fila_reivindicar_lote(INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila_reivindicar_lote(INT) TO stellspy_app;

COMMENT ON FUNCTION fila_reivindicar_lote(INT) IS
  'Claim atômico de fila entre tenants (FOR UPDATE SKIP LOCKED). Devolve tenant_id para o worker abrir contexto.';
