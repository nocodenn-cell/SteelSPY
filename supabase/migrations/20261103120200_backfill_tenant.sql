-- Fase 0 / M12 — backfill do tenant nas obras existentes
--
-- Cria (se necessário) a construtora padrão e vincula todas as obras órfãs.
-- Idempotente: se não houver obra com tenant_id NULL, não faz nada.
--
-- A construtora padrão nasce SEM CNPJ de propósito: o CNPJ da construtora
-- operadora não está no repositório e inventá-lo seria criar dado falso.
-- Preencher antes de cadastrar a segunda construtora (gate AC0.10).

DO $$
DECLARE
  v_tenant UUID;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM obras WHERE tenant_id IS NULL) THEN
    RAISE NOTICE 'backfill: nenhuma obra sem tenant, nada a fazer';
    RETURN;
  END IF;

  SELECT id INTO v_tenant FROM construtoras ORDER BY criado_em, id LIMIT 1;

  IF v_tenant IS NULL THEN
    INSERT INTO construtoras (nome, plano)
    VALUES ('Migração — preencher', 'piloto')
    RETURNING id INTO v_tenant;
    RAISE NOTICE 'backfill: construtora padrão criada (%)', v_tenant;
  END IF;

  UPDATE obras SET tenant_id = v_tenant WHERE tenant_id IS NULL;

  RAISE NOTICE 'backfill: % obra(s) vinculada(s) ao tenant %',
    (SELECT count(*) FROM obras WHERE tenant_id = v_tenant), v_tenant;
END $$;
