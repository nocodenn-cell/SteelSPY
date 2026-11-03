"""Isolamento multiempresa provado no PostgreSQL, não no Python.

Cada teste aqui responde a uma pergunta que uma revisão de código não responde:

- a role da aplicação realmente não tem BYPASSRLS?
- sem contexto de tenant, alguma linha vaza?
- a construtora A consegue enxergar a obra da B por SQL direto?
- se alguém remover a policy, o vazamento reaparece? (teste de mutação)
- o bootstrap de login funciona sem abrir o isolamento?
- as migrações rodam duas vezes sem efeito colateral?
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from app.tenant import CHAVE_TENANT, resolver_tenant_de_nfe_log, vincular_sessao


# ---------------------------------------------------------------------------
# Estrutura de proteção
# ---------------------------------------------------------------------------


def test_role_da_aplicacao_nao_tem_bypassrls(sql_owner: Any) -> None:
    """Se esta role bypassasse RLS, todo o resto desta suíte seria teatro."""
    with sql_owner.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'stellspy_app'"
            )
        ).one()
    assert linha.rolbypassrls is False
    assert linha.rolsuper is False


def test_role_da_aplicacao_nao_e_dona_das_tabelas(sql_owner: Any) -> None:
    """Dono de tabela escapa do RLS a menos que FORCE esteja ligado — não confiamos nisso."""
    with sql_owner.connect() as conn:
        dono = conn.execute(
            text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = 'obras'")
        ).scalar_one()
    assert dono != "stellspy_app"


@pytest.mark.parametrize("tabela", ["construtoras", "obras", "usuarios", "obra_usuarios"])
def test_rls_ligado_e_forcado(sql_owner: Any, tabela: str) -> None:
    with sql_owner.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"
            ),
            {"t": tabela},
        ).one()
    assert linha.relrowsecurity is True, f"{tabela} sem RLS"
    assert linha.relforcerowsecurity is True, f"{tabela} sem FORCE ROW LEVEL SECURITY"


@pytest.mark.parametrize(
    "tabela",
    ["construtoras", "obras", "usuarios", "obra_usuarios"],
)
def test_toda_tabela_com_tenant_tem_policy(sql_owner: Any, tabela: str) -> None:
    with sql_owner.connect() as conn:
        qtd = conn.execute(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": tabela}
        ).scalar_one()
    assert qtd >= 1, f"{tabela} tem RLS mas nenhuma policy — negaria tudo"


# ---------------------------------------------------------------------------
# Isolamento entre construtoras
# ---------------------------------------------------------------------------


def test_sem_contexto_nenhuma_obra_e_visivel(abrir_como: Any) -> None:
    with abrir_como(None) as conn:
        total = conn.execute(text("SELECT count(*) FROM obras")).scalar_one()
    assert total == 0


def test_tenant_a_ve_somente_as_proprias_obras(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        ids = {r.id for r in conn.execute(text("SELECT id FROM obras"))}
    assert cenario["obra_a"] in ids
    assert cenario["obra_b"] not in ids


def test_tenant_b_nao_alcanca_obra_do_tenant_a(
    abrir_como: Any, cenario: dict[str, Any]
) -> None:
    """Consulta direta pelo id exato, como faria alguém tentando forçar a barra."""
    with abrir_como(cenario["tenant_b"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM obras WHERE id = :id"), {"id": cenario["obra_a"]}
        ).scalar_one()
    assert achou == 0


def test_tenant_a_nao_ve_usuario_do_tenant_b(
    abrir_como: Any, cenario: dict[str, Any]
) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM usuarios WHERE id = :id"), {"id": cenario["usuario_b"]}
        ).scalar_one()
    assert achou == 0


def test_tenant_a_nao_ve_vinculo_do_tenant_b(
    abrir_como: Any, cenario: dict[str, Any]
) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM obra_usuarios WHERE obra_id = :o"), {"o": cenario["obra_b"]}
        ).scalar_one()
    assert achou == 0


def test_construtora_so_ve_a_propria_linha(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        ids = {r.id for r in conn.execute(text("SELECT id FROM construtoras"))}
    assert ids == {cenario["tenant_a"]}


def test_nao_consegue_inserir_obra_em_outro_tenant(
    abrir_como: Any, cenario: dict[str, Any]
) -> None:
    """WITH CHECK impede escrita cruzada, não só leitura."""
    with pytest.raises(Exception) as exc:
        with abrir_como(cenario["tenant_a"]) as conn:
            conn.execute(
                text(
                    "INSERT INTO obras (tenant_id, nome, cnpj_destinatario) "
                    "VALUES (:t, 'Invasora', '33333333000133')"
                ),
                {"t": cenario["tenant_b"]},
            )
    assert "row-level security" in str(exc.value).lower() or "policy" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Listener: o contexto chega à transação sem SQL manual
# ---------------------------------------------------------------------------


def test_listener_aplica_tenant_na_transacao(
    sessao_app_factory: Any, cenario: dict[str, Any]
) -> None:
    session = sessao_app_factory()
    try:
        vincular_sessao(session, cenario["tenant_a"])
        assert session.info[CHAVE_TENANT] == str(cenario["tenant_a"])

        ids = {r.id for r in session.execute(text("SELECT id FROM obras"))}
        assert cenario["obra_a"] in ids
        assert cenario["obra_b"] not in ids
    finally:
        session.close()


def test_listener_nao_vaza_tenant_entre_sessoes(
    sessao_app_factory: Any, cenario: dict[str, Any]
) -> None:
    """Uma sessão nova, sem vínculo, não herda o tenant da anterior."""
    primeira = sessao_app_factory()
    try:
        vincular_sessao(primeira, cenario["tenant_a"])
        primeira.execute(text("SELECT 1")).scalar_one()
    finally:
        primeira.close()

    segunda = sessao_app_factory()
    try:
        total = segunda.execute(text("SELECT count(*) FROM obras")).scalar_one()
        assert total == 0, "contexto de tenant vazou entre sessões"
    finally:
        segunda.close()


# ---------------------------------------------------------------------------
# Bootstrap de login (SECURITY DEFINER)
# ---------------------------------------------------------------------------


def test_bootstrap_resolve_tenant_da_obra(abrir_como: Any, cenario: dict[str, Any]) -> None:
    """O login precisa descobrir o tenant antes de existir contexto."""
    with abrir_como(None) as conn:
        linha = conn.execute(
            text("SELECT tenant_id FROM auth_lookup_obra(:id)"), {"id": cenario["obra_a"]}
        ).one()
    assert linha.tenant_id == cenario["tenant_a"]


def test_bootstrap_de_obra_inexistente_devolve_vazio(abrir_como: Any) -> None:
    with abrir_como(None) as conn:
        linhas = conn.execute(
            text("SELECT * FROM auth_lookup_obra(:id)"),
            {"id": "00000000-0000-0000-0000-000000000000"},
        ).fetchall()
    assert linhas == []


def test_bootstrap_resolve_tenant_do_nfe_log(
    sessao_app_factory: Any, cenario: dict[str, Any]
) -> None:
    """`resolver_tenant_de_nfe_log` abre o contexto e devolve o tenant."""
    session = sessao_app_factory()
    try:
        tenant = resolver_tenant_de_nfe_log(session, cenario["nfe_a"])
        assert tenant == cenario["tenant_a"]
        # e a partir daqui a sessão já enxerga a obra
        nome = session.execute(
            text("SELECT nome FROM obras WHERE id = :id"), {"id": cenario["obra_a"]}
        ).scalar_one()
        assert nome == "Obra Alfa 1"
    finally:
        session.close()


def test_bootstrap_nao_expoe_obra_de_outro_tenant_por_engano(
    sessao_app_factory: Any, cenario: dict[str, Any]
) -> None:
    """Depois de abrir o contexto de B, a obra de A continua invisível."""
    session = sessao_app_factory()
    try:
        assert resolver_tenant_de_nfe_log(session, cenario["nfe_b"]) == cenario["tenant_b"]
        achou = session.execute(
            text("SELECT count(*) FROM obras WHERE id = :id"), {"id": cenario["obra_a"]}
        ).scalar_one()
        assert achou == 0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Teste de mutação: a policy é o que segura o isolamento
# ---------------------------------------------------------------------------


def test_mutacao_remover_policy_faz_o_isolamento_falhar(
    sql_owner: Any, abrir_como: Any, cenario: dict[str, Any]
) -> None:
    """
    Prova que o verde dos testes acima depende da policy.

    Trocar a policy restritiva por uma permissiva (`USING (true)`) precisa
    fazer a construtora A enxergar a obra da B. Se isso não acontecer, os
    testes de isolamento estariam passando por outro motivo e não valeriam.

    A policy original é restaurada ao final, mesmo em caso de falha.
    """
    with abrir_como(cenario["tenant_a"]) as conn:
        antes = conn.execute(
            text("SELECT count(*) FROM obras WHERE id = :id"), {"id": cenario["obra_b"]}
        ).scalar_one()
    assert antes == 0, "pré-condição: B não deveria estar visível para A"

    try:
        with sql_owner.begin() as conn:
            conn.execute(text("DROP POLICY p_obras_tenant ON obras"))
            conn.execute(
                text("CREATE POLICY p_obras_mutacao ON obras USING (true) WITH CHECK (true)")
            )

        with abrir_como(cenario["tenant_a"]) as conn:
            depois = conn.execute(
                text("SELECT count(*) FROM obras WHERE id = :id"), {"id": cenario["obra_b"]}
            ).scalar_one()
        assert depois == 1, "com a policy removida o vazamento DEVERIA acontecer"
    finally:
        with sql_owner.begin() as conn:
            conn.execute(text("DROP POLICY IF EXISTS p_obras_mutacao ON obras"))
            conn.execute(
                text(
                    "CREATE POLICY p_obras_tenant ON obras "
                    "USING (tenant_id = tenant_atual()) "
                    "WITH CHECK (tenant_id = tenant_atual())"
                )
            )

    with abrir_como(cenario["tenant_a"]) as conn:
        restaurado = conn.execute(
            text("SELECT count(*) FROM obras WHERE id = :id"), {"id": cenario["obra_b"]}
        ).scalar_one()
    assert restaurado == 0, "a policy restaurada precisa voltar a bloquear"


# ---------------------------------------------------------------------------
# Migrações
# ---------------------------------------------------------------------------


def test_migracoes_sao_idempotentes(
    sql_owner: Any,
    runner_migracoes: Any,
    caminho_migracoes: Any,
    url_owner: str,
) -> None:
    """Rodar a aplicação de migrações duas vezes não deve aplicar nada."""
    total_arquivos = len(list(caminho_migracoes.glob("*.sql")))

    assert runner_migracoes.main(["--url", url_owner, "--dir", str(caminho_migracoes)]) == 0

    with sql_owner.connect() as conn:
        aplicadas = conn.execute(text("SELECT count(*) FROM schema_migrations")).scalar_one()

    assert aplicadas == total_arquivos, (
        f"esperava {total_arquivos} migrações registradas, encontrei {aplicadas}"
    )
