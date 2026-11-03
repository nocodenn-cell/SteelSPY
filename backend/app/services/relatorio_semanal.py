"""
Agrega NF-e conferidas no período e monta CSV para o relatório semanal.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

TZ_BR = ZoneInfo("America/Sao_Paulo")


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def periodo_rolling_dias(dias: int) -> tuple[datetime, datetime]:
    """Janela [início, fim) em UTC: últimos `dias` dias até agora (modo legado)."""
    fim = agora_utc()
    ini = fim - timedelta(days=max(1, dias))
    return ini, fim


def periodo_utc_rolling(dias: int) -> tuple[datetime, datetime]:
    """Mesmo que periodo_rolling_dias (nome explícito para o job)."""
    return periodo_rolling_dias(dias)


def periodo_br_dias_corridos(dias: int) -> tuple[datetime, datetime]:
    """
    Últimos `dias` dias corridos no fuso America/Sao_Paulo:
    [meia-noite de (hoje_BR - dias + 1), agora_BR] convertidos para UTC.
    """
    now_br = datetime.now(TZ_BR)
    d_start = now_br.date() - timedelta(days=max(1, dias) - 1)
    start_br = datetime.combine(d_start, time.min, tzinfo=TZ_BR)
    ini = start_br.astimezone(timezone.utc)
    fim = now_br.astimezone(timezone.utc)
    return ini, fim


def relatorio_usar_tz_br() -> bool:
    return os.getenv("RELATORIO_USAR_TZ_BR", "").strip() == "1"


def compor_chave_idempotencia(*, dias: int, modo: str) -> str:
    """
    Uma chave por execução lógica por dia (evita reenvio se o cron rodar 2×).
    modo: 'UTC' | 'BR'
    """
    if modo == "BR":
        d = datetime.now(TZ_BR).date().isoformat()
    else:
        d = agora_utc().date().isoformat()
    return f"steelspy:v1:{dias}d:{modo}:{d}"


def periodo_relatorio_job() -> tuple[datetime, datetime, str, str]:
    """
    Retorna (inicio_utc, fim_utc, chave_idempotencia, etiqueta_tz_para_email).
    RELATORIO_USAR_TZ_BR=1 → janela em dias corridos BR; senão rolling UTC.
    """
    dias = relatorio_dias_env()
    if relatorio_usar_tz_br():
        ini, fim = periodo_br_dias_corridos(dias)
        chave = compor_chave_idempotencia(dias=dias, modo="BR")
        return ini, fim, chave, "America/Sao_Paulo (dias corridos)"
    ini, fim = periodo_utc_rolling(dias)
    chave = compor_chave_idempotencia(dias=dias, modo="UTC")
    return ini, fim, chave, "UTC (rolling)"


def _int_jsonb(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class LinhaRelatorio:
    obra_id: str
    obra_nome: str
    nfe_log_id: str
    chave_acesso: str
    processado_em: datetime
    status_conferencia: str
    tipo: str
    emitente_nome: str
    nfe_numero: str
    nfe_serie: str
    resumo_global: str
    itens_total: int | None
    itens_verdes: int | None
    itens_amarelos: int | None
    itens_vermelhos: int | None


def listar_logs_periodo_obra(
    db: Session,
    *,
    obra_id: UUID,
    inicio_utc: datetime,
    fim_utc: datetime,
) -> list[LinhaRelatorio]:
    rows = db.execute(
        text("""
            SELECT
              o.id AS obra_id,
              o.nome AS obra_nome,
              n.id AS nfe_log_id,
              n.chave_acesso,
              n.processado_em,
              n.status_conferencia,
              COALESCE(n.tipo, 'entrada') AS tipo,
              n.resumo_global,
              n.itens_resumo,
              n.xml_data
            FROM nfe_logs n
            JOIN obras o ON o.id = n.obra_id
            WHERE n.obra_id = :obra
              AND n.processado_em >= :ini
              AND n.processado_em < :fim
            ORDER BY n.processado_em ASC
        """),
        {"obra": str(obra_id), "ini": inicio_utc, "fim": fim_utc},
    ).mappings().all()

    out: list[LinhaRelatorio] = []
    for r in rows:
        xd = r.get("xml_data")
        if isinstance(xd, str):
            try:
                xd = json.loads(xd)
            except json.JSONDecodeError:
                xd = {}
        elif xd is None:
            xd = {}
        elif not isinstance(xd, dict):
            xd = {}

        ir = r.get("itens_resumo")
        if isinstance(ir, str):
            try:
                ir = json.loads(ir)
            except json.JSONDecodeError:
                ir = {}
        elif ir is None:
            ir = {}
        elif not isinstance(ir, dict):
            ir = {}

        out.append(
            LinhaRelatorio(
                obra_id=str(r["obra_id"]),
                obra_nome=str(r["obra_nome"] or ""),
                nfe_log_id=str(r["nfe_log_id"]),
                chave_acesso=str(r["chave_acesso"]),
                processado_em=r["processado_em"],
                status_conferencia=str(r["status_conferencia"] or ""),
                tipo=str(r["tipo"] or "entrada"),
                emitente_nome=str(xd.get("emitente_nome") or ""),
                nfe_numero=str(xd.get("nfe_numero") or ""),
                nfe_serie=str(xd.get("nfe_serie") or ""),
                resumo_global=str(r["resumo_global"] or ""),
                itens_total=_int_jsonb(ir.get("total")),
                itens_verdes=_int_jsonb(ir.get("verdes")),
                itens_amarelos=_int_jsonb(ir.get("amarelos")),
                itens_vermelhos=_int_jsonb(ir.get("vermelhos")),
            )
        )
    return out


def obras_com_relatorio_configurado(db: Session) -> list[dict[str, Any]]:
    """Obras com pelo menos um e-mail em relatorio_email_destinos."""
    rows = db.execute(
        text("""
            SELECT id, nome, relatorio_email_destinos,
                   relatorio_ultimo_periodo_chave, relatorio_ultimo_envio_em
            FROM obras
            WHERE cardinality(relatorio_email_destinos) > 0
        """)
    ).mappings().all()
    return [dict(x) for x in rows]


def montar_csv_bytes(linhas: list[LinhaRelatorio]) -> bytes:
    """UTF-8 com BOM para abrir bem no Excel (pt-BR)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    w.writerow(
        [
            "obra_id",
            "obra_nome",
            "nfe_log_id",
            "chave_acesso",
            "processado_em_utc",
            "status_conferencia",
            "tipo",
            "emitente_nome",
            "nfe_numero",
            "nfe_serie",
            "resumo_global",
            "itens_total",
            "itens_verdes",
            "itens_amarelos",
            "itens_vermelhos",
        ]
    )
    for ln in linhas:
        pe = ln.processado_em
        if pe.tzinfo is None:
            pe = pe.replace(tzinfo=timezone.utc)
        w.writerow(
            [
                ln.obra_id,
                ln.obra_nome,
                ln.nfe_log_id,
                ln.chave_acesso,
                pe.isoformat(),
                ln.status_conferencia,
                ln.tipo,
                ln.emitente_nome,
                ln.nfe_numero,
                ln.nfe_serie,
                ln.resumo_global,
                ln.itens_total if ln.itens_total is not None else "",
                ln.itens_verdes if ln.itens_verdes is not None else "",
                ln.itens_amarelos if ln.itens_amarelos is not None else "",
                ln.itens_vermelhos if ln.itens_vermelhos is not None else "",
            ]
        )
    raw = buf.getvalue().encode("utf-8-sig")
    return raw


def nome_arquivo_csv(obra_id: UUID, inicio_utc: datetime, fim_utc: datetime) -> str:
    oid = str(obra_id).replace("-", "")[:12]
    d0 = inicio_utc.strftime("%Y%m%d")
    d1 = fim_utc.strftime("%Y%m%d")
    return f"steelspy_nfe_{oid}_{d0}_{d1}.csv"


def corpo_email_pt(
    obra_nome: str,
    inicio_utc: datetime,
    fim_utc: datetime,
    num_linhas: int,
    *,
    etiqueta_tz: str,
) -> str:
    return (
        f"Relatório automático SteelSpy — obra: {obra_nome}\n"
        f"Janela de dados ({etiqueta_tz}): {inicio_utc.isoformat()} → {fim_utc.isoformat()} (instantes em ISO UTC)\n"
        f"Quantidade de registros (NF-e): {num_linhas}\n\n"
        f"O arquivo CSV em anexo usa separador ';' e codificação UTF-8 (BOM).\n"
        f"Coluna processado_em_utc permanece em UTC para rastreio.\n"
    )


def relatorio_dias_env() -> int:
    raw = os.getenv("RELATORIO_DIAS", "7").strip()
    try:
        d = int(raw)
        return max(1, min(d, 366))
    except ValueError:
        return 7


def atualizar_idempotencia_relatorio(db: Session, obra_id: UUID, chave: str) -> None:
    """Persiste chave do envio e horário (evita duplicado no mesmo dia lógico)."""
    db.execute(
        text("""
            UPDATE obras
            SET relatorio_ultimo_periodo_chave = :chave,
                relatorio_ultimo_envio_em = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"chave": chave, "id": str(obra_id)},
    )
    db.commit()
