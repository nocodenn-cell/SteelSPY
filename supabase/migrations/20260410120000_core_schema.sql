-- Auditoria construção: obras, especificações, NF-e, sinônimos, fila
-- Melhorias em relação ao rascunho: sem UNIQUE em CNPJ (várias obras/mesmo CNPJ);
-- status_conferencia inclui PENDENTE; FKs com ON DELETE; checks de domínio.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Obras e configurações (margem 0.02 = 2%)
CREATE TABLE obras (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome TEXT NOT NULL,
  cnpj_destinatario TEXT NOT NULL CHECK (cnpj_destinatario ~ '^[0-9]{14}$'),
  aceita_similar BOOLEAN NOT NULL DEFAULT FALSE,
  margem_tolerancia_float DOUBLE PRECISION NOT NULL DEFAULT 0.02
    CHECK (margem_tolerancia_float > 0 AND margem_tolerancia_float <= 0.5),
  modo_aprendizado BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_obras_cnpj ON obras (cnpj_destinatario);

-- Especificação técnica (base da verdade)
CREATE TABLE especificacoes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  obra_id UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  material_tipo TEXT,
  bitola_mm DOUBLE PRECISION,
  marca_exigida TEXT,
  qtd_planejada_metros DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_especificacoes_obra ON especificacoes (obra_id);

-- Logs de NF-e e conferência
CREATE TABLE nfe_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  chave_acesso VARCHAR(44) NOT NULL CHECK (chave_acesso ~ '^[0-9]{44}$'),
  obra_id UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  status_conferencia TEXT NOT NULL DEFAULT 'PENDENTE'
    CHECK (status_conferencia IN ('PENDENTE', 'VERDE', 'AMARELO', 'VERMELHO')),
  xml_data JSONB,
  override_info JSONB,
  processado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (obra_id, chave_acesso)
);

CREATE INDEX idx_nfe_logs_obra ON nfe_logs (obra_id);
CREATE INDEX idx_nfe_logs_processado ON nfe_logs (processado_em DESC);

-- De/Para: termo na NF → material padrão (texto)
CREATE TABLE sinonimos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  termo_nfe TEXT NOT NULL,
  material_padrao TEXT NOT NULL,
  confiabilidade DOUBLE PRECISION NOT NULL DEFAULT 1.0
    CHECK (confiabilidade >= 0 AND confiabilidade <= 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (termo_nfe)
);

CREATE INDEX idx_sinonimos_termo ON sinonimos (lower(termo_nfe));

-- Fila: XML indisponível — retentativas após 5 / 15 / 30 min (processada pelo worker)
CREATE TABLE fila_nfe (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  obra_id UUID NOT NULL REFERENCES obras (id) ON DELETE CASCADE,
  chave_acesso VARCHAR(44) NOT NULL CHECK (chave_acesso ~ '^[0-9]{44}$'),
  tentativas INT NOT NULL DEFAULT 0 CHECK (tentativas >= 0 AND tentativas <= 3),
  proxima_tentativa TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'pendente'
    CHECK (status IN ('pendente', 'processando', 'processado', 'falha')),
  ultimo_erro TEXT,
  notificado_aguardando BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (obra_id, chave_acesso)
);

CREATE INDEX idx_fila_nfe_proxima ON fila_nfe (status, proxima_tentativa)
  WHERE status = 'pendente';

COMMENT ON COLUMN obras.margem_tolerancia_float IS 'Fração ex.: 0.02 = ±2% para faixa VERDE em quantidade';
COMMENT ON TABLE nfe_logs IS 'override_info: auditoria de quem autorizou exceções';
COMMENT ON TABLE fila_nfe IS 'Worker deve chamar processar_tick_fila; BackgroundTasks só persiste/enfileira';
