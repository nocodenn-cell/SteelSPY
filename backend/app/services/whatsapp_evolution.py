"""
Notificações WhatsApp via Evolution API (opcional).

Resiliência: retentativas com backoff exponencial + jitter em falhas transitórias
(timeout, rede, HTTP 408/429/5xx). Respostas 4xx definitivas (exceto 429) não reintentam.

Destino: coluna obras.whatsapp_destino; se vazia, usa WHATSAPP_ALERT_NUMBER (env).

Contrato: POST /message/sendText/{instance}, header apikey, JSON { "number", "text" }.
"""

from __future__ import annotations

import logging
import os
import random
import time
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Falhas típicas de rede/API instável
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _env_int(name: str, default: int, *, min_v: int = 1, max_v: int = 100) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(min_v, min(max_v, int(raw)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _normalizar_numero_e164_digits(raw: str | None) -> str | None:
    if raw is None:
        return None
    d = _digits_only(str(raw).strip())
    if len(d) < 10 or len(d) > 15:
        if d:
            logger.warning("Número WhatsApp inválido (esperado 10–15 dígitos).")
        return None
    return d


def evolution_servidor_configurado() -> bool:
    """Base + credenciais Evolution (sem exigir número de destino)."""
    if os.getenv("WHATSAPP_DISABLED", "").strip() == "1":
        return False
    base = os.getenv("EVOLUTION_API_BASE_URL", "").strip()
    key = os.getenv("EVOLUTION_API_KEY", "").strip()
    inst = os.getenv("EVOLUTION_INSTANCE_NAME", "").strip()
    return bool(base and key and inst)


def _numero_fallback_global() -> str | None:
    return _normalizar_numero_e164_digits(os.getenv("WHATSAPP_ALERT_NUMBER", "").strip())


def _fetch_whatsapp_destino_obra(obra_id: str) -> str | None:
    """SELECT mínimo para evitar import circular com conferencia_persist."""
    from sqlalchemy import text

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT whatsapp_destino FROM obras WHERE id = CAST(:id AS uuid)"),
            {"id": obra_id},
        ).scalar()
        if row is None:
            return None
        return str(row).strip() if row else None
    finally:
        db.close()


def resolver_destino_whatsapp(
    obra_id: str,
    destino_obra: str | None,
    *,
    usar_coluna_obra_no_banco: bool,
) -> str | None:
    """
    Ordem: valor já conhecido da obra → (opcional) coluna no banco → WHATSAPP_ALERT_NUMBER.

    `usar_coluna_obra_no_banco=False` quando `carregar_obra_por_id` já foi chamado no mesmo fluxo
    (evita SELECT duplicado). Se o destino da obra for inválido/vazio, cai no fallback global.
    """
    n = _normalizar_numero_e164_digits(destino_obra)
    if n:
        return n
    if usar_coluna_obra_no_banco:
        raw = _fetch_whatsapp_destino_obra(obra_id)
        n2 = _normalizar_numero_e164_digits(raw)
        if n2:
            return n2
    return _numero_fallback_global()


def _endpoint_send_text() -> str | None:
    base = os.getenv("EVOLUTION_API_BASE_URL", "").strip().rstrip("/")
    inst = os.getenv("EVOLUTION_INSTANCE_NAME", "").strip()
    if not base or not inst:
        return None
    return f"{base}/message/sendText/{quote(inst, safe='')}"


def _deve_reintentar_http(status_code: int) -> bool:
    if status_code in _RETRY_STATUS:
        return True
    return status_code >= 500


def _enviar_texto_evolution(numero: str, texto: str) -> bool:
    """
    Uma tentativa HTTP. Retorna True se 2xx.
    """
    url = _endpoint_send_text()
    api_key = os.getenv("EVOLUTION_API_KEY", "").strip()
    if not url or not api_key:
        return False

    payload = {"number": numero, "text": texto}
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    r = httpx.post(url, headers=headers, json=payload, timeout=_TIMEOUT)
    if 200 <= r.status_code < 300:
        return True
    r.raise_for_status()
    return False


def _enviar_texto_com_resiliencia(numero: str, texto: str) -> bool:
    max_t = _env_int("EVOLUTION_MAX_TENTATIVAS", 3, min_v=1, max_v=10)
    base_sleep = _env_float("EVOLUTION_BACKOFF_BASE_SEGUNDOS", 1.0)

    ultimo_erro: str | None = None
    for tentativa in range(max_t):
        try:
            ok_once = _enviar_texto_evolution(numero, texto)
            if ok_once:
                if tentativa > 0:
                    logger.info("Evolution: envio OK na tentativa %s/%s", tentativa + 1, max_t)
                else:
                    logger.info("WhatsApp Evolution: mensagem enviada (destino mascarado).")
                return True
            ultimo_erro = "envio retornou sem sucesso (ex.: URL/API key ausentes)"
        except httpx.HTTPStatusError as e:
            sc = e.response.status_code
            ultimo_erro = f"HTTP {sc}"
            if not _deve_reintentar_http(sc):
                logger.warning("Evolution: erro não reintentável: %s", e)
                return False
        except httpx.TimeoutException as e:
            ultimo_erro = f"timeout: {e}"
        except httpx.TransportError as e:
            ultimo_erro = f"transporte: {e}"
        except httpx.HTTPError as e:
            ultimo_erro = str(e)
        except OSError as e:
            ultimo_erro = f"os: {e}"

        if tentativa < max_t - 1:
            exp = base_sleep * (2**tentativa)
            jitter = random.uniform(0, base_sleep * 0.25)
            sleep_s = min(exp + jitter, 60.0)
            logger.warning(
                "Evolution: tentativa %s/%s falhou (%s); nova tentativa em %.2fs",
                tentativa + 1,
                max_t,
                ultimo_erro or "?",
                sleep_s,
            )
            time.sleep(sleep_s)

    logger.warning("Evolution: esgotadas %s tentativas (%s)", max_t, ultimo_erro)
    return False


def _enviar_ou_noop(
    obra_id: str,
    destino_obra: str | None,
    *,
    usar_coluna_obra_no_banco: bool,
    texto: str,
) -> None:
    if not evolution_servidor_configurado():
        logger.debug("WhatsApp Evolution (servidor) desligado ou incompleto; mensagem não enviada.")
        return

    numero = resolver_destino_whatsapp(
        obra_id,
        destino_obra,
        usar_coluna_obra_no_banco=usar_coluna_obra_no_banco,
    )
    if not numero:
        logger.warning(
            "WhatsApp: sem destino (obra sem whatsapp_destino e WHATSAPP_ALERT_NUMBER vazio) obra=%s",
            obra_id[:8],
        )
        return

    ok = _enviar_texto_com_resiliencia(numero, texto)
    if not ok:
        logger.warning("WhatsApp: falha definitiva após retentativas obra=%s", obra_id[:8])


def notificar_mensagem_fiscal(
    obra_id: str,
    chave: str,
    mensagem: str,
    *,
    whatsapp_destino_obra: str | None = None,
    usar_coluna_obra_no_banco: bool = False,
) -> None:
    """Após conferência concluída (API síncrona ou worker da fila)."""
    if not evolution_servidor_configurado():
        logger.info(
            "Mensagem fiscal (WhatsApp desligado) obra=%s chave=%s\n%s",
            obra_id,
            chave[:8] + "…",
            mensagem,
        )
        return
    prefix = f"[SteelSpy] Obra {obra_id[:8]}…\nChave {chave[:12]}…\n\n"
    _enviar_ou_noop(
        obra_id,
        whatsapp_destino_obra,
        usar_coluna_obra_no_banco=usar_coluna_obra_no_banco,
        texto=prefix + mensagem,
    )


def notificar_xml_pendente(
    obra_id: str,
    chave: str,
    *,
    whatsapp_destino_obra: str | None = None,
    usar_coluna_obra_no_banco: bool = True,
) -> None:
    """Primeira tentativa da fila ou aviso de NF ainda sem XML na API."""
    chave44 = chave[:44] if len(chave) >= 44 else chave
    texto = (
        f"[SteelSpy] Aguardando XML na SEFAZ/API.\n"
        f"Obra: {obra_id}\n"
        f"Chave NF-e: {chave44}\n"
        f"Retentativas automáticas em 5, 15 e 30 min."
    )
    if not evolution_servidor_configurado():
        logger.info("Aviso XML pendente (WhatsApp desligado) obra=%s chave=%s…", obra_id, chave44[:8])
        return
    _enviar_ou_noop(
        obra_id,
        whatsapp_destino_obra,
        usar_coluna_obra_no_banco=usar_coluna_obra_no_banco,
        texto=texto,
    )


def evolution_pode_enviar() -> bool:
    """Compat: True se o servidor Evolution (URL + apikey + instância) está configurado."""
    return evolution_servidor_configurado()
