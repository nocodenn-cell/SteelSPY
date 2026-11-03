-- Fase 0 / M23 — Senha da role de aplicação vinda de configuração
--
-- A senha NÃO está no repositório. Ela vem da configuração do banco:
--
--   ALTER DATABASE <banco> SET stellspy.app_password = '<senha>';
--   -- ou, para uma sessão de migração:
--   SET stellspy.app_password = '<senha>';
--
-- O executor de migrações (backend/scripts/apply_migrations.py) define essa
-- configuração a partir da variável de ambiente STELLSPY_APP_PASSWORD antes de
-- aplicar os arquivos.
--
-- Se a configuração não existir, esta migração FALHA de propósito: subir um
-- banco com a role de aplicação sem senha seria pior que não subir.

DO $$
DECLARE
  v_senha TEXT := current_setting('stellspy.app_password', true);
BEGIN
  IF v_senha IS NULL OR btrim(v_senha) = '' THEN
    RAISE EXCEPTION
      'stellspy.app_password não configurado. Defina STELLSPY_APP_PASSWORD no ambiente do executor de migrações (ou SET stellspy.app_password antes de aplicar).';
  END IF;

  IF length(v_senha) < 12 THEN
    RAISE EXCEPTION
      'stellspy.app_password curto demais (% caracteres). Use ao menos 12.', length(v_senha);
  END IF;

  EXECUTE format('ALTER ROLE stellspy_app PASSWORD %L', v_senha);
  RAISE NOTICE 'senha da role stellspy_app atualizada a partir da configuração';
END $$;
