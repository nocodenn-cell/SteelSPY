-- Sprint 2 / M27 — Fornecedores, pedidos de compra e conciliação
--
-- O elo que faltava: até aqui o sistema comparava NF-e com a *especificação* da
-- obra. Falta o compromisso comercial — o que a construtora **comprou**.
--
-- Integridade multiempresa no nível do banco:
-- cada tabela carrega `tenant_id` e as foreign keys são COMPOSTAS
-- `(tenant_id, id)`. Assim o Postgres recusa, sozinho, um item de pedido que
-- aponte para pedido de outra construtora — sem depender de código de aplicação
-- lembrar de checar. É a mesma lógica do RLS: o banco fecha, não a disciplina.

-- Alvo das FKs compostas. Redundante com a PK, mas necessário: uma FK composta
-- precisa de um UNIQUE exatamente nas colunas referenciadas.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_obras_tenant_id') THEN
    ALTER TABLE obras ADD CONSTRAINT uq_obras_tenant_id UNIQUE (tenant_id, id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS fornecedores (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id      UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  cnpj           TEXT NOT NULL CHECK (cnpj ~ '^[0-9]{14}$'),
  razao_social   TEXT NOT NULL,
  nome_fantasia  TEXT,
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_fornecedores_tenant_cnpj UNIQUE (tenant_id, cnpj),
  CONSTRAINT uq_fornecedores_tenant_id UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS pedidos_compra (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id         UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  obra_id           UUID NOT NULL,
  fornecedor_id     UUID NOT NULL,
  numero            TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'aberto'
                      CHECK (status IN ('aberto', 'parcial', 'atendido', 'cancelado')),
  valor_total       NUMERIC(14, 2),
  emitido_em        DATE,
  previsao_entrega  DATE,
  observacoes       TEXT,
  erp_ref           TEXT,
  criado_por        UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_pedidos_tenant_numero UNIQUE (tenant_id, numero),
  CONSTRAINT uq_pedidos_tenant_id UNIQUE (tenant_id, id),
  CONSTRAINT fk_pedidos_obra FOREIGN KEY (tenant_id, obra_id)
    REFERENCES obras (tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_pedidos_fornecedor FOREIGN KEY (tenant_id, fornecedor_id)
    REFERENCES fornecedores (tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS pedido_itens (
  id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id           UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  pedido_id           UUID NOT NULL,
  linha               INT NOT NULL CHECK (linha >= 1),
  material_tipo       TEXT NOT NULL,
  categoria_material  TEXT NOT NULL DEFAULT 'aco'
                        CHECK (categoria_material IN ('aco', 'cimento', 'bloco', 'desconhecido')),
  bitola_mm           DOUBLE PRECISION,
  marca_exigida       TEXT,
  quantidade          NUMERIC(14, 3) NOT NULL CHECK (quantidade > 0),
  unidade             TEXT NOT NULL,
  preco_unitario      NUMERIC(14, 4),
  atributos           JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT uq_pedido_itens_linha UNIQUE (pedido_id, linha),
  CONSTRAINT fk_pedido_itens_pedido FOREIGN KEY (tenant_id, pedido_id)
    REFERENCES pedidos_compra (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pedidos_obra ON pedidos_compra (obra_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_pedidos_tenant ON pedidos_compra (tenant_id);
CREATE INDEX IF NOT EXISTS idx_pedido_itens_pedido ON pedido_itens (pedido_id);

-- ---------------------------------------------------------------------------
-- Vínculo NF-e <-> pedido
-- ---------------------------------------------------------------------------
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS pedido_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_nfe_logs_pedido') THEN
    ALTER TABLE nfe_logs ADD CONSTRAINT fk_nfe_logs_pedido
      FOREIGN KEY (tenant_id, pedido_id)
      REFERENCES pedidos_compra (tenant_id, id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_nfe_logs_pedido
  ON nfe_logs (pedido_id) WHERE pedido_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Conciliação de três vias (snapshot auditável)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conciliacoes (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id         UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  pedido_id         UUID NOT NULL,
  nfe_log_id        UUID REFERENCES nfe_logs (id) ON DELETE SET NULL,
  recebimento_id    UUID REFERENCES recebimentos (id) ON DELETE SET NULL,
  -- Snapshot do comparativo. Guardar o resultado, não só o estado atual, é o
  -- que permite responder "por que esta decisão foi tomada em março".
  resultado         JSONB NOT NULL,
  severidade_tecnica TEXT NOT NULL
                      CHECK (severidade_tecnica IN ('VERDE', 'AMARELO', 'VERMELHO')),
  status            TEXT NOT NULL DEFAULT 'em_analise'
                      CHECK (status IN ('em_analise', 'aceita', 'rejeitada')),
  decisao           JSONB,
  criado_por        UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_conciliacoes_pedido FOREIGN KEY (tenant_id, pedido_id)
    REFERENCES pedidos_compra (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conciliacoes_pedido ON conciliacoes (pedido_id, criado_em DESC);

COMMENT ON TABLE pedidos_compra IS
  'Compromisso comercial com fornecedor. Distinto da especificação técnica: aqui é o que foi comprado.';
COMMENT ON TABLE conciliacoes IS
  'Snapshot do confronto pedido x NF-e x recebimento. Append-only: cada conciliação é um fato datado.';
COMMENT ON COLUMN conciliacoes.decisao IS
  'Decisão humana sobre a conciliação (quem, quando, por quê). Nunca automática.';

-- ---------------------------------------------------------------------------
-- RLS desde o nascimento
-- ---------------------------------------------------------------------------
ALTER TABLE fornecedores   ENABLE ROW LEVEL SECURITY;
ALTER TABLE fornecedores   FORCE  ROW LEVEL SECURITY;
ALTER TABLE pedidos_compra ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedidos_compra FORCE  ROW LEVEL SECURITY;
ALTER TABLE pedido_itens   ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido_itens   FORCE  ROW LEVEL SECURITY;
ALTER TABLE conciliacoes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE conciliacoes   FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_fornecedores_tenant ON fornecedores;
CREATE POLICY p_fornecedores_tenant ON fornecedores
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_pedidos_tenant ON pedidos_compra;
CREATE POLICY p_pedidos_tenant ON pedidos_compra
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_pedido_itens_tenant ON pedido_itens;
CREATE POLICY p_pedido_itens_tenant ON pedido_itens
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());

DROP POLICY IF EXISTS p_conciliacoes_tenant ON conciliacoes;
CREATE POLICY p_conciliacoes_tenant ON conciliacoes
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());
