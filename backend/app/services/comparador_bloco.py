"""
Regras de divergência para itens classificados como bloco (cerâmico / concreto).

Usa `atributos_especificos.dimensoes`, `resistencia_mpa` (ou fck_mpa) e quantidade planejada.
"""

from __future__ import annotations

from typing import Any, Tuple

from app.services.quantidade_material import converter_quantidade_recebida, normalizar_dimensoes

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
    # "19 x 19 x 39 cm" e "19x19x39" são o mesmo bloco: compara pelos números.
    if dims_esp and dims_rec and normalizar_dimensoes(dims_esp) != normalizar_dimensoes(dims_rec):
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

    un_rec = item_recebido.get("unidade_original") or item_recebido.get("unidade")
    un_prev = especificacao.get("unidade_prevista") or attrs.get("unidade_prevista")
    conv = converter_quantidade_recebida(item_recebido.get("quantidade", 0), un_rec, un_prev)
    qr = conv.recebida

    if qe > 0:
        if not conv.comparavel:
            return (
                AMARELO,
                f"Quantidade: não comparável — {conv.nota} Conferir manualmente.",
            )
        delta_pct = abs(qr - qe) / qe
        if delta_pct > 0.10:
            return (
                VERMELHO,
                f"Quantidade: divergência {delta_pct * 100:.1f}% (>10%).",
            )
        if delta_pct >= 0.02:
            return (
                AMARELO,
                f"Quantidade: divergência {delta_pct * 100:.1f}% (faixa 2–10%).",
            )

    rotulo_dim = dims_esp or dims_rec or "bloco"
    return VERDE, f"OK — {qr:g} ({item_recebido.get('unidade') or 'un'}) {rotulo_dim}."
