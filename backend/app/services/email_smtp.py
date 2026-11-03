"""
Envio de e-mail com anexo via SMTP (stdlib). Usado pelo job de relatório semanal.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def enviar_email_com_anexo(
    *,
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    anexo_nome: str,
    anexo_bytes: bytes,
    remetente: str | None = None,
    copia_oculta: list[str] | None = None,
) -> None:
    """
    Envia mensagem multipart com um anexo. Usa variáveis SMTP_* no ambiente.

    SMTP_HOST obrigatório; SMTP_USER/SMTP_PASSWORD podem ser vazios em relay interno.
    SMTP_PORT default 587 (STARTTLS) ou 465 se SMTP_USE_SSL=1.
    """
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise RuntimeError("SMTP_HOST não definido.")

    use_ssl = _env_bool("SMTP_USE_SSL", False)
    port = _env_int("SMTP_PORT", 465 if use_ssl else 587)
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    use_tls = _env_bool("SMTP_USE_TLS", not use_ssl)

    from_addr = remetente or os.getenv("RELATORIO_EMAIL_FROM", "").strip()
    if not from_addr:
        raise RuntimeError("RELATORIO_EMAIL_FROM (ou parâmetro remetente) não definido.")

    if not destinatarios:
        raise ValueError("Lista de destinatários vazia.")

    bcc = [x.strip() for x in (copia_oculta or []) if x.strip()]
    envelope = list(destinatarios) + bcc

    msg = MIMEMultipart()
    msg["Subject"] = assunto
    msg["From"] = from_addr
    msg["To"] = ", ".join(destinatarios)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))

    part = MIMEBase("application", "octet-stream")
    part.set_payload(anexo_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{anexo_nome}"')
    msg.attach(part)

    raw = msg.as_string()

    if use_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, envelope, raw)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            if use_tls:
                ctx = ssl.create_default_context()
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, envelope, raw)

    logger.info("E-mail enviado (To=%s Bcc=%s) anexo=%s", destinatarios, bcc or [], anexo_nome)


def destinatarios_globais_opcional() -> list[str]:
    """RELATORIO_EMAIL_COPIA: cópia fixa (ex.: backoffice), separada por vírgula."""
    raw = os.getenv("RELATORIO_EMAIL_COPIA", "").strip()
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out
