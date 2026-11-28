"""B13: o filtro de dia do dashboard segue o dia de São Paulo, não o UTC."""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dashboard.intervalo import intervalo_utc_dias  # noqa: E402


def test_nf_as_22h30_de_sao_paulo_entra_no_proprio_dia() -> None:
    # 27/11 22:30 em São Paulo (UTC-3) = 28/11 01:30 UTC: o dia do operador é 27.
    nf = datetime(2026, 11, 28, 1, 30, tzinfo=timezone.utc)
    inicio, fim = intervalo_utc_dias(date(2026, 11, 27), date(2026, 11, 27))
    assert inicio <= nf < fim


def test_nf_as_00h30_de_sao_paulo_nao_vaza_para_o_dia_anterior() -> None:
    # 28/11 00:30 em São Paulo = 28/11 03:30 UTC: pertence ao dia 28, não ao 27.
    nf = datetime(2026, 11, 28, 3, 30, tzinfo=timezone.utc)
    inicio, fim = intervalo_utc_dias(date(2026, 11, 27), date(2026, 11, 27))
    assert not (inicio <= nf < fim)


def test_intervalo_comeca_as_03h_utc_e_tem_24h_por_dia() -> None:
    inicio, fim = intervalo_utc_dias(date(2026, 11, 27), date(2026, 11, 27))
    assert inicio == datetime(2026, 11, 27, 3, 0, tzinfo=timezone.utc)
    assert fim - inicio == (datetime(2026, 11, 28, 0, 0) - datetime(2026, 11, 27, 0, 0))


def test_periodo_de_dois_dias_inclui_os_dois() -> None:
    inicio, fim = intervalo_utc_dias(date(2026, 11, 26), date(2026, 11, 27))
    assert fim == datetime(2026, 11, 28, 3, 0, tzinfo=timezone.utc)
