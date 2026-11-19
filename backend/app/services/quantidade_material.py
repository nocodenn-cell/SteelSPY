"""Comparação de quantidade para cimento e bloco, com normalização de unidade.

Problema que este módulo resolve
--------------------------------

Os comparadores de cimento e bloco subtraíam `quantidade` da NF de
`quantidade_prevista` da especificação **sem olhar a unidade**. Previsto
`28 sacos` e NF com `1400 kg` (a mesma carga) virava divergência de 4900%,
VERMELHO — um falso alarme que ensina o fiscal a ignorar o sistema.

Regra de honestidade (a mesma do motor de correlação): se as unidades não se
convertem com segurança, **não se compara**. O resultado é `comparavel=False`
e quem chama marca para conferência humana, em vez de inventar um percentual.

Reutiliza `normalizar_cimento` (constantes de sacos/kg/m³), sem duplicar fatores.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.normalizacao_cimento import normalizar_cimento

_SACOS = {"SC", "SAC", "SACO", "SACOS"}
_KG = {"KG", "KGS", "KILO", "QUILO", "QUILOGRAMA", "QUILOGRAMAS"}
_M3 = {"M3", "M³", "METRO CUBICO", "METROS CUBICOS", "M_CUBO"}
_TON = {"T", "TON", "TONELADA", "TONELADAS"}
_UNIDADE = {"UN", "UND", "UNID", "UNIDADE", "UNIDADES", "PC", "PCS", "PECA", "PECAS", "PÇ", "PEÇA", "PEÇAS", "MIL", "MILHEIRO"}


@dataclass(frozen=True)
class QuantidadeComparavel:
    comparavel: bool
    recebida: float  # na unidade da especificação, quando comparável
    unidade: str  # unidade em que `recebida` está expressa
    nota: str | None = None  # evidência da conversão, ou motivo de não comparar


def _canonica(unidade: Any) -> str | None:
    u = str(unidade or "").strip().upper()
    if not u:
        return None
    if u in _SACOS:
        return "sacos"
    if u in _KG:
        return "kg"
    if u in _M3:
        return "m3"
    if u in _TON:
        return "ton"
    if u in _UNIDADE:
        return "un"
    return u.lower()


def _fator_milheiro(unidade: Any) -> float:
    return 1000.0 if str(unidade or "").strip().upper() in {"MIL", "MILHEIRO"} else 1.0


def converter_quantidade_recebida(
    quantidade: Any,
    unidade_recebida: Any,
    unidade_prevista: Any,
) -> QuantidadeComparavel:
    """
    Expressa a quantidade da NF na unidade da especificação.

    - Sem unidade na especificação (cadastro legado): compara como veio, sem
      nota — preserva o comportamento anterior para dados antigos.
    - Mesma unidade: nada a converter.
    - sacos/kg/m³/toneladas: converte pelas constantes de `normalizacao_cimento`.
    - Qualquer outro par: `comparavel=False`.
    """
    try:
        q = float(quantidade)
    except (TypeError, ValueError):
        return QuantidadeComparavel(False, 0.0, "", "quantidade da NF ausente ou ilegível")

    destino = _canonica(unidade_prevista)
    origem = _canonica(unidade_recebida)

    if destino is None or origem is None:
        return QuantidadeComparavel(True, q, destino or origem or "")

    q *= _fator_milheiro(unidade_recebida)
    if origem == "ton":
        q, origem = q * 1000.0, "kg"
    destino_base = destino
    if destino == "ton":
        destino_base = "kg"

    if origem == destino_base:
        if destino == "ton":
            q /= 1000.0
        return QuantidadeComparavel(True, q, destino)

    if {origem, destino_base} <= {"sacos", "kg", "m3"}:
        convertida, _ = normalizar_cimento(q, origem, destino_base)
        if destino == "ton":
            convertida /= 1000.0
        nota = (
            f"NF em {unidade_recebida} convertida para {destino}: "
            f"{float(quantidade):g} → {convertida:g}."
        )
        return QuantidadeComparavel(True, convertida, destino, nota)

    return QuantidadeComparavel(
        False,
        q,
        origem,
        f"unidades sem conversão segura (NF em {unidade_recebida}, previsto em {unidade_prevista}).",
    )


def normalizar_dimensoes(valor: Any) -> str:
    """'19 x 19 x 39 cm' → '19x19x39'. Mesma regra usada no casamento da especificação."""
    import re

    if valor is None:
        return ""
    nums = re.findall(r"\d+", str(valor))
    if len(nums) >= 3:
        return "x".join(nums[:3])
    return re.sub(r"\s+", "", str(valor).strip().lower())
