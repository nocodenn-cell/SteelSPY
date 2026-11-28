"""
Regras de divergência para itens classificados como cimento (CP-II, CP-V, etc.).

Usada por `conferente.conferir_nf_multiplos_itens` para itens de cimento. A decisão de matching por categoria fica em `conferente.py`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Tuple

from app.services.quantidade_material import converter_quantidade_recebida

# Status alinhados a `app.domain.conferente.StatusConferencia`
VERDE = "VERDE"
AMARELO = "AMARELO"
VERMELHO = "VERMELHO"


def _attrs(esp: dict[str, Any]) -> dict[str, Any]:
    raw = esp.get("atributos_especificos")
    if isinstance(raw, dict):
        return raw
    return {}


def _parse_data_validade(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()[:10]
        try:
            y, m, d = (int(x) for x in s.split("-"))
            return date(y, m, d)
        except (ValueError, AttributeError):
            return None
    return None


def _norm_tipo(s: str | None) -> str:
    return (s or "").strip().upper()


def classificar_item_cimento(
    especificacao: dict[str, Any],
    item_recebido: dict[str, Any],
    *,
    hoje: date | None = None,
) -> Tuple[str, str]:
    """
    Compara especificação (obra) × item recebido (NF / parser).

    `especificacao`: linha de `especificacoes` com `atributos_especificos`.
    `item_recebido`: dict com chaves opcionais: tipo, fck_mpa, data_validade,
    quantidade, unidade (para mensagem).
    """
    h = hoje or datetime.now(timezone.utc).date()
    attrs = _attrs(especificacao)

    tipo_esp = _norm_tipo(attrs.get("tipo") or attrs.get("tipo_cimento"))
    tipo_rec = _norm_tipo(
        item_recebido.get("tipo") or item_recebido.get("tipo_cimento"),
    )
    if tipo_esp and tipo_rec and tipo_esp != tipo_rec:
        return (
            VERMELHO,
            f"TIPO DE CIMENTO DIVERGENTE: especificado {tipo_esp}, NF {tipo_rec}.",
        )

    fck_esp = attrs.get("fck_mpa")
    fck_rec = item_recebido.get("fck_mpa")
    if fck_esp is not None and fck_rec is not None:
        try:
            fe = float(fck_esp)
            fr = float(fck_rec)
        except (TypeError, ValueError):
            fe = fr = None
        if fe is not None and fr is not None:
            diff = abs(fr - fe)
            if diff > 5.0:
                return (
                    VERMELHO,
                    f"FCK muito fora do especificado: {fr} MPa vs {fe} MPa (Δ > 5 MPa).",
                )
            if diff >= 2.0:
                return (
                    AMARELO,
                    f"FCK abaixo do especificado: {fr} MPa vs {fe} MPa (Δ {diff:.1f} MPa).",
                )

    dv = _parse_data_validade(item_recebido.get("data_validade"))
    if dv is not None:
        dias = (dv - h).days
        if dias < 0:
            return VERMELHO, f"CIMENTO FORA DA VALIDADE (validade {dv.isoformat()})."
        if dias < 30:
            return (
                AMARELO,
                f"Cimento próximo do vencimento: {dias} dias até {dv.isoformat()}.",
            )

    q_esp = especificacao.get("quantidade_prevista")
    if q_esp is None:
        q_esp = _attrs(especificacao).get("quantidade_prevista")
    if q_esp is None:
        q_esp = especificacao.get("qtd_planejada_metros")
    try:
        qe = float(q_esp) if q_esp is not None else 0.0
    except (TypeError, ValueError):
        qe = 0.0

    un_rec = item_recebido.get("unidade_original") or item_recebido.get("unidade")
    un_prev = especificacao.get("unidade_prevista") or _attrs(especificacao).get("unidade_prevista")
    conv = converter_quantidade_recebida(item_recebido.get("quantidade", 0), un_rec, un_prev)
    qr = conv.recebida

    if qe > 0:
        if not conv.comparavel:
            return (
                AMARELO,
                f"Quantidade: não comparável — {conv.nota} Conferir manualmente.",
            )
        delta_pct = abs(qr - qe) / qe
        evidencia = f" {conv.nota}" if conv.nota else ""
        if delta_pct > 0.10:
            return (
                VERMELHO,
                f"Quantidade: divergência {delta_pct * 100:.1f}% (>10%).{evidencia}",
            )
        if delta_pct >= 0.02:
            return (
                AMARELO,
                f"Quantidade: divergência {delta_pct * 100:.1f}% (faixa 2–10%).{evidencia}",
            )

    rotulo_tipo = tipo_esp or tipo_rec or "cimento"
    sufixo = f" {conv.nota}" if conv.nota else ""
    return VERDE, f"OK — {qr:g} ({conv.unidade or item_recebido.get('unidade') or 'un'}) {rotulo_tipo}.{sufixo}"
