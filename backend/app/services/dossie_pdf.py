"""Dossiê de recebimento em PDF.

Herda a mecânica do laudo (fpdf2 + DejaVu, A4, sem rede) e muda só o conteúdo:
o laudo fala de uma nota, o dossiê fala de um pedido — o compromisso, a cobrança,
o físico, as divergências, quem decidiu e a prova fotográfica com hash.

O documento é factual. Ele lista o que o sistema registrou; não afirma que o
material é conforme, nem substitui parecer de responsável técnico.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fpdf import FPDF

FONT_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"

# Larguras que somam a área útil do A4 com as margens do FPDF (210 - 2*15 = 180mm).
_W_TOTAL = 180


def _fmt_data(valor: str | None) -> str:
    if not valor:
        return "—"
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(valor)


def _fmt_numero(valor: Any, casas: int = 3) -> str:
    if valor is None or valor == "":
        return "—"
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return str(valor)
    texto = f"{n:.{casas}f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _cnpj(c):
    d = "".join(ch for ch in str(c or "") if ch.isdigit())
    if len(d) != 14:
        return str(c or "—")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _secao(pdf: FPDF, font: str, numero: str, titulo: str) -> None:
    pdf.set_font(font, "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 7, f"{numero}. {titulo}", ln=1)
    pdf.set_font(font, "", 9)


def _campo(pdf: FPDF, nome: str, valor: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.cell(58, 5, nome, ln=0)
    pdf.multi_cell(_W_TOTAL - 58, 5, str(valor or "—"))
    # fpdf2 deixa o cursor à direita da célula; sem isto a próxima linha nasce
    # fora da margem e o texto não cabe.
    pdf.set_x(pdf.l_margin)


def _texto(pdf: FPDF, altura: float, texto: Any, *, alinhamento: str = "L") -> None:
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(_W_TOTAL, altura, str(texto if texto not in (None, "") else "—"), align=alinhamento)
    pdf.set_x(pdf.l_margin)


def _cor_da_severidade(severidade: str) -> tuple[int, int, int]:
    return {
        "VERDE": (21, 128, 61),
        "AMARELO": (180, 130, 10),
        "VERMELHO": (185, 28, 28),
    }.get(str(severidade or "").upper(), (71, 85, 105))


def nome_arquivo_dossie(dossie: dict[str, Any]) -> str:
    numero = str((dossie.get("pedido") or {}).get("numero", "pedido"))[:20].replace("/", "-")
    return f"dossie_{numero}.pdf"


def gerar_dossie_pdf_bytes(dossie: dict[str, Any]) -> bytes:
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    if FONT_PATH.is_file():
        pdf.add_font("DejaVu", "", str(FONT_PATH))
        pdf.add_font("DejaVu", "B", str(FONT_PATH))
        font = "DejaVu"
    else:
        font = "helvetica"

    pedido = dossie.get("pedido") or {}
    construtora = dossie.get("construtora") or {}
    obra = dossie.get("obra") or {}
    fornecedor = dossie.get("fornecedor") or {}

    pdf.set_font(font, "B", 14)
    _texto(pdf, 8, "DOSSIÊ DE RECEBIMENTO DE MATERIAL", alinhamento="C")
    pdf.set_font(font, "", 9)
    pdf.set_text_color(60, 60, 60)
    _texto(pdf, 5, "stellSPY — auditoria de recebimento em obra", alinhamento="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    _secao(pdf, font, "1", "Identificação")
    _campo(pdf, "Construtora", construtora.get("nome"))
    _campo(pdf, "CNPJ da construtora", _cnpj(construtora.get("cnpj")))
    _campo(pdf, "Obra", obra.get("nome"))
    _campo(pdf, "CNPJ destinatário", _cnpj(obra.get("cnpj_destinatario")))
    _campo(pdf, "Fornecedor", fornecedor.get("razao_social"))
    _campo(pdf, "CNPJ do fornecedor", _cnpj(fornecedor.get("cnpj")))
    _campo(pdf, "Pedido", pedido.get("numero"))
    _campo(pdf, "Status do pedido", pedido.get("status"))
    _campo(pdf, "Valor total do pedido", _fmt_numero(pedido.get("valor_total"), 2))
    _campo(pdf, "Identificador do dossiê", dossie.get("id"))
    _campo(pdf, "Gerado em", _fmt_data(dossie.get("gerado_em")))
    if obra.get("modo_aprendizado"):
        pdf.set_font(font, "B", 9)
        _texto(pdf, 5, "OBRA EM MODO APRENDIZADO — as especificações ainda estão sendo calibradas.")
        pdf.set_font(font, "", 9)
    pdf.ln(3)

    _secao(pdf, font, "2", "Linhas do pedido")
    col = (12, 58, 22, 20, 30, 38)
    pdf.set_font(font, "B", 7)
    for titulo, w in zip(("Linha", "Material", "Bitola", "Quantidade", "Código fornecedor", "Marca exigida"), col):
        pdf.cell(w, 7, titulo, border=1, align="C")
    pdf.ln()
    pdf.set_font(font, "", 7)
    for item in pedido.get("itens") or []:
        pdf.cell(col[0], 6, str(item.get("linha", "—")), border=1)
        pdf.cell(col[1], 6, str(item.get("material_tipo", "—"))[:34], border=1)
        pdf.cell(col[2], 6, _fmt_numero(item.get("bitola_mm"), 1) + (" mm" if item.get("bitola_mm") else ""), border=1)
        pdf.cell(col[3], 6, f"{_fmt_numero(item.get('quantidade'))} {item.get('unidade') or ''}".strip(), border=1)
        pdf.cell(col[4], 6, str(item.get("codigo_produto_fornecedor") or "—")[:22], border=1)
        pdf.cell(col[5], 6, str(item.get("marca_exigida") or "—")[:24], border=1)
        pdf.ln()
    pdf.ln(4)

    _secao(pdf, font, "3", "Notas fiscais vinculadas")
    notas = dossie.get("nfe") or []
    if not notas:
        _texto(pdf, 5, "Nenhuma NF-e vinculada a este pedido.")
    for n in notas:
        resumo = n.get("resumo_global") or {}
        pdf.set_font(font, "B", 8)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 5, f"Chave …{str(n.get('chave_acesso'))[-8]} — {_fmt_data(n.get('processado_em'))}", ln=1)
        pdf.set_font(font, "", 8)
        _texto(
            pdf,
            4,
            f"Conferência: {n.get('status_conferencia') or '—'} · tipo {n.get('tipo') or '—'} · "
            f"alerta: {resumo.get('alerta') or 'nenhum'}",
        )
        for it in (n.get("itens_resumo") or [])[:20]:
            _texto(
                pdf,
                4,
                f"  item {it.get('n_item')} · {str(it.get('descricao') or '')[:60]} · "
                f"{_fmt_numero(it.get('quantidade'))} {it.get('unidade') or ''}",
            )
    pdf.ln(3)

    _secao(pdf, font, "4", "Recebimentos e evidências")
    recibos = dossie.get("recebimentos") or []
    if not recibos:
        _texto(pdf, 5, "Nenhum recebimento registrado nesta obra.")
    for r in recibos:
        _texto(
            pdf,
            5,
            f"{_fmt_data(r.get('recebido_em'))} · {r.get('tipo')} · {r.get('status')} · "
            f"{r.get('total_evidencias')} foto(s)",
        )
    evidencias = dossie.get("evidencias") or []
    if evidencias:
        pdf.set_font(font, "B", 8)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 6, "Prova fotográfica (hash do arquivo normalizado):", ln=1)
        pdf.set_font(font, "", 7)
        for e in evidencias[:60]:
            _texto(
                pdf,
                4,
                f"{_fmt_data(e.get('recebida_em'))} · {e.get('tipo')}/{e.get('origem')} · "
                f"sha256 {str(e.get('sha256'))[:24]}…"
                + (" · SINAL DE FRAUDE" if e.get("sinalizacao_fraude") else ""),
            )
    pdf.ln(3)

    _secao(pdf, font, "5", "Divergências, severidade técnica e decisões")
    conciliacoes = dossie.get("conciliacoes") or []
    if not conciliacoes:
        _texto(pdf, 5, "Nenhuma conciliação registrada.")
    for c in conciliacoes:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "B", 9)
        pdf.set_text_color(*_cor_da_severidade(c.get("severidade_tecnica")))
        pdf.cell(0, 6, f"{_fmt_data(c.get('criado_em'))} — severidade {c.get('severidade_tecnica')} · {c.get('status')}", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font, "", 8)
        decisao = c.get("decisao") or {}
        if decisao:
            _campo(
                pdf,
                "Decisão humana",
                f"{decisao.get('decisao', '—')} por {decisao.get('usuario_email') or decisao.get('usuario_id') or '—'}"
                f" em {_fmt_data(decisao.get('em'))}",
            )
            if decisao.get("justificativa"):
                _campo(pdf, "Justificativa", decisao["justificativa"])
        else:
            _texto(pdf, 4, "Sem decisão humana registrada.")
    pdf.ln(3)

    _secao(pdf, font, "6", "Itens sem correspondência no pedido")
    sem_pedido = [
        linha
        for c in conciliacoes
        for linha in (c.get("faturados_sem_pedido") or [])
    ]
    if sem_pedido:
        pdf.set_font(font, "", 8)
        for f in sem_pedido[:30]:
            _texto(
                pdf,
                4,
                f"item {f.get('n_item')} · {str(f.get('descricao') or '')[:60]} · "
                f"{_fmt_numero(f.get('quantidade'))} {f.get('unidade') or ''} — cobrado sem linha equivalente no pedido",
            )
    else:
        _texto(pdf, 5, "Nenhum item faturado ficou sem correspondência na última conciliação registrada.")
    pdf.ln(3)

    pdf.set_font(font, "", 8)
    pdf.set_text_color(100, 100, 100)
    _texto(
        pdf,
        4,
        str(
            dossie.get("ressalva")
            or "Documento gerado automaticamente a partir dos registros do sistema. "
            "Não constitui laudo técnico nem parecer jurídico."
        ),
    )
    pdf.set_text_color(0, 0, 0)

    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")
