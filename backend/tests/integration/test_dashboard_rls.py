"""O painel lê com a role de menor privilégio, preso a uma construtora.

Auditoria da Sprint 6: a versão anterior exigia uma credencial de back-office
(superuser ou BYPASSRLS) para listar obras de todos os tenants. Num piloto com
uma construtora isso é privilégio a mais. A role `stellspy_dashboard` agora:
  * só tem SELECT (e só nas cinco tabelas do painel);
  * continua sob RLS, com `app.tenant_id` fixado em DASHBOARD_TENANT_ID;
  * sem contexto de tenant, não vê nenhuma linha.

Os testes usam conexões reais com essa role. Se a migração sumir ou alguém
conceder escrita/bypass, eles falham — é o objetivo.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

RAIZ = pathlib.Path(__file__).resolve().parents[3]


def _carregar(nome: str) -> Any:
    caminho = RAIZ / "dashboard" / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(f"_dashboard_{nome}", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


diagnostico = _carregar("diagnostico")
leitura = _carregar("leitura")


@contextmanager
def _como(engine: Any, tenant_id: str | None) -> Iterator[Any]:
    with diagnostico.conexao_do_tenant(engine, tenant_id) as conn:
        yield conn


def _contar(conn: Any, sql: str, **params: Any) -> int:
    return int(conn.execute(text(sql), params).scalar_one())


def test_role_do_painel_e_minima(sql_dashboard: Any, cenario: dict[str, Any]) -> None:
    with sql_dashboard.connect() as conn:
        attrs = conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).mappings().one()
        assert attrs["rolsuper"] is False
        assert attrs["rolbypassrls"] is False
        assert attrs["rolcreatedb"] is False
        assert attrs["rolcreaterole"] is False
        assert attrs["rolinherit"] is False
        assert attrs["rolcanlogin"] is True, "o teste precisa conectar; senha veio do ambiente"

        poderes = {
            tabela: {
                acao: bool(
                    conn.execute(
                        text("SELECT has_table_privilege(current_user, :t, :a)"),
                        {"t": tabela, "a": acao},
                    ).scalar_one()
                )
                for acao in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            for tabela in ("obras", "construtoras", "nfe_logs", "nfe_itens", "especificacoes")
        }

    for tabela, acoes in poderes.items():
        assert acoes["SELECT"] is True, f"o painel precisa ler {tabela}"
        assert acoes["INSERT"] is False, f"{tabela}: painel não escreve"
        assert acoes["UPDATE"] is False, f"{tabela}: painel não escreve"
        assert acoes["DELETE"] is False, f"{tabela}: painel não escreve"

    with sql_dashboard.connect() as conn:
        for fora_do_painel in ("usuarios", "sessoes", "evidencias", "recebimentos", "fila_nfe"):
            assert not conn.execute(
                text("SELECT has_table_privilege(current_user, :t, 'SELECT')"),
                {"t": fora_do_painel},
            ).scalar_one(), f"{fora_do_painel} não é tabela do painel"


def test_sem_tenant_nenhuma_obra(sql_dashboard: Any, cenario: dict[str, Any]) -> None:
    diag = diagnostico.diagnostico_conexao(sql_dashboard)
    assert diag["usuario"] == "stellspy_dashboard"
    assert diag["obras_visiveis"] == 0
    assert diag["construtora"] is None

    with _como(sql_dashboard, None) as conn:
        assert leitura.listar_obras(conn) == []

    problemas = diagnostico.problemas_da_credencial(diag)
    assert any("DASHBOARD_TENANT_ID" in p for p in problemas)


def test_tenant_a_ve_somente_a_propria_construtora(
    sql_owner: Any, sql_dashboard: Any, cenario: dict[str, Any]
) -> None:
    with sql_owner.connect() as conn:
        esperadas = {
            str(linha)
            for linha in conn.execute(
                text("SELECT id FROM obras WHERE tenant_id = :t"), {"t": cenario["tenant_a"]}
            ).scalars()
        }

    diag = diagnostico.diagnostico_conexao(sql_dashboard, cenario["tenant_a"])
    assert diag["construtora"] == "Construtora Alfa"
    assert diag["obras_visiveis"] == len(esperadas)

    with _como(sql_dashboard, cenario["tenant_a"]) as conn:
        vistas = {o["obra_id"] for o in leitura.listar_obras(conn)}
        construtora = leitura.construtora(conn)

    assert vistas == esperadas
    assert str(cenario["obra_b"]) not in vistas
    assert construtora and construtora["id"] == str(cenario["tenant_a"])


def test_tenant_b_nao_alcanca_obra_de_a(sql_owner: Any, sql_dashboard: Any, cenario: dict[str, Any]) -> None:
    with sql_owner.connect() as conn:
        # Prova de que o dado existe: sem isso o zero do dashboard seria trivial.
        assert _contar(conn, "SELECT count(*) FROM obras WHERE id = :o", o=cenario["obra_a"]) == 1

    with _como(sql_dashboard, cenario["tenant_b"]) as conn:
        assert _contar(conn, "SELECT count(*) FROM obras WHERE id = :o", o=cenario["obra_a"]) == 0
        assert _contar(conn, "SELECT count(*) FROM nfe_logs WHERE id = :n", n=cenario["nfe_a"]) == 0
        assert _contar(
            conn, "SELECT count(*) FROM nfe_itens WHERE nfe_log_id = :n", n=cenario["nfe_a"]
        ) == 0
        assert _contar(conn, "SELECT count(*) FROM construtoras WHERE id = :t", t=cenario["tenant_a"]) == 0


def test_painel_nao_escreve(sql_dashboard: Any, cenario: dict[str, Any]) -> None:
    with pytest.raises(DBAPIError) as erro:
        with _como(sql_dashboard, cenario["tenant_a"]) as conn:
            conn.execute(
                text(
                    "INSERT INTO obras (tenant_id, nome, cnpj_destinatario, api_key) "
                    "VALUES (:t, 'intrusa', :c, :k)"
                ),
                {
                    "t": cenario["tenant_a"],
                    "c": f"{uuid.uuid4().int % 10**14:014d}",
                    "k": f"intrusa-{uuid.uuid4().hex[:8]}",
                },
            )
    assert "permission denied" in str(erro.value).lower()


def test_credencial_de_escrita_ou_cross_tenant_e_recusada(
    sql_owner: Any, sql_app: Any, sql_dashboard: Any, cenario: dict[str, Any]
) -> None:
    tenant = cenario["tenant_a"]

    diag_painel = diagnostico.diagnostico_conexao(sql_dashboard, tenant)
    assert diagnostico.problemas_da_credencial(diag_painel) == []

    diag_owner = diagnostico.diagnostico_conexao(sql_owner, tenant)
    assert diag_owner["superusuario"] or diag_owner["bypass_rls"]
    assert any("superusuário" in p or "BYPASSRLS" in p for p in diagnostico.problemas_da_credencial(diag_owner))

    diag_app = diagnostico.diagnostico_conexao(sql_app, tenant)
    assert diag_app["pode_escrever"] is True
    assert any("pode escrever" in p for p in diagnostico.problemas_da_credencial(diag_app))


def test_listagens_do_painel_nao_misturam_tenants(
    sql_owner: Any, sql_dashboard: Any, cenario: dict[str, Any]
) -> None:
    hoje = date.today()

    with sql_owner.connect() as conn:
        assert _contar(
            conn,
            "SELECT count(*) FROM nfe_itens WHERE nfe_log_id = :n",
            n=cenario["nfe_a"],
        ) == 1

    with _como(sql_dashboard, cenario["tenant_a"]) as conn:
        itens_a = leitura.nfe_itens_periodo(
            conn, obra_id=str(cenario["obra_a"]), d0=hoje - timedelta(days=1), d1=hoje
        )
        itens_b = leitura.nfe_itens_periodo(
            conn, obra_id=str(cenario["obra_b"]), d0=hoje - timedelta(days=1), d1=hoje
        )
        nfes_b = leitura.nfes_resumo(
            conn, obra_id=str(cenario["obra_b"]), d0=hoje - timedelta(days=1), d1=hoje
        )

    assert len(itens_a) == 1
    assert itens_b == []
    assert nfes_b == []


def test_normalizar_tenant_recusa_texto_livre() -> None:
    assert diagnostico.normalizar_tenant(None) is None
    assert diagnostico.normalizar_tenant("") is None
    assert diagnostico.normalizar_tenant("alfa") is None
    valido = str(uuid.uuid4())
    assert diagnostico.normalizar_tenant(f" {valido} ") == valido
