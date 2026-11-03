-- Fase 0 / M21 — Sessões de usuário com revogação
--
-- O cookie carrega um identificador de sessão (`jti`) assinado por HMAC. A
-- assinatura impede adulteração; esta tabela permite **revogação** — algo que
-- um token autocontido sozinho não oferece.
--
-- Sem esta tabela, "sair" só limparia o cookie no navegador e o token roubado
-- continuaria válido até expirar. Com ela, o logout invalida no servidor.
--
-- `tenant_id` e `usuario_id` são gravados no servidor e conferidos a cada
-- requisição. O navegador não escolhe tenant nem papel: ele só devolve o jti.

CREATE TABLE IF NOT EXISTS sessoes (
  id           UUID PRIMARY KEY,               -- jti do cookie, gerado no servidor
  tenant_id    UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  usuario_id   UUID NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
  criada_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expira_em    TIMESTAMPTZ NOT NULL,
  revogada_em  TIMESTAMPTZ,
  motivo_revogacao TEXT,
  ip           INET,
  user_agent   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessoes_usuario
  ON sessoes (usuario_id) WHERE revogada_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_sessoes_expira
  ON sessoes (expira_em) WHERE revogada_em IS NULL;

COMMENT ON TABLE sessoes IS
  'Sessões ativas. Permite revogação imediata (logout, incidente, troca de papel).';
COMMENT ON COLUMN sessoes.id IS
  'jti: identificador opaco embutido no cookie assinado. É a única coisa que o cliente devolve.';
