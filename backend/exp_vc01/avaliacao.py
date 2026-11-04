"""Avaliação contra contagens humanas conhecidas (Etapa 4).

O ground truth é a contagem de `<object>` no XML Pascal VOC do dataset: cada caixa
é uma extremidade que um humano marcou. Nada aqui usa número simulado — se o
detector erra, o erro aparece.

A separação de divisões é código, não intenção: `calibrar` recusa a divisão de
teste e `avaliar` recusa qualquer outra, porque a métrica que se apresenta como
resultado só tem valor se os limiares não foram ajustados nela mesma.
"""

from __future__ import annotations

import math
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from exp_vc01.tipos import CONTADO

DIVISOES = ("Training", "Validation", "Test")
DIVISOES_DE_CALIBRACAO = frozenset({"Training", "Validation"})
DIVISAO_DE_AVALIACAO = "Test"


class VazamentoDeDivisao(RuntimeError):
    """Alguém tentou calibrar no teste, ou avaliar fora do teste."""


def contar_ground_truth(caminho_xml: Path) -> int:
    return len(ET.parse(caminho_xml).getroot().findall("object"))


def amostra_da_divisao(
    pasta: Path, limite: int | None = None, excluir: set[str] | None = None
) -> list[tuple[Path, Path]]:
    """Pares (imagem, xml) de uma divisão, ordenados por nome para ser reproduzível."""
    pares = [
        (jpg, jpg.with_suffix(".xml"))
        for jpg in sorted(pasta.glob("*.jpg"))
        if jpg.with_suffix(".xml").is_file()
        and not jpg.name.startswith("gt_sobreposta")
        and jpg.name not in (excluir or set())
    ]
    return pares[:limite] if limite else pares


def mapear_duplicatas(pasta_dados: Path) -> dict[str, set[str]]:
    """Nomes, por divisão, de imagens byte-idênticas a alguma de outra divisão.

    O conjunto publicado tem 29 imagens do teste repetidas no treino (o artigo
    original declara teste com 146 imagens; a pasta traz 175). Deixar isso
    dentro da métrica inflaria o resultado, então a avaliação exclui.
    """
    import hashlib

    por_hash: dict[str, dict[str, str]] = {}
    for divisao in DIVISOES:
        for jpg in sorted((pasta_dados / divisao).glob("*.jpg")):
            if jpg.name.startswith("gt_sobreposta"):
                continue
            resumo = hashlib.sha256(jpg.read_bytes()).hexdigest()
            por_hash.setdefault(resumo, {})[divisao] = jpg.name

    duplicadas: dict[str, set[str]] = {}
    for mapa in por_hash.values():
        if len(mapa) > 1:
            for divisao, nome in mapa.items():
                duplicadas.setdefault(divisao, set()).add(nome)
    return duplicadas


def garantir_disjuntas(
    pasta_dados: Path, *, excluir: dict[str, set[str]] | None = None
) -> dict[str, int]:
    """Confirma que nenhuma imagem aparece em duas divisões (hash do arquivo).

    `excluir` são os nomes descartados por divisão — as imagens contaminadas que
    `mapear_duplicatas` encontrou. Retorna o total por divisão já descontando-as.
    Levanta se duas imagens *mantidas* forem idênticas: aí a métrica não vale.
    """
    import hashlib

    vistos: dict[str, str] = {}
    totais: dict[str, int] = {}
    for divisao in DIVISOES:
        pasta = pasta_dados / divisao
        if not pasta.is_dir():
            raise FileNotFoundError(f"divisão {divisao} ausente em {pasta_dados}")
        descartar = (excluir or {}).get(divisao, set())
        contagem = 0
        for jpg in sorted(pasta.glob("*.jpg")):
            if jpg.name.startswith("gt_sobreposta") or jpg.name in descartar:
                continue
            resumo = hashlib.sha256(jpg.read_bytes()).hexdigest()
            if resumo in vistos and vistos[resumo] != divisao:
                raise VazamentoDeDivisao(
                    f"{jpg.name} também está em {vistos[resumo]}: as divisões não são independentes"
                )
            vistos[resumo] = divisao
            contagem += 1
        totais[divisao] = contagem
    return totais


def _percentual(partes: int, total: int) -> float:
    return round(100.0 * partes / total, 2) if total else 0.0


def metricas(registros: list[dict[str, Any]]) -> dict[str, Any]:
    """Métricas da Etapa 4 sobre os laudos já produzidos.

    Assumido (asserted) = laudo com veredito CONTADO. Recusado/inconclusivo não
    entra na acerto-percentual: o protótipo se calou, e isso é medido à parte
    como taxa de rejeição.
    """
    assumidos = [r for r in registros if r.get("veredito") == CONTADO]
    calados = [r for r in registros if r.get("veredito") != CONTADO]
    desvios = [int(r["contagem"]) - int(r["ground_truth"]) for r in assumidos]
    absolutos = [abs(d) for d in desvios]
    percentuais = [abs(d) / int(r["ground_truth"]) * 100.0 for r, d in zip(assumidos, desvios, strict=True) if int(r["ground_truth"]) > 0]
    latencias = [int(r.get("latencia_ms") or 0) for r in registros]

    exatos = sum(1 for d in desvios if d == 0)
    erros_nao_sinalizados = sum(1 for d in desvios if d != 0)

    def _p(q: float) -> int:
        if not latencias:
            return 0
        ordenado = sorted(latencias)
        # nearest-rank: p95 de 4 amostras é a maior, não a terceira.
        indice = max(0, min(len(ordenado) - 1, math.ceil(q * len(ordenado)) - 1))
        return ordenado[indice]

    return {
        "fotografias": len(registros),
        "assumidas": len(assumidos),
        "caladas": len(calados),
        "taxa_rejeicao_pct": _percentual(len(calados), len(registros)),
        "contagens_exatas": exatos,
        "taxa_exatas_pct": _percentual(exatos, len(assumidos)),
        "erro_absoluto_medio": round(statistics.fmean(absolutos), 3) if absolutos else None,
        "erro_absoluto_maximo": max(absolutos) if absolutos else None,
        "erro_percentual_medio": round(statistics.fmean(percentuais), 2) if percentuais else None,
        "subcontagens": sum(1 for d in desvios if d < 0),
        "supercontagens": sum(1 for d in desvios if d > 0),
        "subcontagens_pct": _percentual(sum(1 for d in desvios if d < 0), len(assumidos)),
        "supercontagens_pct": _percentual(sum(1 for d in desvios if d > 0), len(assumidos)),
        "erros_nao_sinalizados": erros_nao_sinalizados,
        "erros_nao_sinalizados_pct": _percentual(erros_nao_sinalizados, len(assumidos)),
        "latencia_ms": {"p50": _p(0.50), "p95": _p(0.95), "max": max(latencias) if latencias else 0},
        "ground_truth_medio": round(statistics.fmean([int(r["ground_truth"]) for r in registros]), 2) if registros else None,
    }


def registrar(laudo: dict[str, Any], nome: str, ground_truth: int) -> dict[str, Any]:
    detector = laudo.get("detector") or {}
    correcao = laudo.get("correcao_humana")
    return {
        "nome": nome,
        "veredito": laudo.get("veredito"),
        "contagem": laudo.get("contagem_maquina"),
        "ground_truth": ground_truth,
        "confianca": detector.get("confianca"),
        "latencia_ms": (detector.get("latencia_ms") or {}).get("total"),
        "motivos": laudo.get("motivos"),
        "corrigida_por_humano": bool(correcao),
    }


def validar_uso(split: str, *, para: str) -> None:
    if para == "calibracao" and split not in DIVISOES_DE_CALIBRACAO:
        raise VazamentoDeDivisao(f"calibração não pode usar a divisão {split!r}; use Validation ou Training")
    if para == "avaliacao" and split != DIVISAO_DE_AVALIACAO:
        raise VazamentoDeDivisao(f"avaliação de resultado só vale na divisão {DIVISAO_DE_AVALIACAO!r}, não {split!r}")
