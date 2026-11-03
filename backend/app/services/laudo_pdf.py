"""
Laudo de Conformidade Técnica (PDF) — governança e rastro para obra/fornecedor.
Usa fpdf2 + fonte DejaVu (UTF-8) em assets/fonts/DejaVuSans.ttf.
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fpdf import FPDF

from app.utils.url_seguras import URLNaoPermitidaError, validar_url_imagem_publica

FONT_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"
EMISSOR_PADRAO = os.getenv("LAUDO_EMISSOR_NOME", "CheckObra AI")
LOGO_OBRA_PATH = os.getenv("LAUDO_LOGO_OBRA_PATH", "")
LOGO_SISTEMA_PATH = os.getenv("LAUDO_LOGO_SISTEMA_PATH", "")

SEFAZ_PORTAL = "https://www.nfe.fazenda.gov.br/portal/principal.aspx"


def montar_contexto_laudo(
    *,
    nfe_log: dict[str, Any],
    obra: dict[str, Any],
) -> dict[str, Any]:
    """
    Estrutura neutra (dict) para o PDF e para testes.
    `nfe_log`: id, chave_acesso, status_conferencia, processado_em, xml_data, override_info, foto_url?
    `obra`: nome, cnpj_destinatario, modo_aprendizado? (obra em testes → faixa + marca d'água no PDF)
    """
    xml = nfe_log.get("xml_data") if isinstance(nfe_log.get("xml_data"), dict) else {}
    emit = xml.get("emitente") or {}
    if not emit and isinstance(xml.get("raw"), dict):
        raw = xml["raw"]
        emit = raw.get("emitente") or raw.get("emit") or {}

    chave = str(nfe_log.get("chave_acesso", ""))
    detalhes = xml.get("detalhes") if isinstance(xml.get("detalhes"), list) else []
    motivos = xml.get("motivos") if isinstance(xml.get("motivos"), list) else []
    alerta = xml.get("alerta") or ""
    modo_aprendizado = bool(xml.get("modo_aprendizado", False))
    mensagem_aprendizado = xml.get("mensagem_modo_aprendizado")
    modo_obra = bool(obra.get("modo_aprendizado", False))

    fornecedor_nome = (
        (xml.get("emitente_nome") or "").strip()
        or str(emit.get("nome") or emit.get("xNome") or "").strip()
        or "—"
    )
    cnpj_emit = str(xml.get("emitente_cnpj") or emit.get("cnpj") or emit.get("CNPJ") or "")
    numero_nf = str(xml.get("nfe_numero") or emit.get("numero_nf") or emit.get("nNF") or "—")
    serie_nf = str(
        xml.get("nfe_serie")
        or emit.get("serie")
        or emit.get("serie_nf")
        or xml.get("serie_nf")
        or "—"
    )

    return {
        "laudo_id": str(nfe_log.get("id", "")),
        "status": nfe_log.get("status_conferencia", ""),
        "alerta": alerta,
        "processado_em": nfe_log.get("processado_em"),
        "obra_nome": obra.get("nome", "—"),
        "obra_cnpj": _format_cnpj(obra.get("cnpj_destinatario", "")),
        "fornecedor_nome": fornecedor_nome,
        "fornecedor_cnpj": _format_cnpj(cnpj_emit),
        "numero_nf": numero_nf,
        "serie_nf": serie_nf,
        "chave_acesso": chave,
        "chave_formatada": _formatar_chave(chave),
        "url_consulta_sefaz": SEFAZ_PORTAL,
        "detalhes": detalhes,
        "motivos": motivos,
        "modo_aprendizado": modo_aprendizado,
        "mensagem_modo_aprendizado": mensagem_aprendizado,
        "ambiente_testes": modo_obra or modo_aprendizado,
        "override_info": nfe_log.get("override_info") if isinstance(nfe_log.get("override_info"), dict) else {},
        "foto_url": nfe_log.get("foto_url") or xml.get("foto_url"),
        "emissor": EMISSOR_PADRAO,
    }


def _format_cnpj(d: str) -> str:
    s = "".join(c for c in str(d) if c.isdigit())
    if len(s) != 14:
        return str(d) or "—"
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def _formatar_chave(chave: str) -> str:
    d = "".join(c for c in chave if c.isdigit())
    if len(d) != 44:
        return chave
    parts = [d[i : i + 4] for i in range(0, 44, 4)]
    return " ".join(parts)


def _veredito_bloco(status: str) -> tuple[str, str, tuple[int, int, int]]:
    """Texto principal + subtítulo + RGB fill (claro)."""
    if status == "VERDE":
        return (
            "MATERIAL CONFORME — Liberado para descarga",
            "Nenhuma divergência crítica identificada na conferência técnica automatizada.",
            (212, 237, 218),
        )
    if status == "AMARELO":
        return (
            "ATENÇÃO — Divergência tolerável / ressalva",
            "Há divergências que exigem validação do responsável técnico antes de consolidar o recebimento.",
            (255, 243, 205),
        )
    if status == "VERMELHO":
        return (
            "NÃO CONFORME — Bloqueio de entrada sugerido",
            "Devolução ou substituição sugerida conforme política da construtora e contrato de fornecimento.",
            (248, 215, 218),
        )
    return (
        "PENDENTE — Laudo preliminar",
        "Conferência ainda não concluída (aguardando dados da NF-e).",
        (226, 227, 229),
    )


def _carregar_imagem_url(url: str, timeout: float = 15.0) -> bytes | None:
    try:
        validar_url_imagem_publica(url)
    except URLNaoPermitidaError:
        return None
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        if r.status_code == 200 and r.content[:4] in (b"\xff\xd8\xff", b"\x89PNG", b"GIF8"):
            return r.content
    except httpx.RequestError:
        return None
    return None


def _proc_txt(ctx: dict[str, Any]) -> str:
    proc = ctx.get("processado_em")
    if hasattr(proc, "isoformat"):
        return proc.isoformat()
    if proc:
        return str(proc)
    return datetime.utcnow().isoformat() + "Z"


def _faixa_ambiente_testes(pdf: FPDF, font: str) -> None:
    pdf.set_fill_color(255, 210, 100)
    pdf.rect(0, 0, pdf.w, 10, "F")
    pdf.set_xy(pdf.l_margin, 2)
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(65, 40, 0)
    pdf.cell(
        0,
        6,
        "AMBIENTE DE TESTES — SEM VALOR DE BLOQUEIO OPERACIONAL",
        ln=1,
    )
    pdf.set_text_color(0, 0, 0)


def _marca_dagua_testes(pdf: FPDF, font: str) -> None:
    with pdf.rotation(32, x=pdf.w / 2, y=pdf.h / 2):
        pdf.set_font(font, "B", 40)
        pdf.set_text_color(238, 238, 238)
        pdf.set_xy(30, 145)
        pdf.cell(0, 10, "TESTES")
    pdf.set_text_color(0, 0, 0)


def _grade_blocos_autoridade(pdf: FPDF, font: str, ctx: dict[str, Any]) -> None:
    """Grade 2x2: Obra | Fornecedor / Data-Hora | NF-e."""
    x0 = pdf.l_margin
    wtot = pdf.w - pdf.l_margin - pdf.r_margin
    wcol = wtot / 2
    h_hdr = 5.0
    obra_body = f"{ctx.get('obra_nome', '—')}\nCNPJ {ctx.get('obra_cnpj', '—')}"
    forn_body = f"{ctx.get('fornecedor_nome', '—')}\nCNPJ {ctx.get('fornecedor_cnpj', '—')}"
    nfe_body = f"Nota nº {ctx.get('numero_nf', '—')}\nSérie {ctx.get('serie_nf', '—')}"
    proc_txt = _proc_txt(ctx)

    pdf.set_font(font, "B", 11)
    pdf.cell(0, 6, "1. Identificação (blocos de autoridade)", ln=1)
    pdf.set_font(font, "", 8)

    y = pdf.get_y()
    pdf.set_xy(x0, y)
    pdf.set_font(font, "B", 8)
    pdf.cell(wcol, h_hdr, "Obra", border=1)
    pdf.set_xy(x0 + wcol, y)
    pdf.cell(wcol, h_hdr, "Fornecedor (emitente)", border=1)
    pdf.set_xy(x0, y + h_hdr)
    pdf.set_font(font, "", 8)
    pdf.multi_cell(wcol, 4, obra_body, border=1)
    yl = pdf.get_y()
    pdf.set_xy(x0 + wcol, y + h_hdr)
    pdf.multi_cell(wcol, 4, forn_body, border=1)
    yr = pdf.get_y()
    pdf.set_y(max(yl, yr))

    y2 = pdf.get_y()
    pdf.set_xy(x0, y2)
    pdf.set_font(font, "B", 8)
    pdf.cell(wcol, h_hdr, "Data / hora do processamento", border=1)
    pdf.set_xy(x0 + wcol, y2)
    pdf.cell(wcol, h_hdr, "NF-e", border=1)
    pdf.set_xy(x0, y2 + h_hdr)
    pdf.set_font(font, "", 8)
    pdf.multi_cell(wcol, 4, proc_txt, border=1)
    y2l = pdf.get_y()
    pdf.set_xy(x0 + wcol, y2 + h_hdr)
    pdf.multi_cell(wcol, 4, nfe_body, border=1)
    y2r = pdf.get_y()
    pdf.set_y(max(y2l, y2r))
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)


def _anexo_evidencia_recebimento(pdf: FPDF, font: str, ctx: dict[str, Any]) -> None:
    foto = ctx.get("foto_url")
    if not foto:
        return
    pdf.set_font(font, "B", 11)
    pdf.cell(0, 6, "Anexo: Evidência de Recebimento", ln=1)
    pdf.set_font(font, "", 8)
    data = _carregar_imagem_url(str(foto))
    if data:
        try:
            img = io.BytesIO(data)
            pdf.image(img, x=pdf.l_margin, w=min(120, pdf.w - pdf.l_margin - pdf.r_margin))
            pdf.ln(2)
        except Exception:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                0,
                5,
                f"URL registrada: {foto} (imagem não pôde ser embutida no laudo).",
            )
    else:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, f"URL registrada: {foto} (download indisponível para o laudo).")
    pdf.ln(2)
    pdf.set_x(pdf.l_margin)


def gerar_laudo_pdf_bytes(ctx: dict[str, Any]) -> bytes:
    """Gera PDF A4 em memória."""
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    if FONT_PATH.is_file():
        pdf.add_font("DejaVu", "", str(FONT_PATH))
        pdf.add_font("DejaVu", "B", str(FONT_PATH))
        font = "DejaVu"
    else:
        font = "helvetica"

    if ctx.get("ambiente_testes"):
        _marca_dagua_testes(pdf, font)
        _faixa_ambiente_testes(pdf, font)
        pdf.set_y(12)

    # --- Cabeçalho: logos opcionais
    y0 = pdf.get_y()
    if LOGO_OBRA_PATH and Path(LOGO_OBRA_PATH).is_file():
        try:
            pdf.image(LOGO_OBRA_PATH, x=15, y=y0, w=35)
        except Exception:
            pass
    if LOGO_SISTEMA_PATH and Path(LOGO_SISTEMA_PATH).is_file():
        try:
            pdf.image(LOGO_SISTEMA_PATH, x=160, y=y0, w=35)
        except Exception:
            pass
    pdf.set_y(y0 + 22)

    pdf.set_font(font, "B", 14)
    pdf.multi_cell(0, 8, "RELATÓRIO DE CONFORMIDADE DE RECEBIMENTO TÉCNICO", align="C")
    pdf.ln(2)
    pdf.set_font(font, "", 9)
    pdf.set_text_color(60, 60, 60)
    emissor = ctx.get("emissor", EMISSOR_PADRAO)
    pdf.multi_cell(0, 5, f"Emitido por: {emissor}", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)

    pdf.set_font(font, "", 9)
    pdf.cell(0, 5, f"ID do laudo (rastreio): {ctx.get('laudo_id', '—')}", ln=1)
    pdf.ln(2)
    _grade_blocos_autoridade(pdf, font, ctx)
    chave_fmt = ctx.get("chave_formatada") or ctx.get("chave_acesso", "")
    pdf.set_font(font, "", 9)
    pdf.cell(0, 5, f"Chave de acesso: {chave_fmt}", ln=1)
    url = ctx.get("url_consulta_sefaz", SEFAZ_PORTAL)
    pdf.set_text_color(0, 80, 160)
    pdf.cell(0, 5, f"Consulta nacional NF-e: {url}", ln=1, link=url)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)

    # --- Veredito
    pdf.set_font(font, "B", 11)
    pdf.cell(0, 6, "2. Veredito técnico", ln=1)
    status = str(ctx.get("status", ""))
    titulo, subtitulo, rgb = _veredito_bloco(status)
    pdf.set_fill_color(*rgb)
    pdf.set_font(font, "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 7, titulo, fill=True)
    pdf.set_font(font, "", 9)
    pdf.set_fill_color(*rgb)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, subtitulo, fill=True)
    pdf.set_x(pdf.l_margin)
    if ctx.get("alerta"):
        pdf.set_font(font, "", 9)
        pdf.multi_cell(0, 5, f"Classificação do alerta: {ctx.get('alerta')}")
        pdf.set_x(pdf.l_margin)
    if ctx.get("mensagem_modo_aprendizado"):
        pdf.set_font(font, "B", 9)
        pdf.multi_cell(0, 5, "Modo Aprendizado — comunicado ao fiscal:")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "", 9)
        pdf.multi_cell(0, 5, str(ctx["mensagem_modo_aprendizado"]))
        pdf.set_x(pdf.l_margin)
    pdf.ln(3)
    pdf.set_x(pdf.l_margin)

    # --- Tabela
    pdf.set_font(font, "B", 11)
    pdf.cell(0, 6, "3. Comparação técnica (especificação x NF-e)", ln=1)
    col_w = (32, 44, 58, 49)
    pdf.set_font(font, "B", 7)
    headers = ("Item / material", "Especificado (projeto)", "Recebido (NF-e)", "Conclusão")
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, align="C")
    pdf.ln()
    pdf.set_font(font, "", 7)
    for row in ctx.get("detalhes") or []:
        if not isinstance(row, dict):
            continue
        item = str(row.get("item", "—"))[:32]
        esp = str(row.get("esperado", "—"))[:38]
        rec = str(row.get("recebido", "—"))[:52]
        conc = str(row.get("conclusão", row.get("conclusao", "—")))[:42]
        pdf.cell(col_w[0], 6, item, border=1)
        pdf.cell(col_w[1], 6, esp, border=1)
        pdf.cell(col_w[2], 6, rec, border=1)
        pdf.cell(col_w[3], 6, conc, border=1)
        pdf.ln()
    pdf.ln(4)

    # --- Motivos (texto)
    motivos = ctx.get("motivos") or []
    if motivos:
        pdf.set_font(font, "B", 10)
        pdf.cell(0, 6, "Detalhamento (motivos do sistema)", ln=1)
        pdf.set_font(font, "", 8)
        for m in motivos[:30]:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4, f"• {m}")
        if len(motivos) > 30:
            pdf.cell(0, 5, f"… (+{len(motivos) - 30} linhas)", ln=1)
        pdf.ln(2)

    # --- Override
    ov = ctx.get("override_info") or {}
    hist = ov.get("historico") or []
    if hist:
        pdf.set_font(font, "B", 11)
        pdf.cell(0, 6, "4. Histórico de decisão / override", ln=1)
        pdf.set_font(font, "", 9)
        for entrada in hist[-5:]:
            if not isinstance(entrada, dict):
                continue
            usuario = entrada.get("usuario_id") or "—"
            em = entrada.get("em", "—")
            motivo = entrada.get("justificativa") or entrada.get("motivo_texto") or "—"
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, f"Divergência autorizada ou registrada manualmente por {usuario} em {em}.")
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, f"Motivo: {motivo}")
            pdf.ln(1)

    _anexo_evidencia_recebimento(pdf, font, ctx)

    pdf.set_font(font, "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    emissor_rod = ctx.get("emissor") or EMISSOR_PADRAO
    pdf.multi_cell(
        0,
        4,
        f"Documento gerado automaticamente por {emissor_rod} — Compliance estrutural / recebimento. "
        "Não substitui parecer do responsável técnico nem cláusulas contratuais.",
    )

    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return str(out).encode("latin-1")


def nome_arquivo_laudo(ctx: dict[str, Any]) -> str:
    lid = ctx.get("laudo_id", "laudo")[:8]
    st = ctx.get("status", "X")
    return f"laudo_conformidade_{st}_{lid}.pdf"
