"""
Núcleo de normalização e matching NF-e × especificação.
Peso linear aproximada: kg/m = (bitola_mm²)/162 (vergalhão redondo, convenção usual no Brasil).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.services.comparador_bloco import classificar_item_bloco
from app.services.comparador_cimento import classificar_item_cimento
from app.services.material_categoria import detectar_categoria_material
from app.services.nfe_item_campos import extrair_campos_multimaterial
from app.utils.chave_nfe import ChaveNFeInvalidaError, validar_chave_acesso_nfe


class StatusConferencia(str, Enum):
    PENDENTE = "PENDENTE"
    VERDE = "VERDE"
    AMARELO = "AMARELO"
    VERMELHO = "VERMELHO"


class TipoAlerta(str, Enum):
    """Rótulo principal para PWA / WhatsApp."""

    CONFORME = "CONFORME"
    MATERIAL_NAO_SOLICITADO = "MATERIAL_NAO_SOLICITADO"
    MARCA_DIVERGENTE = "MARCA_DIVERGENTE"
    QUANTIDADE_DIVERGENTE = "QUANTIDADE_DIVERGENTE"
    MISTO = "DIVERGENCIAS_MULTIPLAS"
    PENDENTE_XML = "PENDENTE_XML"


def validar_chave(chave: str) -> str:
    """Valida 44 dígitos e DV módulo 11 antes de qualquer API paga."""
    return validar_chave_acesso_nfe(chave)


def kg_por_metro_bitola(bitola_mm: float) -> float:
    """Massa linear teórica (kg/m) a partir do diâmetro nominal em mm."""
    d = float(bitola_mm)
    if d <= 0:
        raise ValueError("bitola_mm deve ser positiva.")
    return (d * d) / 162.0


def converter_para_metros(peso_kg: float, bitola_mm: float) -> float:
    """
    Converte massa (kg) em metros lineares usando kg/m = bitola_mm²/162.
    Equivalente a: metros = peso_kg / (bitola_mm**2 / 162).
    """
    kg_m = kg_por_metro_bitola(bitola_mm)
    if kg_m <= 0:
        raise ValueError("kg/m inválido.")
    return float(peso_kg) / kg_m


def _pior(a: StatusConferencia, b: StatusConferencia) -> StatusConferencia:
    ordem = {
        StatusConferencia.VERDE: 0,
        StatusConferencia.AMARELO: 1,
        StatusConferencia.VERMELHO: 2,
        StatusConferencia.PENDENTE: -1,
    }
    return a if ordem[a] >= ordem[b] else b


def _pior_alerta(a: TipoAlerta, b: TipoAlerta) -> TipoAlerta:
    """Prioridade para título do alerta (mais grave vence)."""
    ordem = {
        TipoAlerta.CONFORME: 0,
        TipoAlerta.PENDENTE_XML: 0,
        TipoAlerta.QUANTIDADE_DIVERGENTE: 1,
        TipoAlerta.MARCA_DIVERGENTE: 2,
        TipoAlerta.MISTO: 3,
        TipoAlerta.MATERIAL_NAO_SOLICITADO: 4,
    }
    return a if ordem[a] >= ordem[b] else b


def _norm_marca(s: str | None) -> str:
    return (s or "").strip().upper()


def _bitolas_equivalentes(a: float | None, b: float | None, tol_mm: float = 0.5) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol_mm


def _categoria_material_esp(esp: dict[str, Any]) -> str:
    """Linhas antigas sem coluna assumem aço."""
    c = esp.get("categoria_material")
    if not c:
        return "aco"
    return str(c).strip().lower()


def _attrs_especificacao(esp: dict[str, Any]) -> dict[str, Any]:
    raw = esp.get("atributos_especificos")
    if isinstance(raw, dict):
        return raw
    return {}


def _slug_tipo_cimento(s: str | None) -> str:
    """Compara CP-II ≈ CP II ≈ CPII."""
    return "".join(c for c in (s or "").upper() if c.isalnum())


def _norm_dimensoes_val(val: Any) -> str:
    """Ex.: '19 x 19 x 39 cm' → '19x19x39' (primeiros 3 números)."""
    if val is None:
        return ""
    nums = re.findall(r"\d+", str(val))
    if len(nums) >= 3:
        return "x".join(nums[:3])
    return re.sub(r"\s+", "", str(val).strip().lower())


def buscar_especificacao_por_bitola(
    bitola_xml: float | None,
    especificacoes: list[dict[str, Any]],
    tol_mm: float = 0.5,
) -> dict[str, Any] | None:
    """Primeira especificação de aço cuja bitola coincida com a da NF (tolerância default 0,5 mm)."""
    if bitola_xml is None:
        return None
    for esp in especificacoes:
        if _categoria_material_esp(esp) != "aco":
            continue
        b = esp.get("bitola_mm")
        if b is not None and _bitolas_equivalentes(float(b), float(bitola_xml), tol_mm):
            return esp
    return None


def buscar_especificacao_cimento(
    item_xml: dict[str, Any],
    especificacoes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    linhas = [e for e in especificacoes if _categoria_material_esp(e) == "cimento"]
    if not linhas:
        return None
    tr = _slug_tipo_cimento(str(item_xml.get("tipo_cimento") or item_xml.get("tipo") or ""))
    if not tr:
        return linhas[0] if len(linhas) == 1 else None
    for esp in linhas:
        a = _attrs_especificacao(esp)
        te = _slug_tipo_cimento(str(a.get("tipo") or esp.get("material_tipo") or ""))
        if te and te == tr:
            return esp
    return None


def buscar_especificacao_bloco(
    item_xml: dict[str, Any],
    especificacoes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    linhas = [e for e in especificacoes if _categoria_material_esp(e) == "bloco"]
    if not linhas:
        return None
    dr = _norm_dimensoes_val(item_xml.get("dimensoes"))
    if not dr:
        return linhas[0] if len(linhas) == 1 else None
    for esp in linhas:
        de = _norm_dimensoes_val(_attrs_especificacao(esp).get("dimensoes"))
        if de == dr:
            return esp
    return None


def _aplicar_modo_aprendizado_item(
    status: StatusConferencia,
    motivos: list[str],
    config: ConfigObraConferente,
) -> tuple[StatusConferencia, list[str], str | None]:
    checkpoint: str | None = None
    if status == StatusConferencia.VERMELHO and config.modo_aprendizado:
        motivos_pre = [m for m in motivos if "modo_aprendizado" not in m.lower()]
        checkpoint = _mensagem_checkpoint_aprendizado(motivos_pre)
        status = StatusConferencia.AMARELO
        motivos.append(
            "modo_aprendizado: status rebaixado de VERMELHO para AMARELO (entrada não bloqueada automaticamente)."
        )
    return status, motivos, checkpoint


def _status_str_para_enum(s: str) -> StatusConferencia:
    return StatusConferencia[s]


def _conclusao_por_status(st: StatusConferencia) -> str:
    if st == StatusConferencia.VERMELHO:
        return "Risco estrutural alto — ação necessária"
    if st == StatusConferencia.AMARELO:
        return "Atenção — validar com engenharia"
    return "Dentro do especificado"


def _rotulo_item_nf(item_xml: dict[str, Any], indice: int) -> str:
    desc = item_xml.get("descricao") or item_xml.get("xProd") or item_xml.get("material_tipo")
    if desc:
        return str(desc)
    m = _norm_marca(item_xml.get("marca"))
    b = item_xml.get("bitola_mm")
    return f"Item NF {indice + 1}" + (f" — {b} mm" if b is not None else "") + (f" ({m})" if m else "")


def _mensagem_checkpoint_aprendizado(motivos_vermelho: list[str]) -> str:
    """Texto explícito para WhatsApp/PWA quando houve rebaixamento por modo aprendizado."""
    trecho = "; ".join(motivos_vermelho[:4]) if motivos_vermelho else "Divergência de conformidade"
    return (
        "\u26a0\ufe0f DIVERG\u00caNCIA IDENTIFICADA: "
        f"{trecho}. "
        "O sistema não bloqueou a entrada por estar em Modo Aprendizado, "
        "mas registre se esta divergência é aceitável para a obra."
    )


def _motivos_tem_marca_critica(motivos: list[str]) -> bool:
    for m in motivos:
        if m.startswith("Marca:") and "aceita similar" not in m:
            return True
    return False


def _motivos_tem_quantidade_critica(motivos: list[str]) -> bool:
    return any(m.startswith("Quantidade:") for m in motivos)


def _safe_float_qtd(x: Any) -> float | None:
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _trecho_qtd_unidade(item_xml: dict[str, Any]) -> str:
    """Quantidade + unidade como na NF (laudo / PWA)."""
    uo = str(item_xml.get("unidade_original") or item_xml.get("unidade") or "").strip()
    q = item_xml.get("quantidade")
    if q is None:
        return uo or "—"
    try:
        qf = float(q)
        if abs(qf - round(qf)) < 1e-9:
            qs = str(int(round(qf)))
        else:
            qs = f"{qf:g}"
    except (TypeError, ValueError):
        qs = str(q)
    return f"{qs} {uo}".strip() if uo else qs


def _bitola_txt(bitola_nf: Any) -> str:
    if bitola_nf is None:
        return "—"
    try:
        b = float(bitola_nf)
        if abs(b - round(b)) < 1e-9:
            return f"{int(round(b))} mm"
        return f"{b:g} mm"
    except (TypeError, ValueError):
        return f"{bitola_nf} mm"


def divergencias_from_motivos(motivos: list[str]) -> list[str]:
    """Tags estruturadas para JSON em nfe_itens.divergencias."""
    tags: list[str] = []
    for m in motivos:
        if m.startswith("Bitola:"):
            tags.append("bitola")
        elif m.startswith("Marca:"):
            tags.append("marca")
        elif m.startswith("Quantidade:"):
            tags.append("quantidade")
        elif "TIPO DE CIMENTO" in m or "CIMENTO DIVERGENTE" in m:
            tags.append("tipo_cimento")
        elif "FCK" in m:
            tags.append("fck_mpa")
        elif "DIMENS" in m.upper():
            tags.append("dimensoes")
        elif "RESIST" in m.upper():
            tags.append("resistencia_mpa")
        elif "modo_aprendizado" in m.lower():
            tags.append("modo_aprendizado")
    # ordem estável, sem duplicar
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def resumo_contagens(itens_processados: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(itens_processados),
        "verdes": sum(1 for i in itens_processados if i.get("status_item") == StatusConferencia.VERDE.value),
        "amarelos": sum(1 for i in itens_processados if i.get("status_item") == StatusConferencia.AMARELO.value),
        "vermelhos": sum(1 for i in itens_processados if i.get("status_item") == StatusConferencia.VERMELHO.value),
    }


def _atualizar_alerta_por_motivos(alerta_atual: TipoAlerta, motivos: list[str]) -> TipoAlerta:
    tem_marca = _motivos_tem_marca_critica(motivos)
    tem_qtd = _motivos_tem_quantidade_critica(motivos)
    if tem_marca and tem_qtd:
        return _pior_alerta(alerta_atual, TipoAlerta.MISTO)
    if tem_marca:
        return _pior_alerta(alerta_atual, TipoAlerta.MARCA_DIVERGENTE)
    if tem_qtd:
        return _pior_alerta(alerta_atual, TipoAlerta.QUANTIDADE_DIVERGENTE)
    return alerta_atual


@dataclass
class ConfigObraConferente:
    aceita_similar: bool = False
    margem_tolerancia_float: float = 0.02
    modo_aprendizado: bool = True


def quantidade_recebida_em_metros(item_xml: dict[str, Any]) -> float:
    q = float(item_xml["quantidade"])
    unidade = str(item_xml.get("unidade", "KG")).upper()
    bitola = float(item_xml["bitola_mm"])

    if unidade in ("M", "METRO", "METROS", "ML"):
        return q
    if unidade in ("KG", "KILO", "QUILOGRAMA", "QUILOGRAMAS"):
        return converter_para_metros(q, bitola)
    if unidade in ("BARRA", "BARRAS", "UN", "UNID", "UNIDADE"):
        metros_barra = float(item_xml.get("metros_por_barra", 12.0))
        return q * metros_barra
    raise ValueError(f"Unidade não suportada: {unidade}")


def _config_conferente(config_obra: ConfigObraConferente | dict[str, Any]) -> ConfigObraConferente:
    if isinstance(config_obra, ConfigObraConferente):
        return config_obra
    d = dict(config_obra)
    return ConfigObraConferente(
        aceita_similar=bool(d.get("aceita_similar", False)),
        margem_tolerancia_float=float(d.get("margem_tolerancia_float", 0.02)),
        modo_aprendizado=bool(d.get("modo_aprendizado", True)),
    )


def analisar_divergencia_detalhada(
    item_xml: dict[str, Any],
    item_especificado: dict[str, Any],
    config_obra: ConfigObraConferente | dict[str, Any],
    *,
    bitola_ja_casada: bool = False,
) -> dict[str, Any]:
    """
    Analisa o item separando **severidade técnica** de **status operacional**.

    - `status_tecnico`: o que a regra diz, sem nenhum amortecedor. É a verdade
      técnica da divergência e nunca é alterada pelo modo de aprendizado.
    - `status`: o que o sistema mostra hoje, que pode ser rebaixado pelo modo de
      aprendizado (VERMELHO -> AMARELO) enquanto a obra está em implantação.

    Antes, o rebaixamento apagava a severidade: uma divergência de 90% aparecia
    só como "AMARELO / atenção". Com os dois campos, o modo de aprendizado deixa
    de esconder o que o fiscal precisa saber — ele só deixa de bloquear.
    """
    cfg = _config_conferente(config_obra)

    bitola_esp = item_especificado.get("bitola_mm")
    bitola_xml = item_xml.get("bitola_mm")
    marca_esp = _norm_marca(item_especificado.get("marca_exigida"))
    marca_xml = _norm_marca(item_xml.get("marca"))
    q_esp = float(item_especificado.get("qtd_planejada_metros") or 0)

    status = StatusConferencia.VERDE
    motivos: list[str] = []

    if not bitola_ja_casada and bitola_esp is not None and bitola_xml is not None:
        if not _bitolas_equivalentes(float(bitola_esp), float(bitola_xml)):
            status = _pior(status, StatusConferencia.VERMELHO)
            motivos.append(
                f"Bitola: especificado {bitola_esp} mm, NF {bitola_xml} mm (tol. 0,5 mm)."
            )

    if marca_esp and marca_xml and marca_esp != marca_xml:
        if cfg.aceita_similar:
            status = _pior(status, StatusConferencia.AMARELO)
            motivos.append(f"Marca: esperado {marca_esp}, NF {marca_xml} (aceita similar).")
        else:
            status = _pior(status, StatusConferencia.VERMELHO)
            motivos.append(f"Marca: esperado {marca_esp}, NF {marca_xml}.")

    try:
        q_rec = quantidade_recebida_em_metros(item_xml)
    except (ValueError, KeyError, TypeError) as e:
        status = _pior(status, StatusConferencia.AMARELO)
        motivos.append(f"Quantidade: não foi possível normalizar ({e}).")
        q_rec = float(item_xml.get("quantidade", 0))

    if q_esp > 0:
        delta_pct = abs(q_rec - q_esp) / q_esp
        margem = cfg.margem_tolerancia_float
        if delta_pct <= margem:
            pass
        elif delta_pct <= 0.10:
            status = _pior(status, StatusConferencia.AMARELO)
            motivos.append(
                f"Quantidade: divergência {delta_pct * 100:.2f}% (entre {margem * 100:.0f}% e 10%)."
            )
        else:
            status = _pior(status, StatusConferencia.VERMELHO)
            motivos.append(
                f"Quantidade: divergência {delta_pct * 100:.2f}% (>10%). "
                f"Planejado {q_esp:.2f} m, NF ~{q_rec:.2f} m."
            )

    status_tecnico = status
    checkpoint: str | None = None

    if status_tecnico == StatusConferencia.VERMELHO and cfg.modo_aprendizado:
        checkpoint = _mensagem_checkpoint_aprendizado(list(motivos))
        status = StatusConferencia.AMARELO
        motivos.append(
            "modo_aprendizado: status operacional rebaixado de VERMELHO para AMARELO "
            f"(severidade técnica mantida em {status_tecnico.value})."
        )

    if not motivos:
        motivos.append("Dentro dos parâmetros analisados.")

    return {
        "status_tecnico": status_tecnico,
        "status": status,
        "motivos": motivos,
        "checkpoint": checkpoint,
    }


def analisar_divergencia(
    item_xml: dict[str, Any],
    item_especificado: dict[str, Any],
    config_obra: ConfigObraConferente | dict[str, Any],
    *,
    bitola_ja_casada: bool = False,
) -> tuple[StatusConferencia, list[str], str | None]:
    """
    Assinatura histórica mantida: devolve (status operacional, motivos, checkpoint).

    Quem precisa da severidade técnica usa `analisar_divergencia_detalhada`.
    """
    r = analisar_divergencia_detalhada(
        item_xml, item_especificado, config_obra, bitola_ja_casada=bitola_ja_casada
    )
    return r["status"], r["motivos"], r["checkpoint"]


def conferir_nf_multiplos_itens(
    itens_xml: list[dict[str, Any]],
    especificacoes: list[dict[str, Any]],
    config: ConfigObraConferente,
) -> dict[str, Any]:
    """
    Para cada item: detecta categoria (aço / cimento / bloco), encontra linha da especificação
    e aplica o comparador correspondente. Aço continua priorizando bitola.

    Sem correspondência → VERMELHO (material não solicitado / sem linha para a categoria).
    """
    if not itens_xml:
        return {
            "status": StatusConferencia.VERMELHO.value,
            "alerta": TipoAlerta.MATERIAL_NAO_SOLICITADO.value,
            "detalhes": [
                {
                    "item": "—",
                    "esperado": "—",
                    "recebido": "—",
                    "conclusão": "NF sem itens mapeáveis",
                }
            ],
            "motivos": ["NF sem itens para conferência."],
            "modo_aprendizado": config.modo_aprendizado,
            "mensagem_modo_aprendizado": None,
            "can_override": True,
            "itens_processados": [],
            "resumo": {"total": 0, "verdes": 0, "amarelos": 0, "vermelhos": 0},
        }

    if not especificacoes:
        return {
            "status": StatusConferencia.VERMELHO.value,
            "alerta": TipoAlerta.MATERIAL_NAO_SOLICITADO.value,
            "detalhes": [
                {
                    "item": "—",
                    "esperado": "Cadastro de especificações",
                    "recebido": "Itens na NF",
                    "conclusão": "Obra sem especificações cadastradas",
                }
            ],
            "motivos": ["Obra sem especificações cadastradas."],
            "modo_aprendizado": config.modo_aprendizado,
            "mensagem_modo_aprendizado": None,
            "can_override": True,
            "itens_processados": [],
            "resumo": {"total": 0, "verdes": 0, "amarelos": 0, "vermelhos": 0},
        }

    agregado_status = StatusConferencia.VERDE
    # Severidade técnica pura: nunca é rebaixada pelo modo de aprendizado.
    agregado_tecnico = StatusConferencia.VERDE
    alerta_agregado = TipoAlerta.CONFORME
    detalhes: list[dict[str, str]] = []
    motivos_flat: list[str] = []
    checkpoints: list[str] = []
    itens_processados: list[dict[str, Any]] = []

    for idx, item_xml in enumerate(itens_xml):
        item_lo: dict[str, Any] = {**item_xml}
        item_lo.update(extrair_campos_multimaterial(item_lo.get("descricao")))

        rotulo = _rotulo_item_nf(item_lo, idx)
        bitola_nf = item_lo.get("bitola_mm")
        desc_txt = str(item_lo.get("descricao") or "")
        categoria_nf = detectar_categoria_material(desc_txt)
        if categoria_nf == "desconhecido" and bitola_nf:
            categoria_nf = "aco"

        esp: dict[str, Any] | None = None
        if categoria_nf == "aco":
            esp = buscar_especificacao_por_bitola(
                float(bitola_nf) if bitola_nf is not None else None,
                especificacoes,
            )
        elif categoria_nf == "cimento":
            esp = buscar_especificacao_cimento(item_lo, especificacoes)
        elif categoria_nf == "bloco":
            esp = buscar_especificacao_bloco(item_lo, especificacoes)

        if esp is None:
            agregado_status = _pior(agregado_status, StatusConferencia.VERMELHO)
            agregado_tecnico = _pior(agregado_tecnico, StatusConferencia.VERMELHO)
            alerta_agregado = _pior_alerta(alerta_agregado, TipoAlerta.MATERIAL_NAO_SOLICITADO)
            if categoria_nf == "cimento":
                msg = "Material não solicitado para esta obra (cimento sem correspondência na especificação)."
            elif categoria_nf == "bloco":
                msg = "Material não solicitado para esta obra (bloco sem correspondência na especificação)."
            elif categoria_nf == "aco":
                msg = "Material não solicitado para esta obra (bitola sem correspondência na especificação)."
            else:
                msg = "Material não solicitado para esta obra (categoria/atributos não casados com a especificação)."
            motivos_flat.append(f"[{rotulo}] {msg}")
            marca_nf = _norm_marca(item_lo.get("marca")) or "—"
            detalhes.append(
                {
                    "item": rotulo,
                    "esperado": "Linha na especificação (categoria e atributos)",
                    "recebido": f"{_bitola_txt(bitola_nf)} / {marca_nf} / {_trecho_qtd_unidade(item_lo)}",
                    "conclusão": "Material não solicitado para esta obra",
                }
            )
            itens_processados.append(
                {
                    "item_numero": idx + 1,
                    "material_recebido": rotulo,
                    "bitola_recebida": float(bitola_nf) if bitola_nf is not None else None,
                    "marca_recebida": item_lo.get("marca"),
                    "quantidade_recebida": _safe_float_qtd(item_lo.get("quantidade")),
                    "unidade_recebida": str(item_lo.get("unidade_original") or item_lo.get("unidade") or ""),
                    "status_item": StatusConferencia.VERMELHO.value,
                    # Material não solicitado é crítico por definição: não há
                    # amortecedor de modo de aprendizado neste caminho.
                    "severidade_tecnica": StatusConferencia.VERMELHO.value,
                    "divergencias": ["material_nao_especificado"],
                    "mensagem_item": msg,
                    "especificacao_id": None,
                }
            )
            continue

        cat_esp = _categoria_material_esp(esp)
        motivos_item: list[str]
        ckpt: str | None = None

        if cat_esp == "cimento":
            st_s, msg_c = classificar_item_cimento(esp, item_lo)
            st = _status_str_para_enum(st_s)
            st_tecnico = st
            motivos_item = [msg_c]
            st, motivos_item, ckpt = _aplicar_modo_aprendizado_item(st, motivos_item, config)
        elif cat_esp == "bloco":
            st_s, msg_b = classificar_item_bloco(esp, item_lo)
            st = _status_str_para_enum(st_s)
            st_tecnico = st
            motivos_item = [msg_b]
            st, motivos_item, ckpt = _aplicar_modo_aprendizado_item(st, motivos_item, config)
        else:
            detalhe = analisar_divergencia_detalhada(
                item_lo,
                esp,
                config,
                bitola_ja_casada=True,
            )
            st_tecnico = detalhe["status_tecnico"]
            st = detalhe["status"]
            motivos_item = detalhe["motivos"]
            ckpt = detalhe["checkpoint"]

        agregado_status = _pior(agregado_status, st)
        agregado_tecnico = _pior(agregado_tecnico, st_tecnico)
        if ckpt:
            checkpoints.append(ckpt)

        alerta_agregado = _atualizar_alerta_por_motivos(alerta_agregado, motivos_item)

        mat = esp.get("material_tipo") or "Vergalhão"
        bit_esp = esp.get("bitola_mm")
        conclusao = _conclusao_por_status(st)

        marca_r = _norm_marca(item_lo.get("marca")) or "—"
        marca_e = _norm_marca(esp.get("marca_exigida")) or "—"

        if cat_esp in ("cimento", "bloco"):
            a = _attrs_especificacao(esp)
            tipo_e = a.get("tipo") or a.get("dimensoes") or mat
            detalhes.append(
                {
                    "item": rotulo,
                    "esperado": f"{tipo_e} / previsto {esp.get('quantidade_prevista') or esp.get('qtd_planejada_metros') or '—'}",
                    "recebido": f"{item_lo.get('tipo_cimento') or item_lo.get('dimensoes') or '—'} / {_trecho_qtd_unidade(item_lo)}",
                    "conclusão": conclusao,
                }
            )
        else:
            detalhes.append(
                {
                    "item": str(mat),
                    "esperado": f"{bit_esp} mm / {marca_e}",
                    "recebido": f"{_bitola_txt(bitola_nf)} / {marca_r} / {_trecho_qtd_unidade(item_lo)}",
                    "conclusão": conclusao,
                }
            )
        motivos_flat.extend(f"[{rotulo}] {m}" for m in motivos_item)

        divs = divergencias_from_motivos(motivos_item)
        msg_item = next(
            (
                m
                for m in motivos_item
                if not m.startswith("modo_aprendizado") and m != "Dentro dos parâmetros analisados."
            ),
            motivos_item[0] if motivos_item else "OK",
        )
        esp_id = esp.get("id")
        itens_processados.append(
            {
                "item_numero": idx + 1,
                "material_recebido": rotulo,
                "bitola_recebida": float(bitola_nf) if bitola_nf is not None else None,
                "marca_recebida": item_lo.get("marca"),
                "quantidade_recebida": _safe_float_qtd(item_lo.get("quantidade")),
                "unidade_recebida": str(item_lo.get("unidade_original") or item_lo.get("unidade") or ""),
                "status_item": st.value,
                "severidade_tecnica": st_tecnico.value,
                "divergencias": divs,
                "mensagem_item": msg_item[:2000] if msg_item else "",
                "especificacao_id": str(esp_id) if esp_id is not None else None,
            }
        )

    resumo = resumo_contagens(itens_processados)

    if agregado_status == StatusConferencia.VERDE:
        alerta_final = TipoAlerta.CONFORME.value
    elif alerta_agregado == TipoAlerta.MATERIAL_NAO_SOLICITADO:
        alerta_final = TipoAlerta.MATERIAL_NAO_SOLICITADO.value
    elif alerta_agregado == TipoAlerta.MISTO:
        alerta_final = TipoAlerta.MISTO.value
    elif alerta_agregado == TipoAlerta.MARCA_DIVERGENTE:
        alerta_final = TipoAlerta.MARCA_DIVERGENTE.value
    elif alerta_agregado == TipoAlerta.QUANTIDADE_DIVERGENTE:
        alerta_final = TipoAlerta.QUANTIDADE_DIVERGENTE.value
    else:
        alerta_final = TipoAlerta.MISTO.value

    mensagem_aprendizado = "\n\n".join(checkpoints) if checkpoints else None

    return {
        "status": agregado_status.value,
        # O que a auditoria técnica concluiu, independente de modo de aprendizado.
        "severidade_tecnica": agregado_tecnico.value,
        # Decisão que o sistema sugere hoje (pode estar rebaixada pelo aprendizado).
        "decisao_operacional": agregado_status.value,
        "alerta": alerta_final,
        "detalhes": detalhes,
        "motivos": motivos_flat,
        "modo_aprendizado": config.modo_aprendizado,
        "rebaixado_por_aprendizado": (
            agregado_tecnico != agregado_status
        ),
        "mensagem_modo_aprendizado": mensagem_aprendizado,
        # O aceite humano é sempre possível quando há divergência técnica, mesmo
        # que o modo de aprendizado já tenha rebaixado o status operacional.
        "can_override": agregado_tecnico == StatusConferencia.VERMELHO,
        "itens_processados": itens_processados,
        "resumo": resumo,
    }


__all__ = [
    "ChaveNFeInvalidaError",
    "ConfigObraConferente",
    "StatusConferencia",
    "TipoAlerta",
    "analisar_divergencia",
    "buscar_especificacao_bloco",
    "buscar_especificacao_cimento",
    "buscar_especificacao_por_bitola",
    "conferir_nf_multiplos_itens",
    "divergencias_from_motivos",
    "resumo_contagens",
    "converter_para_metros",
    "kg_por_metro_bitola",
    "quantidade_recebida_em_metros",
    "validar_chave",
]
