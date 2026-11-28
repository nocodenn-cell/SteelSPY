"""
Consultas somente leitura ao Postgres (mesmo schema da API).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from dashboard.intervalo import intervalo_utc_dias


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
    """Dias escolhidos inclusive, no horário de São Paulo (B13)."""
    start, end_excl = intervalo_utc_dias(d0, d1)

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
          -- status efetivo: item aceito por override conta como VERDE. O fato
          -- técnico continua em ni.status_item.
          CASE WHEN ni.override_aplicado THEN 'VERDE' ELSE ni.status_item END AS status_item,
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
    start, end_excl = intervalo_utc_dias(d0, d1)

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
