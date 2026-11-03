"""
Sessão PWA: cookie HttpOnly assinado (HMAC-SHA256), sem dependências extras.
O segredo fica só no servidor; o browser não armazena a API key após o login.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

SESSION_COOKIE_NAME = "stellspy_pwa"


def get_session_secret() -> str | None:
    s = (os.getenv("PWA_SESSION_SECRET") or "").strip()
    return s or None


def session_max_age_seconds() -> int:
    raw = (os.getenv("PWA_SESSION_MAX_AGE_SECONDS") or "").strip()
    if raw.isdigit():
        return max(300, min(int(raw), 60 * 60 * 24 * 30))
    return 60 * 60 * 24 * 7


def cookie_secure_flag() -> bool:
    return (os.getenv("PWA_COOKIE_SECURE") or "1").strip().lower() not in ("0", "false", "no")


def cookie_samesite() -> str:
    """
    lax: mesmo site ou subpaths na mesma origem (padrão).
    none: PWA e API em origens diferentes (ex.: app.* e api.*); exige Secure no cookie.
    """
    raw = (os.getenv("PWA_COOKIE_SAMESITE") or "lax").strip().lower()
    if raw in ("none", "strict", "lax"):
        return raw
    return "lax"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_session_token(obra_id: str, *, secret: str, max_age: int) -> str:
    now = int(time.time())
    payload = {"obra_id": obra_id, "iat": now, "exp": now + max_age}
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_session_token(token: str | None) -> str | None:
    """
    Retorna obra_id (UUID string) se assinatura e expiração forem válidas; caso contrário None.
    """
    secret = get_session_secret()
    if not secret or not token or "." not in token:
        return None
    try:
        body, sig = token.rsplit(".", 1)
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(_b64url_decode(body).decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        oid = data.get("obra_id")
        return str(oid) if oid else None
    except (ValueError, json.JSONDecodeError, KeyError, TypeError, OSError):
        return None
