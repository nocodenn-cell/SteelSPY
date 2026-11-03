"""Dependências HTTP de autenticação e autorização.

Regra única que este módulo faz cumprir:

    identidade vem da sessão; permissão vem do banco; nada vem do corpo da requisição.

O cliente pode enviar `obra_id`, `usuario_id`, `tenant_id`, `papel` — nada disso
é lido como verdade. `tenant_id` sai sempre da sessão; `papel` sai sempre do
banco; `usuario_id` sai sempre da sessão.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth_usuario import (
    COOKIE_SESSAO,
    SessaoAtual,
    papel_na_obra,
    validar_token,
)
from app.autorizacao import pode_executar
from app.db import get_db
from app.seguranca import csrf_valido

NOME_HEADER_CSRF = "X-CSRF-Token"


def _token_da_sessao(request: Request) -> str | None:
    return request.cookies.get(COOKIE_SESSAO)


def sessao_do_request(request: Request, db: Session) -> SessaoAtual | None:
    """
    Sessão de usuário do cookie, ou None.

    Cookie presente e inválido → 401 imediato. Não cai silenciosamente para o
    fluxo legado: quem apresentou credencial de usuário recebe a resposta sobre
    ela, em vez de ser rebaixado para um caminho com menos garantias.
    """
    token = _token_da_sessao(request)
    if not token:
        return None
    sessao = validar_token(db, token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")
    return sessao


def sessao_opcional(
    request: Request,
    db: Session = Depends(get_db),
) -> SessaoAtual | None:
    """Para rotas que aceitam usuário autenticado **ou** o fluxo legado por obra."""
    return sessao_do_request(request, db)


def sessao_atual(
    request: Request,
    db: Session = Depends(get_db),
) -> SessaoAtual:
    """Para rotas que exigem identidade de usuário. Sem sessão → 401."""
    sessao = sessao_do_request(request, db)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Autenticação de usuário obrigatória.")
    return sessao


def exigir_csrf(request: Request, sessao: SessaoAtual | None) -> None:
    """
    Double submit: o token do header precisa casar com o derivado do `jti`.

    Só se aplica a requisição autenticada por cookie. Requisição com
    `X-API-KEY` não carrega credencial ambiente e por isso não é alvo de CSRF.
    """
    if sessao is None:
        return
    recebido = request.headers.get(NOME_HEADER_CSRF)
    if not csrf_valido(str(sessao.jti), recebido):
        raise HTTPException(
            status_code=403,
            detail=f"Token CSRF ausente ou inválido (header {NOME_HEADER_CSRF}).",
        )


def autorizar_na_obra(
    db: Session,
    sessao: SessaoAtual,
    obra_id: Any,
    acao: str,
) -> str:
    """
    Verifica vínculo do usuário com a obra e a matriz de papéis.

    Levanta 403 quando a ação não é permitida para o par (papel global, papel na
    obra). Devolve o papel na obra, para quem quiser registrar no log.
    """
    papel = papel_na_obra(db, sessao, obra_id)
    if papel is None:
        raise HTTPException(status_code=403, detail="Usuário sem vínculo com esta obra.")
    if not pode_executar(acao, papel_global=sessao.papel_global, papel_obra=papel):
        raise HTTPException(
            status_code=403,
            detail=f"Ação '{acao}' não permitida para o papel '{sessao.papel_global}' nesta obra.",
        )
    return papel


def usar_chave_de_obra(
    x_api_key: str | None = Header(None, alias="X-API-KEY"),
) -> str | None:
    """Apenas documento a presença do header; a validação é feita pelo fluxo legado."""
    return x_api_key
