-- Fase 0 / M10 — Construtoras (tenant raiz do SaaS)
--
-- Uma construtora = um tenant. Todo agregado do sistema passa a carregar
-- tenant_id e é isolado por RLS (ver 20261103120600_rls.sql).
--
-- `cnpj` é opcional nesta fase: o operador atual pode não ter o CNPJ em mãos e
-- inventar um seria criar dado falso. Vira obrigatório quando houver a 2ª
-- construtora (gate AC0.10).

CREATE TABLE IF NOT EXISTS construtoras (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome            TEXT NOT NULL,
  cnpj            TEXT CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'),
  slug            TEXT CHECK (slug IS NULL OR slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  plano           TEXT NOT NULL DEFAULT 'piloto'
                    CHECK (plano IN ('piloto', 'core', 'enterprise')),
  retencao_meses  INT NOT NULL DEFAULT 24
                    CHECK (retencao_meses BETWEEN 1 AND 120),
  ativo           BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices parciais: permitem várias linhas com NULL e continuam impondo
-- unicidade sobre valores preenchidos.
CREATE UNIQUE INDEX IF NOT EXISTS uq_construtoras_cnpj
  ON construtoras (cnpj) WHERE cnpj IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_construtoras_slug
  ON construtoras (slug) WHERE slug IS NOT NULL;

COMMENT ON TABLE construtoras IS
  'Tenant raiz do SaaS. Uma construtora possui N obras; todo dado operacional carrega tenant_id.';
COMMENT ON COLUMN construtoras.retencao_meses IS
  'Prazo de retenção de evidências, por contrato. Padrão 24 meses (LGPD/política interna).';
