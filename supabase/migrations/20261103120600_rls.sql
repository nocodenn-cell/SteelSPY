-- Fase 0 / M16 — RLS, FORCE, policies e bootstrap de tenant
--
-- Modelo:
--   * a role da aplicação (stellspy_app) NÃO tem BYPASSRLS e NÃO é dona das tabelas;
--   * FORCE ROW LEVEL SECURITY garante que nem o dono escape por acidente;
--   * cada transação declara `SET LOCAL app.tenant_id` (ver app/tenant.py);
--   * o login precisa descobrir o tenant ANTES de existir contexto de sessão.
--     Para isso existem duas funções SECURITY DEFINER estreitas, e só elas.
--
-- As funções são SECURITY DEFINER de propósito: rodam como o dono (que tem
-- BYPASSRLS neste ambiente), permitindo o bootstrap. Elas recebem apenas um
-- UUID e devolvem uma linha — não aceitam SQL, não listam, não filtram por
-- texto livre.

-- ---------------------------------------------------------------------------
-- Helper: tenant da transação corrente
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION tenant_atual() RETURNS UUID
LANGUAGE sql STABLE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

COMMENT ON FUNCTION tenant_atual() IS
  'Lê app.tenant_id da transação. NULL quando não há contexto — e aí nenhuma linha é visível.';

-- ---------------------------------------------------------------------------
-- RLS: ligar e FORÇAR nas tabelas com tenant
-- ---------------------------------------------------------------------------
ALTER TABLE construtoras   ENABLE ROW LEVEL SECURITY;
ALTER TABLE construtoras   FORCE  ROW LEVEL SECURITY;
ALTER TABLE obras          ENABLE ROW LEVEL SECURITY;
ALTER TABLE obras          FORCE  ROW LEVEL SECURITY;
ALTER TABLE usuarios       ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios       FORCE  ROW LEVEL SECURITY;
ALTER TABLE obra_usuarios  ENABLE ROW LEVEL SECURITY;
ALTER TABLE obra_usuarios  FORCE  ROW LEVEL SECURITY;

-- construtoras: a linha é o próprio tenant
DROP POLICY IF EXISTS p_construtoras_tenant ON construtoras;
CREATE POLICY p_construtoras_tenant ON construtoras
  USING (id = tenant_atual())
  WITH CHECK (id = tenant_atual());

-- demais: comparação direta de coluna
DROP POLICY IF EXISTS p_obras_tenant ON obras;
CREATE POLICY p_obras_tenant ON obras
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_usuarios_tenant ON usuarios;
CREATE POLICY p_usuarios_tenant ON usuarios
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_obra_usuarios_tenant ON obra_usuarios;
CREATE POLICY p_obra_usuarios_tenant ON obra_usuarios
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

-- ---------------------------------------------------------------------------
-- Bootstrap: obra por id (usado no login e no carregamento da obra)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_lookup_obra(p_obra_id UUID)
RETURNS TABLE (
  id                     UUID,
  tenant_id              UUID,
  nome                   TEXT,
  cnpj_destinatario      TEXT,
  aceita_similar         BOOLEAN,
  margem_tolerancia_float DOUBLE PRECISION,
  modo_aprendizado       BOOLEAN,
  api_key                TEXT,
  whatsapp_destino       TEXT
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT o.id, o.tenant_id, o.nome, o.cnpj_destinatario,
         o.aceita_similar, o.margem_tolerancia_float,
         o.modo_aprendizado, o.api_key, o.whatsapp_destino
  FROM obras o
  WHERE o.id = p_obra_id
$$;

REVOKE ALL ON FUNCTION auth_lookup_obra(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_lookup_obra(UUID) TO stellspy_app;

COMMENT ON FUNCTION auth_lookup_obra(UUID) IS
  'Bootstrap de tenant por obra. SECURITY DEFINER: única porta que atravessa RLS, e só por id exato.';

-- ---------------------------------------------------------------------------
-- Bootstrap: tenant a partir do id de um nfe_log
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_lookup_nfe_log_tenant(p_nfe_log_id UUID)
RETURNS TABLE (obra_id UUID, tenant_id UUID)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT n.obra_id, o.tenant_id
  FROM nfe_logs n
  JOIN obras o ON o.id = n.obra_id
  WHERE n.id = p_nfe_log_id
$$;

REVOKE ALL ON FUNCTION auth_lookup_nfe_log_tenant(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_lookup_nfe_log_tenant(UUID) TO stellspy_app;

COMMENT ON FUNCTION auth_lookup_nfe_log_tenant(UUID) IS
  'Resolve a obra e o tenant de um nfe_log antes de abrir o contexto transacional.';
