-- Multi-material: categorias na especificação + tabela de fatores de normalização (cimento/bloco).

-- 1) Colunas em especificacoes (idempotente)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'especificacoes' AND column_name = 'categoria_material'
  ) THEN
    ALTER TABLE especificacoes
      ADD COLUMN categoria_material TEXT NOT NULL DEFAULT 'aco'
      CHECK (categoria_material IN ('aco', 'cimento', 'bloco', 'desconhecido'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'especificacoes' AND column_name = 'atributos_especificos'
  ) THEN
    ALTER TABLE especificacoes
      ADD COLUMN atributos_especificos JSONB NOT NULL DEFAULT '{}'::jsonb;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'especificacoes' AND column_name = 'quantidade_prevista'
  ) THEN
    ALTER TABLE especificacoes ADD COLUMN quantidade_prevista DOUBLE PRECISION;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'especificacoes' AND column_name = 'unidade_prevista'
  ) THEN
    ALTER TABLE especificacoes ADD COLUMN unidade_prevista TEXT;
  END IF;
END $$;

COMMENT ON COLUMN especificacoes.categoria_material IS 'aco | cimento | bloco | desconhecido — define qual ramo do comparador usar';
COMMENT ON COLUMN especificacoes.atributos_especificos IS 'JSON: tipo CP, fck_mpa, slump_mm, dimensoes, etc.';
COMMENT ON COLUMN especificacoes.quantidade_prevista IS 'Planejado na unidade de unidade_prevista (cimento/bloco); aço continua usando qtd_planejada_metros';
COMMENT ON COLUMN especificacoes.unidade_prevista IS 'Ex.: sacos, m3, kg, pecas, m2';

-- 2) Fatores de conversão (seed idempotente)
CREATE TABLE IF NOT EXISTS normalizacao_materiais (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  categoria TEXT NOT NULL CHECK (categoria IN ('cimento', 'bloco')),
  nome TEXT NOT NULL,
  unidade_origem TEXT NOT NULL,
  unidade_destino TEXT NOT NULL,
  fator_conversao DOUBLE PRECISION NOT NULL,
  parametros JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (categoria, nome, unidade_origem, unidade_destino)
);

COMMENT ON TABLE normalizacao_materiais IS 'Regras sacos↔m³, kg↔m³, peças↠m²; parametros trazem densidade, pecas_por_m2, etc.';

-- 3) Seed cimento (1 saco = 1/28 m³; 50 kg/saco; ~1400 kg/m³ massa aparente)
INSERT INTO normalizacao_materiais (categoria, nome, unidade_origem, unidade_destino, fator_conversao, parametros)
VALUES
  ('cimento', 'CP-II', 'sacos', 'm3', 1.0 / 28.0, '{"kg_por_saco": 50, "sacos_por_m3": 28}'::jsonb),
  ('cimento', 'CP-II', 'kg', 'sacos', 1.0 / 50.0, '{"kg_por_saco": 50}'::jsonb),
  ('cimento', 'CP-II', 'kg', 'm3', 1.0 / 1400.0, '{"densidade_kg_m3": 1400}'::jsonb),
  ('cimento', 'CP-V', 'sacos', 'm3', 1.0 / 28.0, '{"kg_por_saco": 50, "sacos_por_m3": 28}'::jsonb),
  ('cimento', 'CP-V', 'kg', 'sacos', 1.0 / 50.0, '{"kg_por_saco": 50}'::jsonb),
  ('cimento', 'CP-V', 'kg', 'm3', 1.0 / 1400.0, '{"densidade_kg_m3": 1400}'::jsonb)
ON CONFLICT (categoria, nome, unidade_origem, unidade_destino) DO NOTHING;

-- 4) Seed blocos (exemplos — alinhar com planilha da obra)
INSERT INTO normalizacao_materiais (categoria, nome, unidade_origem, unidade_destino, fator_conversao, parametros)
VALUES
  ('bloco', '19x19x39', 'pecas', 'm2', 1.0 / 12.5, '{"pecas_por_m2": 12.5, "peso_peca_kg": 12}'::jsonb),
  ('bloco', '19x19x39', 'paletes', 'pecas', 1.0 / 120.0, '{"pecas_por_palete": 120}'::jsonb),
  ('bloco', '14x19x39', 'pecas', 'm2', 1.0 / 16.7, '{"pecas_por_m2": 16.7, "peso_peca_kg": 9}'::jsonb),
  ('bloco', '9x19x39', 'pecas', 'm2', 1.0 / 25.0, '{"pecas_por_m2": 25, "peso_peca_kg": 6}'::jsonb)
ON CONFLICT (categoria, nome, unidade_origem, unidade_destino) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_normalizacao_materiais_cat
  ON normalizacao_materiais (categoria);
