"""
Autenticação piloto: uma API Key por obra (header X-API-KEY).
Desenvolvimento: SKIP_API_KEY=1 desliga a verificação (não usar em produção).
"""

from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import HTTPException

from app.pwa_session import verify_session_token

SKIP_API_KEY = os.getenv("SKIP_API_KEY", "").strip().lower() in ("1", "true", "yes")


def verificar_acesso_obra(
    obra: dict[str, Any],
    *,
    x_api_key: str | None,
    pwa_session_cookie: str | None,
) -> None:
    """Aceita cookie de sessão PWA (mesma obra) ou header X-API-KEY (integrações)."""
    if SKIP_API_KEY:
        return
    oid = verify_session_token(pwa_session_cookie) if pwa_session_cookie else None
    if oid and oid == str(obra["id"]):
        return
    verificar_api_key_obra(obra, x_api_key)


def verificar_api_key_obra(obra: dict[str, Any], x_api_key: str | None) -> None:
    """Comparação em tempo constante; obra deve conter chave 'api_key' vinda do SELECT."""
    if SKIP_API_KEY:
        return
    if not x_api_key or not str(x_api_key).strip():
        raise HTTPException(status_code=401, detail="Header X-API-KEY obrigatório")
    esperada = (obra.get("api_key") or "").strip()
    recebida = str(x_api_key).strip()
    if not esperada or not secrets.compare_digest(esperada, recebida):
        raise HTTPException(status_code=403, detail="API Key inválida para esta obra")
