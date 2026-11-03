"""
Validação de URLs usadas pelo servidor (evita SSRF em foto_url e open redirect no laudo).
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse


class URLNaoPermitidaError(ValueError):
    """URL rejeitada por política de segurança."""


def _host_literais_e_metadata(hostname: str) -> bool:
    h = hostname.lower().rstrip(".")
    if h in ("localhost", "0.0.0.0", "metadata", "metadata.google.internal"):
        return False
    if h.endswith(".localhost") or h.endswith(".local") or h.endswith(".internal"):
        return False
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
        if ip == ipaddress.ip_address("169.254.169.254"):
            return False
    except ValueError:
        pass
    return True


def validar_url_imagem_publica(url: str | None) -> str | None:
    """
    foto_url: apenas HTTPS, host não óbvio de SSRF.
    Opcional: FOTO_URL_ALLOWED_HOSTS=host1,host2 restringe a uma lista explícita.
    """
    if url is None:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        raise URLNaoPermitidaError("foto_url deve usar HTTPS.")
    host = parsed.hostname
    if not host:
        raise URLNaoPermitidaError("foto_url com hostname inválido.")

    allow = (os.getenv("FOTO_URL_ALLOWED_HOSTS") or "").strip()
    if allow:
        permitidos = {x.strip().lower() for x in allow.split(",") if x.strip()}
        if host.lower() not in permitidos:
            raise URLNaoPermitidaError("host da foto_url não está na lista FOTO_URL_ALLOWED_HOSTS.")
    elif not _host_literais_e_metadata(host):
        raise URLNaoPermitidaError("host da foto_url não permitido (rede local / metadata bloqueados).")

    return raw


def url_redirect_laudo_confiavel(url: str, supabase_project_url: str) -> bool:
    """
    Redirecionamento 302 do laudo só para o mesmo host do projeto Supabase
    (evita open redirect se laudo_pdf_url for alterado indevidamente).
    """
    if not supabase_project_url or not url:
        return False
    try:
        alvo = urlparse(url.strip())
        base = urlparse(supabase_project_url.strip().rstrip("/"))
    except Exception:
        return False
    if (alvo.scheme or "").lower() != "https":
        return False
    if not alvo.hostname or not base.hostname:
        return False
    return alvo.hostname.lower() == base.hostname.lower()
