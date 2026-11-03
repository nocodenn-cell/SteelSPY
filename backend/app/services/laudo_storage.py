"""
Upload do laudo PDF ao Supabase Storage e URL pública.
Sem variáveis de ambiente, retorna None e o router entrega o PDF inline.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import httpx

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
LAUDO_BUCKET = os.getenv("LAUDO_STORAGE_BUCKET", "laudos")


def storage_disponivel() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY and LAUDO_BUCKET)


def caminho_objeto_laudo(nfe_log_id: UUID | str) -> str:
    return f"{nfe_log_id}.pdf"


def url_publica_laudo(nfe_log_id: UUID | str) -> str:
    """Bucket deve estar público ou a URL deve ser acessível ao cliente."""
    path = caminho_objeto_laudo(nfe_log_id)
    return f"{SUPABASE_URL}/storage/v1/object/public/{LAUDO_BUCKET}/{path}"


def enviar_laudo_pdf(nfe_log_id: UUID | str, conteudo_pdf: bytes) -> str | None:
    """
    Faz upload (upsert) e devolve URL pública.
    Falha silenciosa (None) se Storage não configurado ou erro HTTP.
    """
    if not storage_disponivel() or not conteudo_pdf:
        return None
    path = caminho_objeto_laudo(nfe_log_id)
    url = f"{SUPABASE_URL}/storage/v1/object/{LAUDO_BUCKET}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/pdf",
        "x-upsert": "true",
    }
    try:
        r = httpx.post(url, content=conteudo_pdf, headers=headers, timeout=60.0)
        if r.status_code not in (200, 201):
            return None
    except httpx.RequestError:
        return None
    return url_publica_laudo(nfe_log_id)
