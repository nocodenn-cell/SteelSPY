-- Fase 1 / M25 — Recebimentos, evidências e trilha de auditoria
--
-- `recebimentos` nasce aqui (mínima) porque é o pai natural da evidência: uma
-- foto sem recebimento não tem a que se referir. Os campos de conferência
-- entram na Sprint 2, na mesma tabela, por migração aditiva.
--
-- Princípios desta fase:
--   * o arquivo ORIGINAL é imutável — nunca é sobrescrito nem normalizado;
--   * a normalização gera um SEGUNDO artefato, com hash próprio;
--   * o caminho interno de armazenamento nunca sai na API;
--   * evidência é dado de tenant: RLS obrigatório.

CREATE TABLE IF NOT EXISTS recebimentos (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id      UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  obra_id        UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  tipo           TEXT NOT NULL DEFAULT 'entrada'
                   CHECK (tipo IN ('entrada', 'devolucao', 'ajuste')),
  status         TEXT NOT NULL DEFAULT 'aberto'
                   CHECK (status IN ('aberto', 'conferido', 'encerrado')),
  id_cliente     UUID,
  observacoes    TEXT,
  criado_por     UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  recebido_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recebimentos_obra ON recebimentos (obra_id, recebido_em DESC);
CREATE INDEX IF NOT EXISTS idx_recebimentos_tenant ON recebimentos (tenant_id);

-- Idempotência de sincronização offline: o mesmo id do dispositivo não duplica.
CREATE UNIQUE INDEX IF NOT EXISTS uq_recebimentos_id_cliente
  ON recebimentos (obra_id, id_cliente) WHERE id_cliente IS NOT NULL;

CREATE TABLE IF NOT EXISTS evidencias (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id           UUID NOT NULL REFERENCES construtoras (id) ON DELETE RESTRICT,
  obra_id             UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  recebimento_id      UUID REFERENCES recebimentos (id) ON DELETE CASCADE,

  -- Hash do que foi recebido (prova do original) e do que armazenamos.
  sha256_original     CHAR(64) NOT NULL,
  sha256              CHAR(64) NOT NULL,

  -- Chaves opacas. NUNCA retornadas pela API.
  storage_key_original TEXT NOT NULL,
  storage_key          TEXT NOT NULL,

  mime_original       TEXT NOT NULL,
  mime                TEXT NOT NULL,
  bytes_original      INT NOT NULL CHECK (bytes_original > 0),
  bytes               INT NOT NULL CHECK (bytes > 0),
  largura             INT,
  altura              INT,

  origem              TEXT NOT NULL DEFAULT 'upload'
                        CHECK (origem IN ('camera', 'galeria', 'upload', 'integracao')),
  tipo                TEXT NOT NULL DEFAULT 'material'
                        CHECK (tipo IN ('material', 'etiqueta', 'nfe', 'lacre', 'documento')),

  -- Metadado do dispositivo: informativo, NUNCA usado como horário de negócio.
  capturada_em        TIMESTAMPTZ,
  -- Horário do servidor: é o que vale para métricas e ordenação.
  recebida_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  criado_por          UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  removido_em         TIMESTAMPTZ
);

-- Antifraude: a mesma imagem não pode servir de prova para dois recebimentos
-- da mesma obra. É também o que torna o upload idempotente.
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidencias_obra_sha
  ON evidencias (obra_id, sha256) WHERE removido_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_evidencias_recebimento ON evidencias (recebimento_id);
CREATE INDEX IF NOT EXISTS idx_evidencias_obra ON evidencias (obra_id, recebida_em DESC);
CREATE INDEX IF NOT EXISTS idx_evidencias_tenant ON evidencias (tenant_id);

CREATE TABLE IF NOT EXISTS evidencia_eventos (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  evidencia_id  UUID NOT NULL REFERENCES evidencias (id) ON DELETE CASCADE,
  tipo          TEXT NOT NULL
                  CHECK (tipo IN ('recebida', 'armazenada', 'baixada', 'rejeitada', 'expurgada')),
  detalhe       JSONB NOT NULL DEFAULT '{}'::jsonb,
  autor_id      UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidencia_eventos_evid ON evidencia_eventos (evidencia_id, criado_em);

COMMENT ON TABLE evidencias IS
  'Arquivo de evidência imutável. O original nunca é alterado; a normalização gera outro artefato.';
COMMENT ON COLUMN evidencias.storage_key_original IS
  'Chave interna do arquivo original. Uso exclusivo do servidor; não vai para a API.';
COMMENT ON COLUMN evidencias.capturada_em IS
  'Metadado do dispositivo. Pode estar errado; não serve como horário de negócio.';
COMMENT ON COLUMN evidencias.recebida_em IS
  'Horário do servidor. Fonte de verdade para ordenação e métricas.';
COMMENT ON TABLE evidencia_eventos IS
  'Trilha append-only: nunca UPDATE, nunca DELETE. Prova quem fez o quê e quando.';

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE recebimentos      ENABLE ROW LEVEL SECURITY;
ALTER TABLE recebimentos      FORCE  ROW LEVEL SECURITY;
ALTER TABLE evidencias        ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidencias        FORCE  ROW LEVEL SECURITY;
ALTER TABLE evidencia_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidencia_eventos FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_recebimentos_tenant ON recebimentos;
CREATE POLICY p_recebimentos_tenant ON recebimentos
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_evidencias_tenant ON evidencias;
CREATE POLICY p_evidencias_tenant ON evidencias
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_evidencia_eventos_tenant ON evidencia_eventos;
CREATE POLICY p_evidencia_eventos_tenant ON evidencia_eventos
  USING (tenant_id = tenant_atual())
  WITH CHECK (tenant_id = tenant_atual());
