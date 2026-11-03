import os
import time

import pytest

from app import pwa_session


def test_create_verify_roundtrip(monkeypatch):
    monkeypatch.setenv("PWA_SESSION_SECRET", "segredo-teste-32-chars-minimo-xx")
    oid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tok = pwa_session.create_session_token(oid, secret="segredo-teste-32-chars-minimo-xx", max_age=3600)
    assert pwa_session.verify_session_token(tok) == oid


def test_verify_rejeita_token_expirado(monkeypatch):
    monkeypatch.setenv("PWA_SESSION_SECRET", "segredo-teste-32-chars-minimo-xx")
    oid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tok = pwa_session.create_session_token(oid, secret="segredo-teste-32-chars-minimo-xx", max_age=-10)
    time.sleep(0.05)
    assert pwa_session.verify_session_token(tok) is None


def test_verify_rejeita_assinatura_errada(monkeypatch):
    monkeypatch.setenv("PWA_SESSION_SECRET", "segredo-teste-32-chars-minimo-xx")
    oid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    tok = pwa_session.create_session_token(oid, secret="segredo-teste-32-chars-minimo-xx", max_age=3600)
    tampered = tok[:-4] + "abcd"
    assert pwa_session.verify_session_token(tampered) is None


def test_verify_sem_secret_no_env(monkeypatch):
    monkeypatch.delenv("PWA_SESSION_SECRET", raising=False)
    assert pwa_session.verify_session_token("qualquer.coisa") is None
