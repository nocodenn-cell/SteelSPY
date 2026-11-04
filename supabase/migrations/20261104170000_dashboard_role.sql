-- Sprint 6 / M31 — Role de leitura do dashboard, presa a um tenant por transação
--
-- Por que existe: o painel lia com credencial de back-office (superuser ou
-- BYPASSRLS) para listar obras de todas as construtoras. Num piloto com uma
-- construtora isso é privilégio a mais — a credencial do painel poderia ler
-- qualquer tenant, inclusive os que não são do piloto.
--
-- Esta role:
--   * NÃO é superuser, NÃO tem BYPASSRLS, NÃO herda de ninguém;
--   * recebe SELECT apenas nas tabelas que o painel lê (nada de usuarios,
--     sessoes, evidencias ou fila_nfe);
--   * continua sob as mesmas policies: sem `app.tenant_id` na transação,
--     `tenant_atual()` é NULL e nenhuma linha passa;
--   * só ganha LOGIN quando a senha é configurada fora do repositório
--     (`stellspy.dashboard_password` / STELLSPY_DASHBOARD_PASSWORD).
--
-- Sem senha configurada a role nasce NOLOGIN: esquecer a variável fecha o
-- acesso em vez de abrir.

DO $$
DECLARE
  v_senha TEXT := current_setting('stellspy.dashboard_password', true);
  v_super BOOLEAN;
  v_bypass BOOLEAN;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stellspy_dashboard') THEN
    CREATE ROLE stellspy_dashboard NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
    RAISE NOTICE 'role stellspy_dashboard criada (NOLOGIN até ter senha)';
  ELSE
    SELECT rolsuper, rolbypassrls INTO v_super, v_bypass
    FROM pg_roles WHERE rolname = 'stellspy_dashboard';

    IF v_super OR v_bypass THEN
      RAISE EXCEPTION
        'role stellspy_dashboard tem atributos incompatíveis (superuser=%, bypassrls=%); corrija com um superusuário antes de continuar',
        v_super, v_bypass;
    END IF;
  END IF;

  IF v_senha IS NOT NULL AND btrim(v_senha) <> '' THEN
    IF length(v_senha) < 12 THEN
      RAISE EXCEPTION
        'stellspy.dashboard_password curto demais (% caracteres). Use ao menos 12.', length(v_senha);
    END IF;
    EXECUTE format('ALTER ROLE stellspy_dashboard PASSWORD %L', v_senha);
    ALTER ROLE stellspy_dashboard LOGIN;
    RAISE NOTICE 'role stellspy_dashboard habilitada para login';
  ELSE
    RAISE NOTICE 'stellspy.dashboard_password ausente: role stellspy_dashboard permanece NOLOGIN';
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO stellspy_dashboard;

-- Somente as tabelas que o painel realmente consulta. `construtoras` existe
-- aqui só para o painel mostrar o nome da construtora do piloto; a policy já
-- limita a linha ao próprio tenant.
GRANT SELECT ON construtoras, obras, nfe_logs, nfe_itens, especificacoes
  TO stellspy_dashboard;

-- Nenhum INSERT/UPDATE/DELETE e nenhum GRANT em sequências: o painel é leitura.
-- Também não há ALTER DEFAULT PRIVILEGES — tabela nova nasce invisível para a
-- role, que é o lado fechado.

COMMENT ON ROLE stellspy_dashboard IS
  'Leitura do dashboard, sob RLS, restrita ao tenant de app.tenant_id. Sem escrita.';
