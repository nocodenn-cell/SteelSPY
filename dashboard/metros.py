"""
Metros lineares a partir das colunas persistidas em nfe_itens (alinhado ao domínio conferente).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite `streamlit run dashboard/app.py` a partir da raiz do repositório
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

from app.domain.conferente import quantidade_recebida_em_metros  # noqa: E402


def metros_do_item(linha: dict) -> float | None:
    """linha: bitola_recebida, quantidade_recebida, unidade_recebida, metros_por_barra opcional."""
    try:
        bit = linha.get("bitola_recebida")
        if bit is None:
            return None
        qtd = float(linha.get("quantidade_recebida") or 0)
        un = str(linha.get("unidade_recebida") or "KG").upper()
        item = {
            "quantidade": qtd,
            "unidade": un,
            "bitola_mm": float(bit),
            "metros_por_barra": float(linha.get("metros_por_barra") or 12.0),
        }
        return float(quantidade_recebida_em_metros(item))
    except Exception:
        return None
