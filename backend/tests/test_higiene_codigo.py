"""Guardas de higiene (B7, B8, B10): APIs descontinuadas e chaves inconsistentes não voltam.

São verificações estáticas porque os defeitos são de forma do código, não de saída:
- B7: datetime.utcnow() está deprecado desde Python 3.12 e produz datetime sem fuso.
- B8: fpdf2 2.x deprecou cell(ln=...), output(dest=...) e add_font com estilo 'B'
      sobre o mesmo TTF (negrito falso, que o viewer não sabe que é falso).
- B10: a chave de conclusão é ASCII ("conclusao"); "conclusão" só existe como alias de leitura.
"""

from __future__ import annotations

import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
ARQUIVOS_PDF = [
    APP / "services" / "laudo_pdf.py",
    APP / "services" / "dossie_pdf.py",
    APP / "services" / "divergencias_pdf.py",
]


def _linhas_com(arquivos, padrao: str) -> list[str]:
    rx = re.compile(padrao)
    achados = []
    for arq in arquivos:
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(linha):
                achados.append(f"{arq.relative_to(RAIZ)}:{n}: {linha.strip()}")
    return achados


def test_b7_sem_datetime_utcnow_no_app() -> None:
    achados = _linhas_com(list(APP.rglob("*.py")), r"utcnow\(")
    assert achados == []


@pytest.mark.parametrize("padrao", [r"\bln\s*=", r"\bdest\s*="])
def test_b8_sem_parametros_deprecados_do_fpdf2(padrao: str) -> None:
    assert _linhas_com(ARQUIVOS_PDF, padrao) == []


def test_b8_sem_negrito_falso_por_add_font() -> None:
    assert _linhas_com(ARQUIVOS_PDF, r'add_font\([^)]*,\s*"B"') == []


def test_b10_chave_de_conclusao_e_ascii_no_dominio() -> None:
    assert _linhas_com([APP / "domain" / "conferente.py"], r'"conclusão"') == []
