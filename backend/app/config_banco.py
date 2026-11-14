"""
Resolução da URL do banco.

Regra: em produção, a ausência de DATABASE_URL é erro de subida. Antes, o
fallback para localhost fazia a API iniciar e falhar só na primeira requisição,
com um stack trace que não aponta a configuração.
"""

from __future__ import annotations

from collections.abc import Mapping

URL_DEV_PADRAO = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"

AMBIENTES_PRODUCAO = frozenset({"producao", "production", "prod"})


def resolver_database_url(env: Mapping[str, str]) -> str:
    url = (env.get("DATABASE_URL") or "").strip()
    if url:
        return url
    ambiente = (env.get("STELLSPY_AMBIENTE") or "desenvolvimento").strip().lower()
    if ambiente in AMBIENTES_PRODUCAO:
        raise RuntimeError(
            "DATABASE_URL não definida com STELLSPY_AMBIENTE=producao. "
            "A aplicação não sobe apontando para localhost."
        )
    return URL_DEV_PADRAO
