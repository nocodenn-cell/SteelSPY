"""
Consultas somente leitura ao Postgres (mesmo schema da API).

O dashboard cruza tenants por definição (lista todas as obras). Com as tabelas
sob `FORCE ROW LEVEL SECURITY`, a role operacional `stellspy_app` só vê a obra
do tenant definido na transação — sem contexto, a lista volta vazia. Por isso o
dashboard precisa de uma credencial de back-office (`DASHBOARD_DATABASE_URL`) e
avisa quando a conexão recebida está sujeita a RLS.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, time, timezone

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from dashboard.diagnostico import diagnostico_conexao

__all__ = [
    "diagnostico_conexao",
    "get_engine",
    "listar_obras",
    "carregar_nfe_itens_periodo",
    "carregar_nfes_resumo",
]


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def listar_obras(engine: Engine) -> pd.DataFrame:
    q = text(
        """
        SELECT id::text AS obra_id, nome, cnpj_destinatario
        FROM obras
        ORDER BY nome
        """
    )
    return pd.read_sql(q, engine)


def carregar_nfe_itens_periodo(
    engine: Engine,
    *,
    obra_id: str,
    d0: date,
    d1: date,
) -> pd.DataFrame:
    """Intervalo [d0 00:00 UTC, d1+1 00:00 UTC) — inclusive nos dias escolhidos."""
    start = datetime.combine(d0, time.min, tzinfo=timezone.utc)
    end_excl = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=timezone.utc)

    q = text(
        """
        SELECT
          nl.id::text AS nfe_log_id,
          nl.chave_acesso,
          nl.processado_em,
          nl.status_conferencia AS status_nf,
          nl.tipo AS tipo_nf,
          ni.item_numero,
          ni.bitola_recebida,
          ni.marca_recebida,
          ni.quantidade_recebida,
          ni.unidade_recebida,
          ni.status_item,
          ni.especificacao_id::text AS especificacao_id,
          e.qtd_planejada_metros,
          e.bitola_mm AS esp_bitola_mm,
          e.marca_exigida
        FROM nfe_itens ni
        INNER JOIN nfe_logs nl ON nl.id = ni.nfe_log_id
        LEFT JOIN especificacoes e ON e.id = ni.especificacao_id
        WHERE nl.obra_id = CAST(:obra AS uuid)
          AND nl.processado_em >= :t0
          AND nl.processado_em < :t1
          AND nl.status_conferencia <> 'PENDENTE'
        ORDER BY nl.processado_em, ni.item_numero
        """
    )
    return pd.read_sql(
        q,
        engine,
        params={"obra": obra_id, "t0": start, "t1": end_excl},
    )


def carregar_nfes_resumo(
    engine: Engine,
    *,
    obra_id: str,
    d0: date,
    d1: date,
) -> pd.DataFrame:
    start = datetime.combine(d0, time.min, tzinfo=timezone.utc)
    end_excl = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=timezone.utc)

    q = text(
        """
        SELECT
          nl.id::text AS nfe_log_id,
          nl.chave_acesso,
          nl.processado_em,
          nl.status_conferencia,
          nl.tipo,
          nl.resumo_global,
          nl.itens_resumo
        FROM nfe_logs nl
        WHERE nl.obra_id = CAST(:obra AS uuid)
          AND nl.processado_em >= :t0
          AND nl.processado_em < :t1
          AND nl.status_conferencia <> 'PENDENTE'
        ORDER BY nl.processado_em DESC
        """
    )
    return pd.read_sql(q, engine, params={"obra": obra_id, "t0": start, "t1": end_excl})
