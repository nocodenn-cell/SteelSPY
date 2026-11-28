"""Intervalo de dias no fuso do negócio (B13). Sem dependências pesadas: testável isoladamente."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

FUSO_NEGOCIO = ZoneInfo("America/Sao_Paulo")


def intervalo_utc_dias(d0: date, d1: date) -> tuple[datetime, datetime]:
    """
    Dias [d0, d1] inclusive no horário de São Paulo, convertidos para UTC.
    Devolve (início, fim_exclusivo) com fuso UTC, prontos para comparar com
    timestamptz no banco. Só a consulta converte; a exibição segue o dia local.
    """
    inicio_local = datetime.combine(d0, time.min, tzinfo=FUSO_NEGOCIO)
    fim_local = datetime.combine(d1 + timedelta(days=1), time.min, tzinfo=FUSO_NEGOCIO)
    return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)
