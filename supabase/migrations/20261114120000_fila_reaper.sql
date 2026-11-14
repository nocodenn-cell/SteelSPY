-- P0 (fila travada em 'processando'): reaper para linhas reivindicadas por um
-- worker que morreu antes de concluir.
--
-- `fila_reivindicar_lote` marca a linha como 'processando' e commita. Se o worker
-- morre depois disso, nada a libera. A fila tem RLS forçado, então o reaper roda
-- como SECURITY DEFINER (mesmo padrão do claim), que enxerga todos os tenants.
--
-- Regras:
--   - claim com mais de p_minutos sem atualização volta a 'pendente' agora;
--   - cada reaper conta uma tentativa, para que uma NF que derruba o worker
--     não entre em loop infinito: ao atingir 3 tentativas, vira 'falha'.
--
-- REVERSÍVEL: DROP FUNCTION fila_reaper_travadas(INT);
-- Idempotente: CREATE OR REPLACE.

CREATE OR REPLACE FUNCTION fila_reaper_travadas(p_minutos INT DEFAULT 10)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  liberadas INT;
BEGIN
  WITH travadas AS (
    UPDATE fila_nfe f
       SET tentativas = f.tentativas + 1,
           status = CASE WHEN f.tentativas + 1 >= 3 THEN 'falha' ELSE 'pendente' END,
           proxima_tentativa = NOW(),
           ultimo_erro = 'reaper: worker não concluiu o claim dentro do prazo',
           updated_at = NOW()
     WHERE f.status = 'processando'
       AND f.updated_at < NOW() - make_interval(mins => p_minutos)
    RETURNING 1
  )
  SELECT COUNT(*) INTO liberadas FROM travadas;
  RETURN liberadas;
END $$;

REVOKE ALL ON FUNCTION fila_reaper_travadas(INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fila_reaper_travadas(INT) TO stellspy_app;

COMMENT ON FUNCTION fila_reaper_travadas(INT) IS
  'Libera linhas de fila presas em processando por mais de p_minutos; conta tentativa e marca falha no 3º.';
