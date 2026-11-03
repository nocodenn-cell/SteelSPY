import logging
from unittest.mock import patch

import httpx
import pytest

from app.services import whatsapp_evolution as we


@pytest.fixture(autouse=True)
def _limpar_env_evolution(monkeypatch):
    for k in (
        "WHATSAPP_DISABLED",
        "EVOLUTION_API_BASE_URL",
        "EVOLUTION_API_KEY",
        "EVOLUTION_INSTANCE_NAME",
        "WHATSAPP_ALERT_NUMBER",
        "EVOLUTION_MAX_TENTATIVAS",
        "EVOLUTION_BACKOFF_BASE_SEGUNDOS",
    ):
        monkeypatch.delenv(k, raising=False)


def test_evolution_pode_enviar_false_sem_variaveis():
    assert we.evolution_pode_enviar() is False


def test_evolution_pode_enviar_false_quando_whatsapp_disabled(monkeypatch):
    monkeypatch.setenv("WHATSAPP_DISABLED", "1")
    monkeypatch.setenv("EVOLUTION_API_BASE_URL", "https://exemplo.com")
    monkeypatch.setenv("EVOLUTION_API_KEY", "k")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "i")
    assert we.evolution_pode_enviar() is False


def test_evolution_pode_enviar_true_servidor_configurado(monkeypatch):
    monkeypatch.setenv("EVOLUTION_API_BASE_URL", "https://exemplo.com")
    monkeypatch.setenv("EVOLUTION_API_KEY", "k")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "minha-inst")
    assert we.evolution_pode_enviar() is True


def test_resolver_prefere_numero_da_obra_sobre_fallback_global(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ALERT_NUMBER", "5511111111111")
    n = we.resolver_destino_whatsapp(
        "00000000-0000-0000-0000-000000000001",
        "5522222222222",
        usar_coluna_obra_no_banco=False,
    )
    assert n == "5522222222222"


@patch("app.services.whatsapp_evolution.httpx.post")
def test_enviar_texto_evolution_post_headers_e_json(mock_post, monkeypatch):
    monkeypatch.setenv("EVOLUTION_API_BASE_URL", "https://api.evolution.test")
    monkeypatch.setenv("EVOLUTION_API_KEY", "secret-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "inst-1")

    req = httpx.Request("POST", "https://api.evolution.test/message/sendText/inst-1")
    mock_post.return_value = httpx.Response(201, request=req)

    assert we._enviar_texto_evolution("5511888777666", "Olá") is True

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.evolution.test/message/sendText/inst-1"
    assert kwargs["headers"]["apikey"] == "secret-key"
    assert kwargs["json"] == {"number": "5511888777666", "text": "Olá"}


@patch("app.services.whatsapp_evolution.time.sleep", lambda *_a, **_k: None)
@patch("app.services.whatsapp_evolution.httpx.post")
def test_resiliencia_reintenta_apos_503(mock_post, monkeypatch):
    monkeypatch.setenv("EVOLUTION_API_BASE_URL", "https://api.evolution.test")
    monkeypatch.setenv("EVOLUTION_API_KEY", "secret-key")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "inst-1")
    monkeypatch.setenv("EVOLUTION_MAX_TENTATIVAS", "3")
    monkeypatch.setenv("EVOLUTION_BACKOFF_BASE_SEGUNDOS", "0")

    req = httpx.Request("POST", "https://api.evolution.test/message/sendText/inst-1")
    mock_post.side_effect = [
        httpx.Response(503, request=req),
        httpx.Response(201, request=req),
    ]

    assert we._enviar_texto_com_resiliencia("5511999999999", "msg") is True
    assert mock_post.call_count == 2


def test_notificar_mensagem_fiscal_sem_config_apenas_log(caplog, monkeypatch):
    monkeypatch.delenv("EVOLUTION_API_BASE_URL", raising=False)
    with caplog.at_level(logging.INFO, logger="app.services.whatsapp_evolution"):
        we.notificar_mensagem_fiscal("obra-uuid", "1" * 44, "texto fiscal")
    assert "WhatsApp desligado" in caplog.text
    assert "obra-uuid" in caplog.text
