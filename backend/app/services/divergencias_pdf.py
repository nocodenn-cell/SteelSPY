"""
PDF técnico: divergências por linha (nfe_itens), para auditoria detalhada.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fpdf import FPDF

FONT_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"

def _negrito(font: str) -> str:
    """DejaVu tem um único TTF (regular). Negrito vira regular, sem fingir um estilo B."""
    return "" if font == "DejaVu" else "B"

EMISSOR_PADRAO = os.getenv("LAUDO_EMISSOR_NOME", "CheckObra AI")


def _fmt_div(div: Any) -> str:
    if div is None:
        return "—"
    if isinstance(div, str):
        return div[:800]
    try:
        return json.dumps(div, ensure_ascii=False)[:1200]
    except (TypeError, ValueError):
        return str(div)[:800]


def gerar_divergencias_pdf_bytes(
    *,
    obra_nome: str,
    chave_acesso: str,
    nfe_log_id: str,
    status_nf: str,
    linhas: list[dict[str, Any]],
) -> bytes:
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    if FONT_PATH.is_file():
        pdf.add_font("DejaVu", "", str(FONT_PATH))
        font = "DejaVu"
    else:
        font = "helvetica"

    pdf.set_font(font, _negrito(font), 13)
    pdf.multi_cell(0, 7, "RELATÓRIO DE DIVERGÊNCIAS POR ITEM", align="C")
    pdf.ln(1)
    pdf.set_font(font, "", 9)
    pdf.cell(0, 5, f"Obra: {obra_nome}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "", 7)
    chave_linha = f"Chave NFe: {chave_acesso}"
    for i in range(0, len(chave_linha), 96):
        pdf.cell(0, 4, chave_linha[i : i + 96], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "", 9)
    pdf.cell(
        0,
        5,
        f"ID conferencia: {nfe_log_id}  |  Status NF: {status_nf}  |  {EMISSOR_PADRAO}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(3)

    if not linhas:
        pdf.set_font(font, "", 9)
        pdf.multi_cell(0, 5, "Nenhum item persistido para esta NF.")
    else:
        pdf.set_font(font, _negrito(font), 10)
        pdf.cell(0, 6, "Detalhamento por linha", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        for row in linhas:
            num = row.get("item_numero", "—")
            st = row.get("status_item", "—")
            pdf.set_font(font, _negrito(font), 8)
            pdf.set_fill_color(241, 245, 249)
            pdf.cell(0, 6, f" Item {num} — {st}", new_x="LMARGIN", new_y="NEXT", fill=True)
            pdf.set_font(font, "", 7)
            linha1 = (
                f"Bitola: {row.get('bitola_recebida', '—')} mm   |   Marca: {row.get('marca_recebida', '—')}   |   "
                f"Qtd: {row.get('quantidade_recebida', '—')} {row.get('unidade_recebida', '')}"
            )
            pdf.multi_cell(0, 4, linha1)
            pdf.set_font(font, _negrito(font), 7)
            pdf.cell(0, 4, "Divergências (sistema):", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(font, "", 7)
            pdf.multi_cell(0, 4, _fmt_div(row.get("divergencias")))
            msg = str(row.get("mensagem_item") or "").strip()
            if msg:
                pdf.set_font(font, _negrito(font), 7)
                pdf.cell(0, 4, "Mensagem:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 7)
                pdf.multi_cell(0, 4, msg[:2000])
            pdf.ln(2)

    pdf.ln(3)
    pdf.set_font(font, "", 7)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0,
        4,
        "Fonte: tabela nfe_itens. Quantidades conforme normalização na conferência (kg→m quando aplicável no motor, "
        "valores aqui são os persistidos na NF).",
    )

    out = pdf.output()
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")


def nome_arquivo_divergencias(nfe_log_id: str) -> str:
    lid = str(nfe_log_id).replace("-", "")[:8]
    return f"divergencias_itens_{lid}.pdf"
