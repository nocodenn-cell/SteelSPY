"""Login, logout e identidade corrente.

O cookie de sessão é HttpOnly e assinado; o de CSRF é legível pelo JavaScript
por necessidade (double submit) e por isso não carrega nada sensível — é um
valor derivado do `jti`, que o site de terceiro não consegue ler nem adivinhar.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth_usuario import (
    COOKIE_CSRF,
    COOKIE_SESSAO,
    CredenciaisInvalidas,
    SessaoAtual,
    TenantAmbiguo,
    abrir_sessao,
    autenticar,
    revogar,
    validade_sessao_segundos,
)
from app.db import get_db
from app.deps import sessao_atual
from app.pwa_session import cookie_samesite, cookie_secure_flag
from app.seguranca import TokenInvalido, ler_token_sessao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    senha: str = Field(..., min_length=1, max_length=512)
    tenant: str | None = Field(
        None, max_length=63, description="Slug da construtora, quando o e-mail existe em mais de uma"
    )


def _aplicar_cookies(response: Response, token: str, csrf: str) -> None:
    comum = {
        "max_age": validade_sessao_segundos(),
        "secure": cookie_secure_flag(),
        "samesite": cookie_samesite(),
        "path": "/",
    }
    response.set_cookie(key=COOKIE_SESSAO, value=token, httponly=True, **comum)
    # Precisa ser legível pelo JS para o double submit. Não é segredo: é derivado
    # do jti + segredo do servidor, e o valor sozinho não autentica nada.
    response.set_cookie(key=COOKIE_CSRF, value=csrf, httponly=False, **comum)


@router.post("/login")
def post_login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        sessao = autenticar(
            db, email=body.email, senha=body.senha, tenant_slug=body.tenant
        )
    except TenantAmbiguo as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CredenciaisInvalidas as exc:
        # Mesma resposta para e-mail inexistente e senha errada.
        logger.warning("tentativa de login falhou: email=%s", body.email[:64])
        raise HTTPException(status_code=401, detail="Credenciais inválidas.") from exc

    token, csrf = abrir_sessao(
        db,
        sessao,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _aplicar_cookies(response, token, csrf)

    return {
        "ok": True,
        "csrf_token": csrf,
        "expira_em": sessao.expira_em.isoformat(),
        "usuario": {
            "id": str(sessao.usuario_id),
            "nome": sessao.nome,
            "email": sessao.email,
            "tenant_id": str(sessao.tenant_id),
            "papel_global": sessao.papel_global,
        },
    }


@router.post("/logout")
def post_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    token = request.cookies.get(COOKIE_SESSAO)
    if token:
        try:
            dados = ler_token_sessao(token)
            revogar(db, dados["jti"], motivo="logout")
        except TokenInvalido:
            # Cookie já inválido: o efeito desejado (não autenticar) já está garantido.
            pass

    comum = {"path": "/", "secure": cookie_secure_flag(), "samesite": cookie_samesite()}
    response.delete_cookie(COOKIE_SESSAO, httponly=True, **comum)
    response.delete_cookie(COOKIE_CSRF, httponly=False, **comum)
    return {"ok": True}


@router.get("/eu")
def get_eu(sessao: SessaoAtual = Depends(sessao_atual)) -> dict[str, object]:
    """Identidade reconstruída do banco — não do cookie."""
    return {
        "usuario_id": str(sessao.usuario_id),
        "nome": sessao.nome,
        "email": sessao.email,
        "tenant_id": str(sessao.tenant_id),
        "papel_global": sessao.papel_global,
        "expira_em": sessao.expira_em.isoformat(),
    }
