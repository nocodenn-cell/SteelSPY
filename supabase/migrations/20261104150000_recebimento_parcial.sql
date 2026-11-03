-- Sprint 3 / P3 — Recebimento parcial e ciclo de vida auditável
--
-- Até aqui, "recebimento" era um carimbo: uma linha em `recebimentos` com data,
-- tipo e fotos. Não havia quanto chegou de cada linha do pedido. Sem isso, o
-- sistema não tinha como dizer "entrega parcial" — e a única saída era tratar o
-- pedido inteiro como atendido na primeira nota, ou deixá-lo aberto para sempre.
--
-- Esta migração acrescenta o que faltava, sem reescrever o que já funciona:
--
--   1. `recebimentos.pedido_id` — o portão registra a entrega contra um
--      compromisso, não contra a obra em abstrato;
--   2. `recebimento_itens` — a contagem física por linha de pedido, que é o que
--      faz "parcial" ser um número e não uma opinião;
--   3. `recebimento_eventos` / `pedido_eventos` — cada mudança de estado com
--      quem mudou, quando e por quê. Estado atual sem trilha não é auditável.
--
-- Vocabulário do recebimento muda de (aberto, conferido, encerrado) para
-- (pendente, parcial, completo, divergente, encerrado). Os dois primeiros são
-- renomeados, não recriados: `aberto` virou `pendente` (chegou, ainda não
-- conferido) e `conferido` virou `completo` (cobriu o pedido).
--
-- A ordem aqui não é cosmética. O CHECK antigo aceita (aberto, conferido,
-- encerrado) e recusa (pendente, completo): se o UPDATE rodar com ele ainda
-- de pé, a migração morre no primeiro banco que tenha entrega registrada — em
-- banco vazio ela passa, e é assim que um upgrade quebrado chega à obra. Por
-- isso o CHECK antigo cai antes, o UPDATE roda sem amarra e o CHECK novo só
-- entra quando nenhuma linha pode violá-lo.

-- ---------------------------------------------------------------------------
-- Entrega vinculada ao pedido
-- ---------------------------------------------------------------------------

ALTER TABLE recebimentos ADD COLUMN IF NOT EXISTS pedido_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_recebimentos_pedido') THEN
    ALTER TABLE recebimentos ADD CONSTRAINT fk_recebimentos_pedido
      FOREIGN KEY (tenant_id, pedido_id)
      REFERENCES pedidos_compra (tenant_id, id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recebimentos_pedido
  ON recebimentos (pedido_id, recebido_em DESC) WHERE pedido_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Estados do recebimento
-- ---------------------------------------------------------------------------

ALTER TABLE recebimentos DROP CONSTRAINT IF EXISTS recebimentos_status_check;

UPDATE recebimentos SET status = 'pendente' WHERE status = 'aberto';
UPDATE recebimentos SET status = 'completo' WHERE status = 'conferido';

ALTER TABLE recebimentos ADD CONSTRAINT recebimentos_status_check
  CHECK (status IN ('pendente', 'parcial', 'completo', 'divergente', 'encerrado'));

ALTER TABLE recebimentos ALTER COLUMN status SET DEFAULT 'pendente';

COMMENT ON COLUMN recebimentos.status IS
  'pendente: registrado no portão, sem contagem conferida. parcial: cobriu parte do pedido. '
  'completo: todas as linhas do pedido fechadas. divergente: falta evidência ou veio além do comprado. '
  'encerrado: só por decisão humana autorizada.';

-- ---------------------------------------------------------------------------
-- Quanto chegou de cada linha
-- ---------------------------------------------------------------------------

-- Alvo da FK composta abaixo: uma FK (tenant_id, id) exige UNIQUE nessas colunas.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_recebimentos_tenant_id') THEN
    ALTER TABLE recebimentos ADD CONSTRAINT uq_recebimentos_tenant_id UNIQUE (tenant_id, id);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS recebimento_itens (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id        UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  recebimento_id   UUID NOT NULL,
  pedido_item_id   UUID NOT NULL,
  -- Na unidade da linha do pedido: é a comparação que importa, e evita somar
  -- quilos com metros dentro do mesmo recebimento.
  quantidade       NUMERIC(14, 3) NOT NULL CHECK (quantidade > 0),
  unidade          TEXT NOT NULL,
  observacao       TEXT CHECK (observacao IS NULL OR char_length(observacao) <= 2000),
  criado_por       UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_recebimento_itens_recebimento FOREIGN KEY (tenant_id, recebimento_id)
    REFERENCES recebimentos (tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_recebimento_itens_pedido_item FOREIGN KEY (tenant_id, pedido_item_id)
    REFERENCES pedido_itens (tenant_id, id) ON DELETE CASCADE,
  -- Duas contagens da mesma linha no mesmo portão somariam o mesmo ferro duas
  -- vezes; é o erro que a conciliação tinha por bitola e não pode ter aqui.
  CONSTRAINT uq_recebimento_itens_linha UNIQUE (recebimento_id, pedido_item_id)
);

CREATE INDEX IF NOT EXISTS idx_recebimento_itens_pedido_item
  ON recebimento_itens (pedido_item_id);
CREATE INDEX IF NOT EXISTS idx_recebimento_itens_tenant
  ON recebimento_itens (tenant_id);

-- ---------------------------------------------------------------------------
-- Trilha de transições (quem, quando, por quê)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recebimento_eventos (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id        UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  recebimento_id   UUID NOT NULL,
  status_de        TEXT,
  status_para      TEXT NOT NULL,
  motivo           TEXT CHECK (motivo IS NULL OR char_length(motivo) <= 2000),
  -- Autor da transição. NULL é só o que o sistema calculou sem decisão humana;
  -- encerrar um recebimento sem autor é impossível por constraint de serviço.
  autor_id         UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_recebimento_eventos_recebimento FOREIGN KEY (tenant_id, recebimento_id)
    REFERENCES recebimentos (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recebimento_eventos_recebimento
  ON recebimento_eventos (recebimento_id, criado_em);

CREATE TABLE IF NOT EXISTS pedido_eventos (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id        UUID NOT NULL REFERENCES construtoras (id) ON DELETE CASCADE,
  pedido_id        UUID NOT NULL,
  status_de        TEXT,
  status_para      TEXT NOT NULL,
  motivo           TEXT CHECK (motivo IS NULL OR char_length(motivo) <= 2000),
  autor_id         UUID REFERENCES usuarios (id) ON DELETE SET NULL,
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_pedido_eventos_pedido FOREIGN KEY (tenant_id, pedido_id)
    REFERENCES pedidos_compra (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pedido_eventos_pedido
  ON pedido_eventos (pedido_id, criado_em);

COMMENT ON TABLE recebimento_eventos IS
  'Append-only: cada mudança de estado do recebimento, com responsável e motivo. '
  'Nunca UPDATE — a pergunta do auditor é "por que estava fechado em março".';
COMMENT ON TABLE pedido_eventos IS
  'Append-only: transições do compromisso comercial. Estado atual é derivável da '
  'última linha; a trilha inteira é o que fica.';

-- ---------------------------------------------------------------------------
-- RLS desde o nascimento
-- ---------------------------------------------------------------------------

ALTER TABLE recebimento_itens    ENABLE ROW LEVEL SECURITY;
ALTER TABLE recebimento_itens    FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_recebimento_itens_tenant ON recebimento_itens;
CREATE POLICY p_recebimento_itens_tenant ON recebimento_itens
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());

ALTER TABLE recebimento_eventos  ENABLE ROW LEVEL SECURITY;
ALTER TABLE recebimento_eventos  FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_recebimento_eventos_tenant ON recebimento_eventos;
CREATE POLICY p_recebimento_eventos_tenant ON recebimento_eventos
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());

ALTER TABLE pedido_eventos       ENABLE ROW LEVEL SECURITY;
ALTER TABLE pedido_eventos       FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_pedido_eventos_tenant ON pedido_eventos;
CREATE POLICY p_pedido_eventos_tenant ON pedido_eventos
  USING (tenant_id = tenant_atual()) WITH CHECK (tenant_id = tenant_atual());
