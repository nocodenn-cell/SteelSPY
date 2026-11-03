"""Login, logout e identidade corrente.

O cookie de sessão é HttpOnly e assinado; o de CSRF é legível pelo JavaScript
por necessidade (double submit) e por isso não carrega nada sensível — é um
valor derivado do `jti`, que o site de terceiro não consegue ler nem adivinhar.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_usuario import (
    COOKIE_CSRF,
    COOKIE_SESSAO,
    CredenciaisInvalidas,
    SessaoAtual,
    TenantAmbiguo,
    abrir_contexto,
    abrir_sessao,
    autenticar,
    revogar,
    validade_sessao_segundos,
)
from app.autorizacao import acoes_permitidas
from app.db import get_db
from app.deps import sessao_atual
from app.limite_tentativas import chave_email, chave_ip, limite
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
    ip = request.client.host if request.client else None

    # Duas chaves independentes: alvo (e-mail) e origem (IP). Basta uma estar
    # bloqueada para recusar — ataque direcionado e varredura são riscos
    # diferentes e merecem contadores diferentes.
    chaves = (chave_email(body.email), chave_ip(ip))
    for chave in chaves:
        bloqueado, restante = limite().bloqueado(chave)
        if bloqueado:
            logger.warning("login bloqueado por excesso de tentativas: %s", chave.split(":")[0])
            raise HTTPException(
                status_code=429,
                detail="Muitas tentativas de login. Aguarde e tente novamente.",
                headers={"Retry-After": str(restante)},
            )

    try:
        sessao = autenticar(
            db, email=body.email, senha=body.senha, tenant_slug=body.tenant
        )
    except TenantAmbiguo as exc:
        # Conta como falha de propósito: responder diferente de "senha errada"
        # já revela que o e-mail existe.
        for chave in chaves:
            limite().registrar_falha(chave)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CredenciaisInvalidas as exc:
        for chave in chaves:
            limite().registrar_falha(chave)
        logger.warning("tentativa de login falhou: email=%s", body.email[:64])
        raise HTTPException(status_code=401, detail="Credenciais inválidas.") from exc

    # Sucesso zera o histórico das duas chaves.
    for chave in chaves:
        limite().limpar(chave)

    token, csrf = abrir_sessao(
        db,
        sessao,
        ip=ip,
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


@router.get("/obras")
def get_minhas_obras(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """
    Obras em que a pessoa tem vínculo, com o papel e as ações permitidas nela.

    Serve a uma coisa só: o celular não precisa adivinhar o que mostrar. Quem não
    tem vínculo com a obra nem vê a obra na lista — e a permissão efetiva continua
    sendo a interseção dos dois papéis, calculada aqui, no servidor.

    O cliente usa isso para esconder botão; o servidor usa a mesma matriz para
    autorizar. Esconder não é autorizar.
    """
    sessao = sessao_atual(request, db)
    abrir_contexto(db, sessao)

    vinculos = db.execute(
        text("""
            SELECT o.id, o.nome, o.modo_aprendizado, ou.papel
            FROM obras o
            JOIN obra_usuarios ou ON ou.obra_id = o.id AND ou.tenant_id = o.tenant_id
            WHERE ou.usuario_id = :u
            ORDER BY o.nome
        """),
        {"u": str(sessao.usuario_id)},
    ).mappings().all()

    return {
        "itens": [
            {
                "id": str(v["id"]),
                "nome": v["nome"],
                "modo_aprendizado": v["modo_aprendizado"],
                "papel_na_obra": v["papel"],
                "acoes": acoes_permitidas(
                    papel_global=sessao.papel_global, papel_obra=v["papel"]
                ),
            }
            for v in vinculos
        ]
    }
