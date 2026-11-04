"""
Consultas somente leitura ao Postgres (mesmo schema da API).

O painel lê como `stellspy_dashboard`: SELECT em cinco tabelas, sob RLS, com
`app.tenant_id` fixado na transação pelo `DASHBOARD_TENANT_ID`. Não existe
credencial que atravesse construtoras — um piloto com uma construtora não
precisa de acesso às outras.

O SQL fica em `dashboard/leitura.py` (sem pandas) porque é ele que os testes de
isolamento exercitam com uma conexão real. Este módulo é a camada fina que o
Streamlit consome.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from dashboard import leitura
from dashboard.diagnostico import conexao_do_tenant, diagnostico_conexao

__all__ = [
    "diagnostico_conexao",
    "conexao_do_tenant",
    "get_engine",
    "construtora",
    "listar_obras",
    "carregar_nfe_itens_periodo",
    "carregar_nfes_resumo",
]


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def construtora(engine: Engine, tenant_id: str) -> dict | None:
    with conexao_do_tenant(engine, tenant_id) as conn:
        return leitura.construtora(conn)


def listar_obras(engine: Engine, tenant_id: str) -> pd.DataFrame:
    with conexao_do_tenant(engine, tenant_id) as conn:
        linhas = leitura.listar_obras(conn)
    return pd.DataFrame(linhas, columns=["obra_id", "nome", "cnpj_destinatario"])


def carregar_nfe_itens_periodo(
    engine: Engine,
    *,
    tenant_id: str,
    obra_id: str,
    d0: date,
    d1: date,
) -> pd.DataFrame:
    with conexao_do_tenant(engine, tenant_id) as conn:
        linhas = leitura.nfe_itens_periodo(conn, obra_id=obra_id, d0=d0, d1=d1)
    return pd.DataFrame(linhas)


def carregar_nfes_resumo(
    engine: Engine,
    *,
    tenant_id: str,
    obra_id: str,
    d0: date,
    d1: date,
) -> pd.DataFrame:
    with conexao_do_tenant(engine, tenant_id) as conn:
        linhas = leitura.nfes_resumo(conn, obra_id=obra_id, d0=d0, d1=d1)
    return pd.DataFrame(linhas)
