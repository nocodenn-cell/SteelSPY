-- Fase 0 / M15 — Role de aplicação, sem privilégios de administrador
--
-- Por que existe: a aplicação NÃO pode conectar como `postgres` nem como o
-- dono das tabelas. Um superusuário ignora RLS por definição, e uma role dona
-- das tabelas ignora RLS quando a tabela não está com FORCE ROW LEVEL SECURITY.
-- Sem esta role separada, todo o isolamento por RLS seria decorativo.
--
-- ATENÇÃO — SENHA DE DESENVOLVIMENTO
-- A senha abaixo serve apenas para o container local de desenvolvimento/testes.
-- Em qualquer ambiente real, ela deve ser trocada e vir de variável de
-- ambiente/secret manager, nunca do repositório.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stellspy_app') THEN
    CREATE ROLE stellspy_app
      LOGIN
      PASSWORD 'stellspy_app_dev_only'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOBYPASSRLS;
    RAISE NOTICE 'role stellspy_app criada';
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
