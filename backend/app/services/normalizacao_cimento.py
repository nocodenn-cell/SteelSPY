"""
Conversões de quantidade para cimento (sacos, kg, m³).

Constantes alinhadas ao seed em `normalizacao_materiais` (28 sacos de 50 kg ≈ 1 m³; massa aparente ~1400 kg/m³).
"""

from __future__ import annotations

from typing import Tuple

SACOS_POR_M3 = 28.0
KG_POR_SACO = 50.0
DENSIDADE_KG_M3 = 1400.0


def normalizar_cimento(
    quantidade: float,
    unidade_origem: str,
    unidade_destino: str,
) -> Tuple[float, str]:
    """
    Normaliza quantidade de cimento para a unidade alvo.

    Exemplos:
        28 sacos → 1 m³
        1400 kg → 1 m³
        1 m³ → 1400 kg
    """
    origem = (unidade_origem or "").strip().lower()
    destino = (unidade_destino or "").strip().lower()

    if origem == destino:
        return float(quantidade), destino

    q = float(quantidade)

    if origem == "sacos" and destino == "m3":
        return q / SACOS_POR_M3, "m3"
    if origem == "sacos" and destino == "kg":
        return q * KG_POR_SACO, "kg"

    if origem == "kg" and destino == "sacos":
        return q / KG_POR_SACO, "sacos"
    if origem == "kg" and destino == "m3":
        return q / DENSIDADE_KG_M3, "m3"

    if origem == "m3" and destino == "kg":
        return q * DENSIDADE_KG_M3, "kg"
    if origem == "m3" and destino == "sacos":
        return q * SACOS_POR_M3, "sacos"

    raise ValueError(f"Conversão de cimento não suportada: {origem!r} → {destino!r}")
