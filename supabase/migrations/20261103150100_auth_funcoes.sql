-- Fase 0 / M22 — RLS das sessões + funções de autenticação
--
-- Toda autenticação acontece ANTES de existir contexto de tenant. Por isso as
-- leituras de login e de validação de sessão passam por funções SECURITY
-- DEFINER estreitas. Elas são a única porta que atravessa o RLS, e cada uma
-- recebe um único valor (e-mail ou jti) — nunca SQL, nunca filtro livre.

ALTER TABLE sessoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessoes FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_sessoes_tenant ON sessoes;
CREATE POLICY p_sessoes_tenant ON sessoes
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

-- ---------------------------------------------------------------------------
-- Login: encontrar candidatos por e-mail
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_login_lookup(p_email TEXT)
RETURNS TABLE (
  usuario_id   UUID,
  tenant_id    UUID,
  tenant_slug  TEXT,
  nome         TEXT,
  senha_hash   TEXT,
  papel_global TEXT,
  usuario_ativo BOOLEAN,
  tenant_ativo  BOOLEAN
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT u.id, u.tenant_id, c.slug, u.nome, u.senha_hash, u.papel_global,
         u.ativo, c.ativo
  FROM usuarios u
  JOIN construtoras c ON c.id = u.tenant_id
  WHERE lower(u.email) = lower(p_email)
  ORDER BY c.criado_em, u.criado_em
$$;

REVOKE ALL ON FUNCTION auth_login_lookup(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_login_lookup(TEXT) TO stellspy_app;

-- ---------------------------------------------------------------------------
-- Validação de sessão a cada requisição
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_validar_sessao(p_jti UUID)
RETURNS TABLE (
  usuario_id    UUID,
  tenant_id     UUID,
  papel_global  TEXT,
  nome          TEXT,
  email         TEXT,
  expira_em     TIMESTAMPTZ,
  revogada      BOOLEAN,
  usuario_ativo BOOLEAN,
  tenant_ativo  BOOLEAN
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT s.usuario_id, s.tenant_id, u.papel_global, u.nome, u.email,
         s.expira_em, (s.revogada_em IS NOT NULL), u.ativo, c.ativo
  FROM sessoes s
  JOIN usuarios u     ON u.id = s.usuario_id
  JOIN construtoras c ON c.id = s.tenant_id
  WHERE s.id = p_jti
$$;

REVOKE ALL ON FUNCTION auth_validar_sessao(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_validar_sessao(UUID) TO stellspy_app;

-- ---------------------------------------------------------------------------
-- Revogação (logout, incidente, troca de papel)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_revogar_sessao(p_jti UUID, p_motivo TEXT DEFAULT 'logout')
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  afetadas INT;
BEGIN
  UPDATE sessoes
     SET revogada_em = COALESCE(revogada_em, NOW()),
         motivo_revogacao = COALESCE(motivo_revogacao, p_motivo)
   WHERE id = p_jti;
  GET DIAGNOSTICS afetadas = ROW_COUNT;
  RETURN afetadas > 0;
END $$;

REVOKE ALL ON FUNCTION auth_revogar_sessao(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_revogar_sessao(UUID, TEXT) TO stellspy_app;

-- ---------------------------------------------------------------------------
-- Vínculo do usuário com a obra (autorização por obra)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth_papel_na_obra(p_usuario_id UUID, p_obra_id UUID)
RETURNS TEXT
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ou.papel
  FROM obra_usuarios ou
  WHERE ou.usuario_id = p_usuario_id
    AND ou.obra_id = p_obra_id
  LIMIT 1
$$;

REVOKE ALL ON FUNCTION auth_papel_na_obra(UUID, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_papel_na_obra(UUID, UUID) TO stellspy_app;

COMMENT ON FUNCTION auth_papel_na_obra(UUID, UUID) IS
  'Papel do usuário naquela obra. NULL = sem vínculo, e sem vínculo nada é permitido.';
