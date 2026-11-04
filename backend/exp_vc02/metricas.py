"""Avaliação de detecções COCO — o mesmo contrato para qualquer modelo.

A Sprint 5 pode trocar o detector; o que não pode mudar é como o resultado é
medido. Duas perguntas separadas:

* **Qualidade da curva** — AP por classe e mAP@[.5:.95], sem escolher limiar;
* **Ponto de operação** — precisão/recall/F1 com um limiar explícito, que é o
  que o portão do recebimento usaria.

Além das métricas, existe um portão de **validação humana**: nenhum modelo é
aprovado sem amostra revisada por pessoa. O campo é lido das predições
(`validacao_humana`), não inferido.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

IOU_PADRAO = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))


class ErroAvaliacao(ValueError):
    """A entrada não permite uma avaliação honesta."""


def _carregar(caminho: str | Path) -> dict[str, Any]:
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ErroAvaliacao(f"arquivo ausente: {caminho}") from exc
    except json.JSONDecodeError as exc:
        raise ErroAvaliacao(f"JSON inválido em {caminho}: {exc}") from exc
    if not isinstance(dados, dict):
        raise ErroAvaliacao(f"{caminho} precisa conter um objeto JSON")
    return dados


def iou(caixa_a: list[float], caixa_b: list[float]) -> float:
    """IoU de duas caixas [x, y, largura, altura]."""
    ax, ay, aw, ah = (float(v) for v in caixa_a)
    bx, by, bw, bh = (float(v) for v in caixa_b)
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersecao = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    uniao = aw * ah + bw * bh - intersecao
    return intersecao / uniao if uniao > 0 else 0.0


def _validar_entrada(verdade: dict[str, Any], predicoes: dict[str, Any]) -> tuple[dict[int, str], set[int], dict[int, list[dict[str, Any]]]]:
    categorias = verdade.get("categories")
    if not isinstance(categorias, list) or not categorias:
        raise ErroAvaliacao("verdade.categories ausente ou vazia")
    nomes: dict[int, str] = {}
    for categoria in categorias:
        if not isinstance(categoria, dict) or not isinstance(categoria.get("id"), int):
            raise ErroAvaliacao(f"categoria inválida: {categoria!r}")
        nomes[categoria["id"]] = str(categoria.get("name") or categoria["id"])

    imagens = verdade.get("images")
    if not isinstance(imagens, list) or not imagens:
        raise ErroAvaliacao("verdade.images ausente ou vazia")
    ids_imagens: set[int] = set()
    for imagem in imagens:
        if not isinstance(imagem, dict) or not isinstance(imagem.get("id"), int):
            raise ErroAvaliacao(f"imagem inválida: {imagem!r}")
        ids_imagens.add(imagem["id"])

    anotacoes_gt = verdade.get("annotations")
    preds = predicoes.get("annotations")
    if not isinstance(anotacoes_gt, list) or not isinstance(preds, list):
        raise ErroAvaliacao("annotations precisa ser lista na verdade e nas predições")

    for anotacao in anotacoes_gt:
        if not isinstance(anotacao, dict) or anotacao.get("image_id") not in ids_imagens:
            raise ErroAvaliacao(f"verdade com image_id desconhecido: {anotacao!r}")
        if anotacao.get("category_id") not in nomes:
            raise ErroAvaliacao(f"verdade com category_id desconhecido: {anotacao!r}")
        if "score" in anotacao:
            raise ErroAvaliacao("verdade não pode ter score")

    por_imagem: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for predicao in preds:
        if not isinstance(predicao, dict):
            raise ErroAvaliacao(f"predição inválida: {predicao!r}")
        if predicao.get("image_id") not in ids_imagens:
            raise ErroAvaliacao(
                f"predição para imagem fora da verdade (image_id={predicao.get('image_id')!r})"
            )
        if predicao.get("category_id") not in nomes:
            raise ErroAvaliacao(
                f"predição com category_id desconhecido: {predicao.get('category_id')!r}"
            )
        score = predicao.get("score")
        if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
            raise ErroAvaliacao(f"score inválido na predição: {score!r}")
        caixa = predicao.get("bbox")
        if not isinstance(caixa, list) or len(caixa) != 4 or not all(isinstance(v, (int, float)) for v in caixa):
            raise ErroAvaliacao(f"bbox inválida na predição: {caixa!r}")
        por_imagem[predicao["image_id"]].append(predicao)

    return nomes, ids_imagens, por_imagem


def _parear(
    gt: list[dict[str, Any]], preds: list[dict[str, Any]], iou_min: float
) -> tuple[list[tuple[float, int]], int]:
    """Casa predições com GT por score decrescente. Devolve [(score, tp)] e FN."""
    usados = [False] * len(gt)
    pares: list[tuple[float, int]] = []
    for predicao in sorted(preds, key=lambda p: float(p["score"]), reverse=True):
        melhor, melhor_iou = -1, iou_min
        for indice, alvo in enumerate(gt):
            if usados[indice]:
                continue
            valor = iou(predicao["bbox"], alvo["bbox"])
            if valor >= melhor_iou:
                melhor, melhor_iou = indice, valor
        if melhor >= 0:
            usados[melhor] = True
            pares.append((float(predicao["score"]), 1))
        else:
            pares.append((float(predicao["score"]), 0))
    return pares, usados.count(False)


def _ap_101(recalls: list[float], precisoes: list[float]) -> float:
    """AP pela interpolação de 101 pontos (mesmo critério do COCO)."""
    if not recalls:
        return 0.0
    precisao_max = list(precisoes)
    for indice in range(len(precisao_max) - 2, -1, -1):
        precisao_max[indice] = max(precisao_max[indice], precisao_max[indice + 1])
    total = 0.0
    for passo in range(101):
        alvo = passo / 100.0
        valor = 0.0
        for recall, precisao in zip(recalls, precisao_max, strict=True):
            if recall >= alvo:
                valor = precisao
                break
        total += valor
    return total / 101.0


def _ap_categoria(
    gt_por_imagem: dict[int, list[dict[str, Any]]],
    preds_por_imagem: dict[int, list[dict[str, Any]]],
    imagens: set[int],
    categoria_id: int,
    iou_min: float,
) -> float | None:
    total_gt = sum(
        1 for imagem in imagens for alvo in gt_por_imagem.get(imagem, []) if alvo["category_id"] == categoria_id
    )
    if total_gt == 0:
        return None

    pontos: list[tuple[float, int]] = []
    for imagem in imagens:
        gt = [a for a in gt_por_imagem.get(imagem, []) if a["category_id"] == categoria_id]
        preds = [p for p in preds_por_imagem.get(imagem, []) if p["category_id"] == categoria_id]
        if not gt and not preds:
            continue
        pares, _ = _parear(gt, preds, iou_min)
        pontos.extend(pares)

    pontos.sort(key=lambda par: par[0], reverse=True)
    tp = fp = 0
    recalls: list[float] = []
    precisoes: list[float] = []
    for _, acerto in pontos:
        tp += acerto
        fp += 1 - acerto
        recalls.append(tp / total_gt)
        precisoes.append(tp / (tp + fp))
    return _ap_101(recalls, precisoes)


def _operacao_categoria(
    gt_por_imagem: dict[int, list[dict[str, Any]]],
    preds_por_imagem: dict[int, list[dict[str, Any]]],
    imagens: set[int],
    categoria_id: int,
    iou_min: float,
    confianca_minima: float,
) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for imagem in imagens:
        gt = [a for a in gt_por_imagem.get(imagem, []) if a["category_id"] == categoria_id]
        preds = [
            p
            for p in preds_por_imagem.get(imagem, [])
            if p["category_id"] == categoria_id and float(p["score"]) >= confianca_minima
        ]
        if not gt and not preds:
            continue
        pares, faltantes = _parear(gt, preds, iou_min)
        tp += sum(acerto for _, acerto in pares)
        fp += sum(1 - acerto for _, acerto in pares)
        fn += faltantes
    return tp, fp, fn


def _taxa(numerador: int, denominador: int) -> float | None:
    return numerador / denominador if denominador else None


def _arredondar(valor: float | None) -> float | None:
    return round(valor, 4) if valor is not None else None


def avaliar(
    verdade: dict[str, Any],
    predicoes: dict[str, Any],
    *,
    confianca_minima: float = 0.5,
    min_map50: float | None = None,
    min_precisao: float | None = None,
    min_recall: float | None = None,
    exigir_validacao_humana: bool = False,
    min_amostras_humanas: int = 100,
    ious: tuple[float, ...] = IOU_PADRAO,
) -> dict[str, Any]:
    nomes, ids_imagens, preds_por_imagem = _validar_entrada(verdade, predicoes)
    gt_por_imagem: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for anotacao in verdade["annotations"]:
        gt_por_imagem[anotacao["image_id"]].append(anotacao)

    ids_categorias = sorted(nomes)
    ap_por_limiar: dict[float, dict[int, float | None]] = {}
    for iou_min in ious:
        ap_por_limiar[iou_min] = {
            categoria: _ap_categoria(gt_por_imagem, preds_por_imagem, ids_imagens, categoria, iou_min)
            for categoria in ids_categorias
        }

    def _media(valores: list[float | None]) -> float | None:
        validos = [v for v in valores if v is not None]
        return sum(validos) / len(validos) if validos else None

    mapas = {limiar: _media(list(aps.values())) for limiar, aps in ap_por_limiar.items()}
    map50 = mapas.get(0.5)
    map75 = mapas.get(0.75)
    map50_95 = _media(list(mapas.values()))

    categorias: dict[str, Any] = {}
    tp_total = fp_total = fn_total = 0
    for categoria in ids_categorias:
        tp, fp, fn = _operacao_categoria(
            gt_por_imagem, preds_por_imagem, ids_imagens, categoria, 0.5, confianca_minima
        )
        tp_total += tp
        fp_total += fp
        fn_total += fn
        precisao = _taxa(tp, tp + fp)
        recall = _taxa(tp, tp + fn)
        categorias[nomes[categoria]] = {
            "gt": sum(
                1 for imagem in ids_imagens for a in gt_por_imagem.get(imagem, []) if a["category_id"] == categoria
            ),
            "predicoes": sum(
                1
                for imagem in ids_imagens
                for p in preds_por_imagem.get(imagem, [])
                if p["category_id"] == categoria and float(p["score"]) >= confianca_minima
            ),
            "ap50": _arredondar(ap_por_limiar[0.5][categoria]) if 0.5 in ap_por_limiar else None,
            "ap75": _arredondar(ap_por_limiar[0.75][categoria]) if 0.75 in ap_por_limiar else None,
            "ap50_95": _arredondar(_media([ap_por_limiar[limiar][categoria] for limiar in ious])),
            "precisao": _arredondar(precisao),
            "recall": _arredondar(recall),
            "f1": _arredondar(2 * precisao * recall / (precisao + recall)) if precisao is not None and recall is not None and (precisao + recall) > 0 else None,
        }

    precisao = _taxa(tp_total, tp_total + fp_total)
    recall = _taxa(tp_total, tp_total + fn_total)
    f1 = 2 * precisao * recall / (precisao + recall) if precisao is not None and recall is not None and (precisao + recall) > 0 else None

    validacao = predicoes.get("validacao_humana") or {}
    humano_ok = (
        isinstance(validacao, dict)
        and validacao.get("aprovado") is True
        and isinstance(validacao.get("amostras"), int)
        and validacao["amostras"] >= min_amostras_humanas
    )

    reprovacoes: list[str] = []
    if min_map50 is not None and (map50 is None or map50 < min_map50):
        reprovacoes.append(f"mAP@0.5 {_arredondar(map50)} < mínimo {min_map50}")
    if min_precisao is not None and (precisao is None or precisao < min_precisao):
        reprovacoes.append(f"precisão {_arredondar(precisao)} < mínimo {min_precisao}")
    if min_recall is not None and (recall is None or recall < min_recall):
        reprovacoes.append(f"recall {_arredondar(recall)} < mínimo {min_recall}")
    if exigir_validacao_humana and not humano_ok:
        reprovacoes.append(
            "validação humana ausente ou insuficiente "
            f"(aprovado={validacao.get('aprovado') if isinstance(validacao, dict) else None}, "
            f"amostras={validacao.get('amostras') if isinstance(validacao, dict) else None}, "
            f"mínimo={min_amostras_humanas})"
        )

    return {
        "aprovado": not reprovacoes,
        "reprovacoes": reprovacoes,
        "confianca_minima": confianca_minima,
        "imagens_verdade": len(ids_imagens),
        "imagens_com_predicao": len([i for i in ids_imagens if preds_por_imagem.get(i)]),
        "gt": {"verdadeiros_positivos": tp_total, "falsos_positivos": fp_total, "falsos_negativos": fn_total},
        "map50": _arredondar(map50),
        "map75": _arredondar(map75),
        "map50_95": _arredondar(map50_95),
        "precisao": _arredondar(precisao),
        "recall": _arredondar(recall),
        "f1": _arredondar(f1),
        "categorias": categorias,
        "validacao_humana": {
            "exigida": exigir_validacao_humana,
            "aprovada": humano_ok,
            "minimo_amostras": min_amostras_humanas,
        },
        "limiares_iou": list(ious),
    }


def avaliar_arquivos(
    verdade_path: str | Path,
    predicoes_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    return avaliar(_carregar(verdade_path), _carregar(predicoes_path), **kwargs)
