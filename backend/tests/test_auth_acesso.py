import pytest
from fastapi import HTTPException

from app import auth_obra, pwa_session


@pytest.fixture
def obra():
    return {"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "api_key": "k-secret"}


def test_acesso_por_cookie_valido(monkeypatch, obra):
    monkeypatch.setattr(auth_obra, "SKIP_API_KEY", False)
    monkeypatch.setenv("PWA_SESSION_SECRET", "segredo-teste-32-chars-minimo-xx")
    tok = pwa_session.create_session_token(
        obra["id"], secret="segredo-teste-32-chars-minimo-xx", max_age=3600
    )
    auth_obra.verificar_acesso_obra(obra, x_api_key=None, pwa_session_cookie=tok)


def test_acesso_cookie_outra_obra_exige_header(monkeypatch, obra):
    monkeypatch.setattr(auth_obra, "SKIP_API_KEY", False)
    monkeypatch.setenv("PWA_SESSION_SECRET", "segredo-teste-32-chars-minimo-xx")
    outra = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    tok = pwa_session.create_session_token(
        outra, secret="segredo-teste-32-chars-minimo-xx", max_age=3600
    )
    with pytest.raises(HTTPException) as ei:
        auth_obra.verificar_acesso_obra(obra, x_api_key=None, pwa_session_cookie=tok)
    assert ei.value.status_code == 401
