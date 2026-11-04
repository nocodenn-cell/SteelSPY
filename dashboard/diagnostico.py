"""
Diagnóstico da conexão do dashboard, sem dependência de pandas.

Separado das consultas de negócio porque é a única pergunta que precisa de
resposta antes de qualquer gráfico: esta credencial enxerga mais de uma
construtora? Com a role da aplicação e sem contexto de tenant, a resposta
correta é "não" — e o dashboard precisa dizer isso em vez de mostrar zero obras.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def diagnostico_conexao(engine: Engine) -> dict[str, Any]:
    """
    Diz se a conexão do dashboard consegue atravessar tenants.
    Não tenta contornar RLS: apenas relata.
    """
    with engine.connect() as conn:
        linha = conn.execute(
            text(
                """
                SELECT current_user AS usuario,
                       COALESCE(r.rolsuper, FALSE) AS superusuario,
                       COALESCE(r.rolbypassrls, FALSE) AS bypass_rls
                FROM pg_roles r
                WHERE r.rolname = current_user
                """
            )
        ).mappings().one()
        obras_visiveis = int(conn.execute(text("SELECT count(*) FROM obras")).scalar_one())
    return {
        "usuario": linha["usuario"],
        "superusuario": bool(linha["superusuario"]),
        "bypass_rls": bool(linha["bypass_rls"]),
        "obras_visiveis": obras_visiveis,
    }
