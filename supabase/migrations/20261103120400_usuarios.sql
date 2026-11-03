-- Fase 0 / M14 — Usuários, vínculo com obras e papéis
--
-- Modelo de autorização em duas camadas:
--   usuarios.papel_global  -> teto do que a pessoa pode fazer na construtora
--   obra_usuarios.papel    -> alcance dentro de cada obra
--
-- Um `fiscal` global não enxerga obra em que não foi vinculado.
--
-- `obra_usuarios.tenant_id` é desnormalizado de propósito: a policy de RLS
-- precisa comparar coluna com coluna. Se a policy consultasse `obras`, a
-- própria consulta passaria por RLS e poderia entrar em recursão.

CREATE TABLE IF NOT EXISTS usuarios (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id      UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  nome           TEXT NOT NULL,
  email          TEXT NOT NULL,
  senha_hash     TEXT,
  papel_global   TEXT NOT NULL DEFAULT 'fiscal'
                   CHECK (papel_global IN ('admin_tenant', 'engenheiro', 'fiscal', 'auditor')),
  ativo          BOOLEAN NOT NULL DEFAULT TRUE,
  ultimo_login   TIMESTAMPTZ,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- E-mail é único por construtora, não globalmente: a mesma pessoa pode ser
-- fiscal em duas construtoras diferentes.
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_tenant_email
  ON usuarios (tenant_id, lower(email));
CREATE INDEX IF NOT EXISTS idx_usuarios_tenant ON usuarios (tenant_id);

CREATE TABLE IF NOT EXISTS obra_usuarios (
  tenant_id   UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  obra_id     UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  usuario_id  UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
  papel       TEXT NOT NULL CHECK (papel IN ('engenheiro', 'fiscal', 'auditor')),
  criado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (obra_id, usuario_id)
);

CREATE INDEX IF NOT EXISTS idx_obra_usuarios_tenant ON obra_usuarios (tenant_id);
CREATE INDEX IF NOT EXISTS idx_obra_usuarios_usuario ON obra_usuarios (usuario_id);

COMMENT ON TABLE usuarios IS
  'Usuários da construtora. senha_hash NULL = acesso apenas por outro mecanismo (futuro magic link).';
COMMENT ON COLUMN usuarios.papel_global IS
  'Teto de permissão na construtora: admin_tenant | engenheiro | fiscal | auditor.';
COMMENT ON TABLE obra_usuarios IS
  'Vínculo usuário-obra com papel local. Sem vínculo, o usuário não acessa a obra.';
COMMENT ON COLUMN obra_usuarios.tenant_id IS
  'Desnormalizado de obras para permitir policy de RLS sem subconsulta recursiva.';
