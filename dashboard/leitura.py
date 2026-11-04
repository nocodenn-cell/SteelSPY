"""Leitura do painel: SQL puro, sem pandas.

Separado de `queries.py` de propósito. O que precisa de teste é *o que* o
dashboard consegue ler com a credencial dele — e isso se prova com uma conexão
real, sem precisar instalar Streamlit/pandas no ambiente de teste.

Toda função recebe uma conexão **já dentro da transação com `app.tenant_id`**
(ver `dashboard.diagnostico.conexao_do_tenant`). Nenhuma delas aceita tenant
como filtro opcional: quem abre a conexão é que escolhe o tenant, e o RLS no
banco confere.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


def construtora(conn: Connection) -> dict[str, Any] | None:
    """A construtora do tenant da transação (o RLS garante que é uma só)."""
    linha = conn.execute(
        text("SELECT id::text AS id, nome FROM construtoras LIMIT 1")
    ).mappings().first()
    return dict(linha) if linha else None


def listar_obras(conn: Connection) -> list[dict[str, Any]]:
    linhas = conn.execute(
        text(
            """
            SELECT id::text AS obra_id, nome, cnpj_destinatario
            FROM obras
            ORDER BY nome
            """
        )
    ).mappings().all()
    return [dict(linha) for linha in linhas]


def _janela(d0: date, d1: date) -> tuple[datetime, datetime]:
    """Intervalo [d0 00:00 UTC, d1+1 00:00 UTC) — inclusive nos dias escolhidos."""
    inicio = datetime.combine(d0, time.min, tzinfo=timezone.utc)
    fim = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return inicio, fim


def nfe_itens_periodo(
    conn: Connection, *, obra_id: str, d0: date, d1: date
) -> list[dict[str, Any]]:
    inicio, fim = _janela(d0, d1)
    linhas = conn.execute(
        text(
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
        ),
        {"obra": obra_id, "t0": inicio, "t1": fim},
    ).mappings().all()
    return [dict(linha) for linha in linhas]


def nfes_resumo(
    conn: Connection, *, obra_id: str, d0: date, d1: date
) -> list[dict[str, Any]]:
    inicio, fim = _janela(d0, d1)
    linhas = conn.execute(
        text(
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
        ),
        {"obra": obra_id, "t0": inicio, "t1": fim},
    ).mappings().all()
    return [dict(linha) for linha in linhas]
