"""Marcações numeradas na foto e laudo do experimento.

O desenho é feito com Pillow — dependência que a aplicação já tem — e não com
OpenCV: assim a saída visual do protótipo é gerável e testável sem o stack de
inferência, e a única coisa que exige `cv2`/`torch` fica restrita ao detector.

A correção humana não apaga o número da máquina. Os dois ficam no laudo, com o
delta entre eles, porque a diferença entre o que o modelo contou e o que o
humano confirmou é exatamente o dado que a Sprint VC-01 veio medir.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from exp_vc01.tipos import Decisao, Limites, Marca, ResultadoDetector

PROTOCOLO = "vc01-contagem/1"
_CORES = {"a": (0, 200, 255), "b": (255, 120, 0)}


def _fonte(tamanho: int) -> Any:
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:  # Pillow < 10.1 não aceita tamanho na fonte padrão
        return ImageFont.load_default()


def marcar_na_foto(fotografia: bytes, marcas: tuple[Marca, ...], lado_marcador: int = 26) -> bytes:
    img = Image.open(io.BytesIO(fotografia)).convert("RGB")
    draw = ImageDraw.Draw(img)
    raio = max(6, lado_marcador // 2)
    for m in marcas:
        cor = _CORES.get(m.familia, (0, 255, 120))
        draw.ellipse((m.x - raio, m.y - raio, m.x + raio, m.y + raio), outline=cor, width=3)
        texto = str(m.numero)
        largura_texto = max(1, 9 * len(texto))
        draw.text(
            (m.x - largura_texto // 2, m.y - 6),
            texto,
            fill=(255, 255, 255),
            font=_fonte(16),
        )
    saida = io.BytesIO()
    img.save(saida, format="JPEG", quality=88, optimize=True)
    return saida.getvalue()


def montar_laudo(
    fotografia: Any,
    resultado: ResultadoDetector | None,
    decisao: Decisao,
    limites: Limites,
    limitacoes: tuple[str, ...],
    *,
    criado_em: datetime | None = None,
) -> dict[str, Any]:
    agora = criado_em or datetime.now(timezone.utc)
    laudo: dict[str, Any] = {
        "protocolo": PROTOCOLO,
        "criado_em": agora.isoformat(),
        "fotografia": fotografia.cabecalho() if hasattr(fotografia, "cabecalho") else dict(fotografia),
        "veredito": decisao.veredito,
        "contagem_maquina": decisao.contagem,
        "motivos": list(decisao.motivos),
        "limitacoes": list(limitacoes),
        "politica": limites.a_dicionario(),
        "correcao_humana": None,
    }
    if resultado is not None:
        laudo["detector"] = {
            "nome": resultado.detector,
            "alvo": resultado.alvo,
            "nota": resultado.nota,
            "confianca": round(resultado.confianca, 4),
            "instabilidade": round(resultado.instabilidade, 4),
            "dimensoes": list(resultado.dimensoes),
            "latencia_ms": resultado.latencia_ms,
        }
        laudo["marcas"] = [
            {"numero": m.numero, "x": m.x, "y": m.y, "familia": m.familia, "forca": round(m.forca, 3)}
            for m in resultado.marcas
        ]
    return laudo


def aplicar_correcao(laudo: dict[str, Any], *, contagem_humana: int, quem: str, motivo: str) -> dict[str, Any]:
    """Registra a decisão humana sem descartar a leitura da máquina."""
    maquina = int(laudo.get("contagem_maquina") or 0)
    laudo["correcao_humana"] = {
        "contagem": contagem_humana,
        "quem": quem,
        "motivo": motivo,
        "em": datetime.now(timezone.utc).isoformat(),
        "delta": contagem_humana - maquina,
        "veredito_final": "CONTADO",
    }
    return laudo


def gravar(laudo: dict[str, Any], caminho: str | Path) -> Path:
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(laudo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return p
