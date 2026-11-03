"""
Heurísticas para extrair da descrição do item da NF-e campos usados em multimaterial.

Não substitui campos estruturados quando a API já envia `bitola_mm`, etc.
"""

from __future__ import annotations

import re
from typing import Any


def extrair_campos_multimaterial(descricao: Any) -> dict[str, Any]:
    """
    Retorna chaves opcionais: tipo_cimento, fck_mpa, dimensoes, resistencia_mpa.
    """
    out: dict[str, Any] = {}
    if descricao is None:
        return out
    s_raw = str(descricao)
    s = s_raw.upper()

    # Tipo de cimento (CP-II, CP-V, …)
    if re.search(r"CP\s*[- ]?\s*III\b", s_raw, re.I):
        out["tipo_cimento"] = "CP-III"
    elif re.search(r"CP\s*[- ]?\s*II\b", s_raw, re.I) and "III" not in s:
        out["tipo_cimento"] = "CP-II"
    elif re.search(r"CP\s*[- ]?\s*IV\b", s_raw, re.I):
        out["tipo_cimento"] = "CP-IV"
    elif re.search(r"CP\s*[- ]?\s*V\b", s_raw, re.I):
        out["tipo_cimento"] = "CP-V"

    # FCK (MPa) em produto ou observação
    mf = re.search(r"FCK\s*[=:]?\s*(\d+(?:[.,]\d+)?)", s_raw, re.I)
    if mf:
        try:
            out["fck_mpa"] = float(mf.group(1).replace(",", "."))
        except ValueError:
            pass

    # Dimensões tipo 19x19x39 ou 19 X 19 X 39 cm
    md = re.search(r"(\d+)\s*[Xx]\s*(\d+)\s*[Xx]\s*(\d+)", s_raw)
    if md:
        out["dimensoes"] = f"{md.group(1)}x{md.group(2)}x{md.group(3)}"

    # Resistência explícita em MPa (bloco / estrutural)
    mr = re.search(r"(\d+(?:[.,]\d+)?)\s*MPA", s_raw, re.I)
    if mr and "fck_mpa" not in out:
        try:
            out["resistencia_mpa"] = float(mr.group(1).replace(",", "."))
        except ValueError:
            pass

    return out
