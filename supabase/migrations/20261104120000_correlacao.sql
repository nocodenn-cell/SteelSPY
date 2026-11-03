-- Sprint 3 / P0 — Correlação explícita entre linha de pedido e item de NF-e
--
-- O problema que esta migração resolve: a conciliação casava pedido × NF-e por
-- bitola. Duas linhas de pedido com a mesma bitola consumiam o mesmo item
-- faturado, e a divergência calculada estava errada sem ninguém saber.
--
-- Para correlação determinística faltavam duas coisas que só o banco pode dar:
--
--   1. o código de produto do fornecedor na linha do pedido — a única chave que
--      sobrevive à descrição livre da NF-e;
--   2. um lugar para gravar a decisão humana quando a máquina não decide,
--      senão a revisão não persiste e a próxima conciliação recria a ambiguidade.
--
-- `correlacoes_humanas` é append-mostly: `removido_em` encerra, nunca apaga.
-- Quem alterou uma correlação precisa aparecer na trilha, com nome e data.

-- ---------------------------------------------------------------------------
-- Identificação da linha do pedido
-- ---------------------------------------------------------------------------

ALTER TABLE pedido_itens ADD COLUMN IF NOT EXISTS codigo_produto_fornecedor TEXT;
ALTER TABLE pedido_itens ADD COLUMN IF NOT EXISTS referencia_erp TEXT;

COMMENT ON COLUMN pedido_itens.codigo_produto_fornecedor IS
  'Código do produto no catálogo do fornecedor (o mesmo que aparece em cProd na NF-e). '
  'É a evidência dura da correlação; na ausência dela, o casamento é heurístico.';
COMMENT ON COLUMN pedido_itens.referencia_erp IS
  'Referência da linha no ERP de origem, para rastreio quando o pedido é importado.';

CREATE INDEX IF NOT EXISTS idx_pedido_itens_codigo
  ON pedido_itens (tenant_id, codigo_produto_fornecedor)
  WHERE codigo_produto_fornecedor IS NOT NULL;

-- Alvos de FK composta: uma FK (tenant_id, id) exige UNIQUE exatamente nessas colunas.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_pedido_itens_tenant_id') THEN
    ALTER TABLE pedido_itens ADD CONSTRAINT uq_pedido_itens_tenant_id UNIQUE (tenant_id, id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_nfe_logs_tenant_id') THEN
    ALTER TABLE nfe_logs ADD CONSTRAINT uq_nfe_logs_tenant_id UNIQUE (tenant_id, id);
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Correlação confirmada por responsável
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS correlacoes_humanas (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id        UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  pedido_item_id   UUID NOT NULL,
  nfe_log_id       UUID NOT NULL,
  nfe_item_numero  INT  NOT NULL CHECK (nfe_item_numero >= 1),
  -- Quantidade correlacionada, na unidade do item da NF-e. NULL = o item inteiro.
  -- Sem esta coluna, duas NF-e de entrega parcial não podem ser divididas entre
  -- duas linhas de pedido da mesma bitola nem com confirmação humana.
  quantidade       NUMERIC(14, 3) CHECK (quantidade IS NULL OR quantidade > 0),
  observacao       TEXT CHECK (observacao IS NULL OR char_length(observacao) <= 2000),
  criado_por       UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  removido_em      TIMESTAMPTZ,
  removido_por     UUID REFERENCES usuarios (id) ON DELETE SET NULL,

  CONSTRAINT fk_correlacoes_pedido_item FOREIGN KEY (tenant_id, pedido_item_id)
    REFERENCES pedido_itens (tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_correlacoes_nfe FOREIGN KEY (tenant_id, nfe_log_id)
    REFERENCES nfe_logs (tenant_id, id) ON DELETE CASCADE
);

-- A mesma correlação não pode ser confirmada duas vezes em aberto.
CREATE UNIQUE INDEX IF NOT EXISTS uq_correlacoes_humanas_ativa
  ON correlacoes_humanas (pedido_item_id, nfe_log_id, nfe_item_numero)
  WHERE removido_em IS NULL;

CREATE INDEX IF NOT EXISTS idx_correlacoes_humanas_pedido_item
  ON correlacoes_humanas (pedido_item_id) WHERE removido_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_correlacoes_humanas_tenant
  ON correlacoes_humanas (tenant_id);

COMMENT ON TABLE correlacoes_humanas IS
  'Correlação linha-de-pedido x item-de-NF-e confirmada por pessoa. '
  'Vence qualquer heurística na conciliação; é a saída para a ambiguidade material.';
COMMENT ON COLUMN correlacoes_humanas.removido_em IS
  'Encerramento, não exclusão: a trilha de quem correlacionou e deixou de correlacionar fica no banco.';

-- ---------------------------------------------------------------------------
-- RLS desde o nascimento
-- ---------------------------------------------------------------------------

ALTER TABLE correlacoes_humanas ENABLE ROW LEVEL SECURITY;
ALTER TABLE correlacoes_humanas FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_correlacoes_humanas_tenant ON correlacoes_humanas;
CREATE POLICY p_correlacoes_humanas_tenant ON correlacoes_humanas
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());
