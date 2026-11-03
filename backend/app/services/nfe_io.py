"""
Integração NFe.io (ou compatível). Em desenvolvimento, use NFE_IO_MOCK=1 para resposta fake.

Contrato de saída (JSON normalizado):
- emitente_nome, emitente_cnpj (somente dígitos), nfe_numero, nfe_serie
- emitente: { nome, cnpj, numero_nf, serie } (espelho para laudos legados)
- itens[]: bitola_mm, marca, quantidade, unidade (maiúscula, uso interno),
           unidade_original (texto da NF: UN, KG, M, etc.), descricao opcional
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.nfe_item_campos import extrair_campos_multimaterial

NFE_IO_BASE = os.getenv("NFE_IO_BASE_URL", "https://api.nfe.io/v1")
NFE_IO_TOKEN = os.getenv("NFE_IO_TOKEN", "")
NFE_IO_MOCK = os.getenv("NFE_IO_MOCK", "0") == "1"


def _digits_only(val: Any) -> str:
    if val is None:
        return ""
    return "".join(c for c in str(val) if c.isdigit())


def _as_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _emitente_from_raw(raw: dict[str, Any]) -> dict[str, str]:
    emit = raw.get("emitente")
    if emit is None and isinstance(raw.get("emit"), dict):
        emit = raw["emit"]
    if not isinstance(emit, dict):
        emit = {}
    nome = (
        emit.get("nome")
        or emit.get("xNome")
        or emit.get("razao_social")
        or emit.get("xFant")
        or ""
    )
    cnpj = emit.get("cnpj") or emit.get("CNPJ") or emit.get("CNPJ_emitente")
    n_nf = emit.get("numero_nf") or emit.get("nNF") or emit.get("numero")
    serie = emit.get("serie") or emit.get("serieNF") or emit.get("serie_nf")
    return {
        "nome": str(nome).strip(),
        "cnpj": _digits_only(cnpj),
        "numero_nf": str(n_nf).strip() if n_nf is not None else "",
        "serie": str(serie).strip() if serie is not None else "",
    }


def _ide_from_raw(raw: dict[str, Any]) -> dict[str, str]:
    ide = raw.get("ide")
    if not isinstance(ide, dict):
        ide = {}
    n = ide.get("nNF") or ide.get("numero") or raw.get("nfe_numero") or raw.get("numero_nf")
    s = ide.get("serie") or raw.get("nfe_serie") or raw.get("serie_nf") or raw.get("serie")
    return {
        "nfe_numero": str(n).strip() if n is not None else "",
        "nfe_serie": str(s).strip() if s is not None else "",
    }


def _achatar_item_com_prod(it: dict[str, Any]) -> dict[str, Any]:
    """NF-e JSON costuma aninhar campos do produto em `prod`."""
    prod = it.get("prod")
    if isinstance(prod, dict):
        merged = {**prod}
        for k, v in it.items():
            if k != "prod" and k not in merged:
                merged[k] = v
        return merged
    return it


def _unidade_comercial_nf(it: dict[str, Any]) -> str:
    u = (
        it.get("uCom")
        or it.get("unidade_comercial")
        or it.get("UnidadeComercial")
        or it.get("unidade")
        or it.get("Unidade")
        or "KG"
    )
    return str(u).strip()


def _normalizar_item_nfe(it: dict[str, Any]) -> dict[str, Any]:
    it = _achatar_item_com_prod(it)
    u_orig = _unidade_comercial_nf(it)
    u_int = u_orig.upper() if u_orig else "KG"
    desc = it.get("descricao") or it.get("xProd") or it.get("produto")
    base = {
        "descricao": desc,
        "bitola_mm": _as_float(it.get("bitola_mm") or it.get("bitola") or it.get("diametro_mm")),
        "marca": it.get("marca") or it.get("fabricante"),
        "quantidade": _as_float(it.get("quantidade") or it.get("qCom") or it.get("qtd")),
        "unidade": u_int,
        "unidade_original": u_orig or u_int,
        "metros_por_barra": _as_float(it.get("metros_por_barra"), 12.0),
        "nItem": it.get("nItem") or it.get("numero_item") or it.get("item"),
    }
    extra = extrair_campos_multimaterial(desc)
    base.update(extra)
    return base


def _montar_emitente_objeto(emit: dict[str, str], nfe_numero: str, nfe_serie: str) -> dict[str, Any]:
    return {
        "nome": emit["nome"],
        "cnpj": emit["cnpj"],
        "numero_nf": nfe_numero or emit["numero_nf"],
        "serie": nfe_serie or emit["serie"],
    }


def _adaptar_resposta_nfe_io(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza resposta da API (NFe.io, proxy SEFAZ ou JSON derivado de XML)."""
    lista = raw.get("itens") or raw.get("items") or raw.get("det") or []
    itens = [_normalizar_item_nfe(x) for x in lista if isinstance(x, dict)]

    emit = _emitente_from_raw(raw)
    ide = _ide_from_raw(raw)

    nfe_numero = emit["numero_nf"] or ide["nfe_numero"] or str(raw.get("nfe_numero") or "")
    nfe_serie = emit["serie"] or ide["nfe_serie"] or str(raw.get("nfe_serie") or "")

    emitente_nome = emit["nome"] or str(raw.get("emitente_nome") or "").strip()
    emitente_cnpj = emit["cnpj"] or _digits_only(raw.get("emitente_cnpj"))

    emit_obj = _montar_emitente_objeto(
        {
            "nome": emitente_nome,
            "cnpj": emitente_cnpj,
            "numero_nf": emit["numero_nf"],
            "serie": emit["serie"],
        },
        nfe_numero,
        nfe_serie,
    )

    chave = raw.get("chave_acesso") or raw.get("chave") or raw.get("chaveAcesso")

    return {
        "chave": chave,
        "emitente_nome": emitente_nome,
        "emitente_cnpj": emitente_cnpj,
        "nfe_numero": nfe_numero,
        "nfe_serie": nfe_serie,
        "emitente": emit_obj,
        "itens": itens,
        "raw": raw,
    }


def buscar_xml_ou_json_por_chave(chave_acesso: str) -> dict[str, Any] | None:
    """
    Retorna payload JSON da NF (itens normalizados pelo adapter) ou None se 404/indisponível.

    Contrato mínimo do dict de saída para o conferente:
    - itens: lista de { bitola_mm, marca, quantidade, unidade, unidade_original, metros_por_barra? }
    """
    if NFE_IO_MOCK:
        return {
            "chave": chave_acesso,
            "emitente_nome": "Aço Brasil Comércio Ltda",
            "emitente_cnpj": "12345678000190",
            "nfe_numero": "78432",
            "nfe_serie": "1",
            "emitente": {
                "nome": "Aço Brasil Comércio Ltda",
                "cnpj": "12345678000190",
                "numero_nf": "78432",
                "serie": "1",
            },
            "itens": [
                {
                    "descricao": "Vergalhão CA-50",
                    "bitola_mm": 10.0,
                    "marca": "GERDAU",
                    "quantidade": 61.7,
                    "unidade": "KG",
                    "unidade_original": "KG",
                },
                {
                    "descricao": "Vergalhão extra",
                    "bitola_mm": 32.0,
                    "marca": "X",
                    "quantidade": 100.0,
                    "unidade": "KG",
                    "unidade_original": "kg",
                },
            ],
        }

    if not NFE_IO_TOKEN:
        return None

    url = f"{NFE_IO_BASE.rstrip('/')}/nfes/{chave_acesso}"
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {NFE_IO_TOKEN}"}, timeout=30.0)
    except httpx.RequestError:
        return None

    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        return None

    raw = r.json()
    return _adaptar_resposta_nfe_io(raw)
