"""Diagnóstico da credencial do painel — sem Streamlit e sem pandas.

Também é aqui que o painel **exige** o privilégio mínimo: uma credencial que
atravessa tenants (superuser ou BYPASSRLS) ou que escreve nas tabelas é
recusada. O piloto roda com uma construtora, e a credencial do painel não
precisa — nem deve — alcançar as outras.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


def normalizar_tenant(valor: str | None) -> str | None:
    """Aceita só UUID válido. Texto livre viraria filtro silenciosamente vazio."""
    if not valor or not str(valor).strip():
        return None
    try:
        return str(UUID(str(valor).strip()))
    except (ValueError, AttributeError):
        return None


@contextlib.contextmanager
def conexao_do_tenant(engine: Engine, tenant_id: str | None) -> Iterator[Connection]:
    """
    Abre uma conexão, tenta o tenant e devolve a conexão.

    `set_config(..., true)` vale só para a transação: a próxima conexão do pool
    nasce sem contexto. Sem tenant, `tenant_atual()` é NULL e o RLS devolve zero
    linhas — o padrão do banco é fechar.
    """
    with engine.connect() as conn:
        with conn.begin():
            if tenant_id:
                conn.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"),
                    {"t": str(tenant_id)},
                )
            yield conn


def diagnostico_conexao(engine: Engine, tenant_id: str | None = None) -> dict[str, Any]:
    """
    Retrato da credencial: quem é, o que ela atravessa e quantas obras vê.

    `obras_visiveis` é medido **com** o tenant configurado. Zero obras, nesse
    caso, significa "esta construtora não tem obra", não "faltou contexto".
    """
    with conexao_do_tenant(engine, tenant_id) as conn:
        linha = conn.execute(
            text(
                """
                SELECT current_user AS usuario,
                       COALESCE(r.rolsuper, FALSE) AS superusuario,
                       COALESCE(r.rolbypassrls, FALSE) AS bypass_rls,
                       COALESCE(r.rolcanlogin, FALSE) AS pode_logar
                FROM pg_roles r WHERE r.rolname = current_user
                """
            )
        ).mappings().one()
        obras_visiveis = int(conn.execute(text("SELECT count(*) FROM obras")).scalar_one())
        pode_escrever = bool(
            conn.execute(
                text("SELECT has_table_privilege(current_user, 'obras', 'INSERT')")
            ).scalar_one()
        )
        nome = conn.execute(
            text("SELECT nome FROM construtoras LIMIT 1")
        ).scalars().first()

    return {
        "usuario": linha["usuario"],
        "superusuario": bool(linha["superusuario"]),
        "bypass_rls": bool(linha["bypass_rls"]),
        "pode_logar": bool(linha["pode_logar"]),
        "pode_escrever": pode_escrever,
        "obras_visiveis": obras_visiveis,
        "tenant": str(tenant_id) if tenant_id else None,
        "construtora": nome,
    }


def problemas_da_credencial(diag: dict[str, Any]) -> list[str]:
    """
    Lista o que impede a credencial de ser usada no piloto.

    Cada item é uma frase com a correção, porque quem lê isso está no terminal
    do servidor, não no código.
    """
    problemas: list[str] = []
    if diag.get("superusuario"):
        problemas.append(
            f"{diag['usuario']} é superusuário: RLS é ignorado. Use a role "
            "stellspy_dashboard (SELECT, sob RLS)."
        )
    if diag.get("bypass_rls"):
        problemas.append(
            f"{diag['usuario']} tem BYPASSRLS: enxerga qualquer construtora. "
            "Use a role stellspy_dashboard."
        )
    if diag.get("pode_escrever"):
        problemas.append(
            f"{diag['usuario']} pode escrever em obras. O painel é somente "
            "leitura; use a role stellspy_dashboard."
        )
    if not diag.get("tenant"):
        problemas.append(
            "DASHBOARD_TENANT_ID não configurado ou inválido: sem tenant não há "
            "obra visível, por desenho."
        )
    return problemas
