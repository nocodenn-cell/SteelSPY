-- P-08 (A4): a idempotência de nfe_logs passa a incluir `tipo`.
--
-- Antes: UNIQUE (obra_id, chave_acesso). Uma devolução cuja NF tem a mesma chave
-- da entrada não ganhava linha própria: o POST devolvia a conferência da entrada,
-- e o upsert, se chegasse ao banco, sobrescrevia a entrada com tipo=devolucao.
--
-- Depois: UNIQUE (obra_id, chave_acesso, tipo). A restrição nova é implicada pela
-- antiga, então nenhuma linha existente pode violá-la. Não é aplicada em produção
-- por esta entrega: a aplicação segue o fluxo de migrações já aprovado.

ALTER TABLE nfe_logs DROP CONSTRAINT IF EXISTS nfe_logs_obra_id_chave_acesso_key;

ALTER TABLE nfe_logs
  ADD CONSTRAINT nfe_logs_obra_chave_tipo_key UNIQUE (obra_id, chave_acesso, tipo);

COMMENT ON CONSTRAINT nfe_logs_obra_chave_tipo_key ON nfe_logs IS
  'Idempotência de conferência: uma linha por (obra, NF, tipo). Devolução com a mesma chave é conferência própria.';
