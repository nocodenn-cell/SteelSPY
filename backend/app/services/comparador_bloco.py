"""
Regras de divergência para itens classificados como bloco (cerâmico / concreto).

Usa `atributos_especificos.dimensoes`, `resistencia_mpa` (ou fck_mpa) e quantidade planejada.
"""

from __future__ import annotations

from typing import Any, Tuple

VERDE = "VERDE"
AMARELO = "AMARELO"
VERMELHO = "VERMELHO"


def _attrs(esp: dict[str, Any]) -> dict[str, Any]:
    raw = esp.get("atributos_especificos")
    if isinstance(raw, dict):
        return raw
    return {}


def classificar_item_bloco(
    especificacao: dict[str, Any],
    item_recebido: dict[str, Any],
) -> Tuple[str, str]:
    """
    Compara especificação × NF (campos opcionais vindos do parser de descrição).
    """
    attrs = _attrs(especificacao)

    dims_esp = (attrs.get("dimensoes") or "").strip()
    dims_rec = (item_recebido.get("dimensoes") or "").strip()
    if dims_esp and dims_rec and dims_esp.upper() != dims_rec.upper():
        return (
            VERMELHO,
            f"DIMENSÕES DIVERGENTES: especificado {dims_esp}, NF {dims_rec}.",
        )

    fck_esp = attrs.get("resistencia_mpa")
    if fck_esp is None:
        fck_esp = attrs.get("fck_mpa")
    fck_rec = item_recebido.get("resistencia_mpa")
    if fck_rec is None:
        fck_rec = item_recebido.get("fck_mpa")

    if fck_esp is not None and fck_rec is not None:
        try:
            fe = float(fck_esp)
            fr = float(fck_rec)
        except (TypeError, ValueError):
            fe = fr = None
        if fe is not None and fr is not None:
            diff = abs(fr - fe)
            if diff > 1.0:
                return (
                    VERMELHO,
                    f"RESISTÊNCIA FORA DO ESPERADO: {fr} MPa vs {fe} MPa (Δ > 1 MPa).",
                )
            if diff > 0.5:
                return (
                    AMARELO,
                    f"RESISTÊNCIA ABAIXO DO ESPECIFICADO: {fr} MPa vs {fe} MPa (Δ {diff:.2f} MPa).",
                )

    q_esp = especificacao.get("quantidade_prevista")
    if q_esp is None:
        q_esp = attrs.get("quantidade_prevista")
    if q_esp is None:
        q_esp = especificacao.get("qtd_planejada_metros")
    try:
        qe = float(q_esp) if q_esp is not None else 0.0
    except (TypeError, ValueError):
        qe = 0.0

    try:
        qr = float(item_recebido.get("quantidade", 0))
    except (TypeError, ValueError):
        qr = 0.0

    if qe > 0:
        delta_pct = abs(qr - qe) / qe
        if delta_pct > 0.10:
            return (
                VERMELHO,
                f"QUANTIDADE: divergência {delta_pct * 100:.1f}% (>10%).",
            )
        if delta_pct >= 0.02:
            return (
                AMARELO,
                f"QUANTIDADE: divergência {delta_pct * 100:.1f}% (faixa 2–10%).",
            )

    rotulo_dim = dims_esp or dims_rec or "bloco"
    return VERDE, f"OK — {qr:g} ({item_recebido.get('unidade') or 'un'}) {rotulo_dim}."
