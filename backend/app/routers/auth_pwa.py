"""
Login PWA: envia API key uma vez; a API devolve cookie HttpOnly assinado.
Demais rotas aceitam sessão válida para a mesma obra ou header X-API-KEY (integrações).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth_obra import verificar_api_key_obra
from app.db import get_db
from app.pwa_session import (
    SESSION_COOKIE_NAME,
    cookie_secure_flag,
    cookie_samesite,
    create_session_token,
    get_session_secret,
    session_max_age_seconds,
    verify_session_token,
)
from app.services.conferencia_persist import carregar_obra_por_id

router = APIRouter(prefix="/auth/pwa", tags=["auth-pwa"])


class PwaLoginBody(BaseModel):
    obra_id: UUID
    api_key: str = Field(..., min_length=1, max_length=512)


@router.post("/login")
def post_pwa_login(
    body: PwaLoginBody,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, str | bool]:
    secret = get_session_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Login por sessão indisponível: defina PWA_SESSION_SECRET no servidor.",
        )
    obra = carregar_obra_por_id(db, body.obra_id)
    verificar_api_key_obra(obra, body.api_key)
    max_age = session_max_age_seconds()
    token = create_session_token(str(body.obra_id), secret=secret, max_age=max_age)
    ss = cookie_samesite()
    secure = cookie_secure_flag()
    if ss == "none" and not secure:
        raise HTTPException(
            status_code=503,
            detail="Cookie cross-site (PWA_COOKIE_SAMESITE=none) exige PWA_COOKIE_SECURE=1.",
        )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite=ss,  # type: ignore[arg-type]
        path="/",
    )
    return {"ok": True, "obra_id": str(body.obra_id)}


@router.get("/session")
def get_pwa_session(
    pwa_session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict[str, bool | str]:
    """
    Valida o cookie HttpOnly sem expor a API key no cliente.
    O PWA pode chamar ao carregar para exibir “sessão ativa” após F5.
    """
    oid = verify_session_token(pwa_session_cookie)
    if not oid:
        raise HTTPException(status_code=401, detail="Sem sessão ativa")
    return {"ok": True, "obra_id": oid}


@router.post("/logout")
def post_pwa_logout(response: Response) -> dict[str, bool]:
    ss = cookie_samesite()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=cookie_secure_flag(),
        samesite=ss,  # type: ignore[arg-type]
    )
    return {"ok": True}
