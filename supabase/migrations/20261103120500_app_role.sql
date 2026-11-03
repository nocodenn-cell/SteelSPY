-- Fase 0 / M15 — Role de aplicação, sem privilégios de administrador
--
-- Por que existe: a aplicação NÃO pode conectar como `postgres` nem como o
-- dono das tabelas. Um superusuário ignora RLS por definição, e uma role dona
-- das tabelas ignora RLS quando a tabela não está com FORCE ROW LEVEL SECURITY.
-- Sem esta role separada, todo o isolamento por RLS seria decorativo.
--
-- A SENHA NÃO FICA AQUI. A role é criada sem senha e recebe uma em seguida,
-- pela migração 20261103150200_app_role_senha.sql, que lê a credencial da
-- configuração do banco (`stellspy.app_password`). Assim o repositório nunca
-- carrega credencial — nem de desenvolvimento.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stellspy_app') THEN
    CREATE ROLE stellspy_app
      LOGIN
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'role stellspy_app criada (sem senha)';
  ELSE
    ALTER ROLE stellspy_app NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
    RAISE NOTICE 'role stellspy_app já existia — garantido NOBYPASSRLS';
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO stellspy_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO stellspy_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stellspy_app;

-- Tabelas criadas depois desta migração também ficam acessíveis.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO stellspy_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO stellspy_app;
