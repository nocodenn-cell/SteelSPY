"""Pipeline do protótipo: foto → detector → decisão → laudo com marcações.

O laudo é o entregável do experimento: ele diz o que foi contado, com que
confiança, em quanto tempo, com que limitações e — quando o humano discorda —
com a correção registrada ao lado do número da máquina.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from exp_vc01.decisao import decidir, recusar
from exp_vc01.detectores import construir
from exp_vc01.foto import de_bytes
from exp_vc01.laudo import marcar_na_foto, montar_laudo
from exp_vc01.tipos import Limites, Marca

LIMITACOES_GERAIS = (
    "contagem por detector visual: não substitui a conferência humana do recebimento",
    "confiança é heurística de consistência interna, não probabilidade calibrada",
    "nada neste módulo escreve em banco, storage de evidências ou dossiê",
)

_LIMITACOES_POR_DETECTOR = {
    "cv": (
        "linha de base clássica por cor: confunde qualquer laranja oxidado com ponta de barra",
        "sem aprendizado: não separa ponta de vergalhão de escora, andaime ou madeira",
    ),
    "hastes": (
        "linha de base geométrica: mede traço fino, não entende o que é vergalhão",
        "fios, ripas e cabos finos entram na mesma regra de aceitação",
    ),
    "rfdetr": (
        "RF-DETR zero-shot sobre classes COCO: nenhuma classe representa extremidade de vergalhão",
        "sem fine-tune, a contagem não tem como estar certa — serve para medir custo e recusa",
    ),
}


def _ler(fonte: str | Path | bytes) -> tuple[bytes | None, str]:
    if isinstance(fonte, bytes):
        return fonte, "upload"
    caminho = Path(str(fonte))
    return (caminho.read_bytes(), str(caminho)) if caminho.is_file() else (None, str(caminho))


def contar(
    fonte: str | Path | bytes,
    *,
    detector: str = "cv",
    limites: Limites | None = None,
    opcoes_detector: dict[str, Any] | None = None,
    mime: str | None = None,
    detector_obj: Any = None,
) -> dict[str, Any]:
    """Conta extremidades visíveis em uma fotografia e devolve o laudo.

    `detector_obj` permite reusar um modelo já carregado — carregar pesos a cada
    foto custaria mais que a inferência em lote.
    """
    polit = limites or Limites()
    dados, origem = _ler(fonte)

    if dados is None:
        return montar_laudo(
            {"origem": origem}, None, recusar("arquivo de fotografia não encontrado"), polit, LIMITACOES_GERAIS
        )

    try:
        fotografia = de_bytes(dados, mime, origem=origem)
    except Exception as exc:  # noqa: BLE001 - recusa explícita, não traceback
        return montar_laudo(
            {"origem": origem},
            None,
            recusar(f"fotografia recusada pela validação de evidência: {exc}"),
            polit,
            LIMITACOES_GERAIS,
        )

    try:
        motor = detector_obj if detector_obj is not None else construir(detector, **(opcoes_detector or {}))
        resultado = motor.detectar(fotografia)
    except Exception as exc:  # noqa: BLE001 - detector ausente ou quebrado vira recusa
        return montar_laudo(
            fotografia,
            None,
            recusar(f"detector {detector!r} não produziu resultado: {type(exc).__name__}: {exc}"),
            polit,
            LIMITACOES_GERAIS,
        )

    decisao = decidir(resultado, polit)
    limitacoes = LIMITACOES_GERAIS + _LIMITACOES_POR_DETECTOR.get(detector, ())
    laudo = montar_laudo(fotografia, resultado, decisao, polit, limitacoes)
    laudo["_fotografia_bytes"] = fotografia.normalizada
    return laudo


def gravar_saida(laudo: dict[str, Any], destino: str | Path) -> dict[str, Any]:
    """Grava `laudo.json` e a foto com as marcações numeradas; devolve os caminhos."""
    p = Path(destino)
    p.mkdir(parents=True, exist_ok=True)
    fotografia = laudo.pop("_fotografia_bytes", None)
    marcas = tuple(
        Marca(numero=m["numero"], x=m["x"], y=m["y"], familia=m["familia"], forca=m["forca"])
        for m in laudo.get("marcas", [])
    )
    saida: dict[str, Any] = {"laudo": str(_gravar_json(laudo, p / "laudo.json"))}
    if fotografia and marcas:
        caminho = p / "foto_marcada.jpg"
        caminho.write_bytes(marcar_na_foto(fotografia, marcas))
        saida["foto_marcada"] = str(caminho)
        saida["marcações"] = len(marcas)
    return saida


def _gravar_json(laudo: dict[str, Any], caminho: Path) -> Path:
    import json

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(laudo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return caminho
