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

-- No Supabase gerenciado a migração roda como `postgres`, que tem CREATEROLE mas
-- NÃO é superuser. Alterar o atributo SUPERUSER — mesmo para NOSUPERUSER — exige
-- superuser. Por isso o ramo de role existente apenas VERIFICA os atributos que
-- afetam o isolamento e falha se estiverem perigosos, em vez de tentar alterá-los.
DO $$
DECLARE
  v_super  BOOLEAN;
  v_bypass BOOLEAN;
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
    SELECT rolsuper, rolbypassrls INTO v_super, v_bypass
    FROM pg_roles WHERE rolname = 'stellspy_app';

    IF v_super OR v_bypass THEN
      RAISE EXCEPTION
        'role stellspy_app tem atributos incompatíveis (superuser=%, bypassrls=%); corrija com um superusuário antes de continuar',
        v_super, v_bypass;
    END IF;

    RAISE NOTICE 'role stellspy_app já existia — superuser=false, bypassrls=false';
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
