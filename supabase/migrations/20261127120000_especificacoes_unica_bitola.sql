-- B12 (revalidação 2026-11-21): uma obra tem no máximo uma especificação por bitola.
--
-- Sem essa regra, duas linhas de especificacoes da mesma obra e bitola disputam o
-- mesmo item da NF e a conferência escolhe uma delas sem aviso. Bitola nula fica
-- fora da regra (a categoria cimento/bloco pode não ter bitola).
--
-- Dados existentes NÃO são alterados. Se já houver duplicatas, a migração aborta
-- com a lista de obras e bitolas afetadas; o ajuste é decidido pelo operador
-- (renomear, remover uma das linhas ou corrigir a bitola) e a migração roda de novo.

DO $$
DECLARE
  v_duplicadas INT;
  v_detalhe TEXT;
BEGIN
  SELECT COUNT(*), string_agg(format('obra=%s bitola=%s n=%s', obra_id, bitola_mm, n), '; ')
    INTO v_duplicadas, v_detalhe
  FROM (
    SELECT obra_id, bitola_mm, COUNT(*) AS n
    FROM especificacoes
    WHERE bitola_mm IS NOT NULL
    GROUP BY obra_id, bitola_mm
    HAVING COUNT(*) > 1
  ) d;

  IF v_duplicadas > 0 THEN
    RAISE EXCEPTION
      'especificacoes: % combinação(ões) obra+bitola duplicada(s); resolver antes de aplicar a unicidade. %',
      v_duplicadas, v_detalhe;
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS especificacoes_obra_bitola_key
  ON especificacoes (obra_id, bitola_mm)
  WHERE bitola_mm IS NOT NULL;

COMMENT ON INDEX especificacoes_obra_bitola_key IS
  'B12: uma especificação por bitola dentro da obra (bitola nula fora da regra).';
