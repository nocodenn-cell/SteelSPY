"""Tipos do protótipo de contagem.

Nada aqui importa biblioteca de visão computacional: os tipos atravessam a
fronteira entre o detector (que pode exigir `cv2`/`torch`) e a decisão, o laudo e
a avaliação, que rodam no Python da aplicação. É o que permite testar a política
de recusa sem instalar o stack de inferência.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONTADO = "CONTADO"
INCONCLUSIVO = "INCONCLUSIVO"
RECUSADO = "RECUSADO"


@dataclass(frozen=True)
class Marca:
    """Uma extremidade visível detectada, com o número que sai desenhado na foto."""

    numero: int
    x: int
    y: int
    familia: str
    forca: float


@dataclass(frozen=True)
class ResultadoDetector:
    """O que o detector encontrou — sem juízo de valor sobre servir ou não.

    `instabilidade` é a divergência entre as varreduras independentes (0 = todas
    as linhas concordaram). `nota` é texto do detector para o laudo: modelo,
    limiar, o que ele de fato contou.
    """

    detector: str
    alvo: str
    marcas: tuple[Marca, ...]
    confianca: float
    instabilidade: float
    nota: str
    latencia_ms: dict[str, int] = field(default_factory=dict)
    dimensoes: tuple[int, int] = (0, 0)

    @property
    def contagem(self) -> int:
        return len(self.marcas)


@dataclass(frozen=True)
class Limites:
    """Política de recusa. Os padrões vêm de calibração na divisão de validação.

    `maximo` é o teto físico plausível para um feixe de vergalhões recebido em
    obra; acima disso a imagem não é um feixe conto, é outra coisa, e dizer
    "200 barras" seria uma invenção.
    """

    minimo: int = 1
    maximo: int = 120
    confianca_minima: float = 0.55
    instabilidade_maxima: float = 0.35

    def a_dicionario(self) -> dict[str, Any]:
        return {
            "minimo": self.minimo,
            "maximo": self.maximo,
            "confianca_minima": self.confianca_minima,
            "instabilidade_maxima": self.instabilidade_maxima,
        }


@dataclass(frozen=True)
class Decisao:
    veredito: str
    motivos: tuple[str, ...]
    contagem: int
