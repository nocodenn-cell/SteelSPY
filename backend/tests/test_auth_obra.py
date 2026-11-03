import pytest
from fastapi import HTTPException

from app import auth_obra


def test_verificar_api_key_aceita_quando_igual(monkeypatch):
    monkeypatch.setattr(auth_obra, "SKIP_API_KEY", False)
    auth_obra.verificar_api_key_obra({"api_key": "minha-chave-piloto"}, "minha-chave-piloto")


def test_verificar_api_key_rejeita_chave_errada(monkeypatch):
    monkeypatch.setattr(auth_obra, "SKIP_API_KEY", False)
    with pytest.raises(HTTPException) as ei:
        auth_obra.verificar_api_key_obra({"api_key": "segredo"}, "outra")
    assert ei.value.status_code == 403


def test_verificar_api_key_exige_header(monkeypatch):
    monkeypatch.setattr(auth_obra, "SKIP_API_KEY", False)
    with pytest.raises(HTTPException) as ei:
        auth_obra.verificar_api_key_obra({"api_key": "x"}, None)
    assert ei.value.status_code == 401
