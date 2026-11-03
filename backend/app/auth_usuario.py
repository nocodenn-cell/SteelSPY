"""Serviço de sessão de usuário.

Separação de responsabilidades:

- `app.seguranca` sabe criptografia (senha, assinatura, CSRF) e não sabe SQL;
- este módulo sabe o ciclo de vida da sessão (autenticar, abrir, validar,
  revogar) e não sabe HTTP;
- `app/routers/auth_usuario` traduz HTTP para este serviço.

A identidade autenticada é sempre reconstruída do banco. Nada que o navegador
envia — além do `jti` assinado — é aceito como verdade.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.seguranca import (
    TokenInvalido,
    criar_token_sessao,
    ler_token_sessao,
    token_csrf,
    verificar_senha,
)
from app.tenant import vincular_sessao

logger = logging.getLogger(__name__)

COOKIE_SESSAO = "stellspy_sessao"
COOKIE_CSRF = "stellspy_csrf"

VALIDADE_PADRAO_SEGUNDOS = 12 * 60 * 60  # 12 h


class CredenciaisInvalidas(Exception):
    """E-mail/senha errados, usuário inativo ou tenant inativo."""


class TenantAmbiguo(Exception):
    """Mesmo e-mail existe em mais de uma construtora; é preciso informar qual."""


@dataclass(frozen=True)
class SessaoAtual:
    jti: UUID
    usuario_id: UUID
    tenant_id: UUID
    papel_global: str
    nome: str
    email: str
    expira_em: datetime


def validade_sessao_segundos() -> int:
    bruto = (os.getenv("AUTH_SESSION_MAX_AGE_SECONDS") or "").strip()
    if bruto.isdigit():
        return max(300, min(int(bruto), 60 * 60 * 24))
    return VALIDADE_PADRAO_SEGUNDOS


def _ip_valido(bruto: str | None) -> str | None:
    if not bruto:
        return None
    try:
        ipaddress.ip_address(bruto.strip())
    except ValueError:
        return None
    return bruto.strip()


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------


def autenticar(
    db: Session,
    *,
    email: str,
    senha: str,
    tenant_slug: str | None = None,
) -> SessaoAtual:
    """
    Valida credenciais e devolve a identidade — sem criar sessão ainda.

    Levanta `CredenciaisInvalidas` em qualquer falha, com a mesma exceção para
    e-mail inexistente e senha errada: não se revela qual dos dois falhou.
    """
    candidatos = db.execute(
        text("SELECT * FROM auth_login_lookup(:e)"), {"e": (email or "").strip()}
    ).mappings().all()

    if tenant_slug:
        alvo = tenant_slug.strip().lower()
        candidatos = [c for c in candidatos if (c["tenant_slug"] or "").lower() == alvo]

    ativos = [c for c in candidatos if c["usuario_ativo"] and c["tenant_ativo"]]

    if len(candidatos) > 1 and len(ativos) > 1:
        raise TenantAmbiguo(
            "Este e-mail existe em mais de uma construtora. Informe o identificador da construtora."
        )

    if len(ativos) != 1:
        raise CredenciaisInvalidas("credenciais inválidas")

    escolhido = ativos[0]
    if not verificar_senha(senha, escolhido["senha_hash"]):
        raise CredenciaisInvalidas("credenciais inválidas")

    expira = datetime.fromtimestamp(
        int(time.time()) + validade_sessao_segundos(), tz=timezone.utc
    )
    return SessaoAtual(
        jti=uuid4(),
        usuario_id=escolhido["usuario_id"],
        tenant_id=escolhido["tenant_id"],
        papel_global=escolhido["papel_global"],
        nome=escolhido["nome"],
        email=email.strip(),
        expira_em=expira,
    )


def abrir_sessao(
    db: Session,
    sessao: SessaoAtual,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """
    Grava a sessão e devolve `(token_do_cookie, token_csrf)`.

    O INSERT passa pelo RLS, então o contexto do tenant precisa estar aberto —
    é o único ponto do fluxo de login em que abrimos contexto antes da resposta.
    """
    vincular_sessao(db, sessao.tenant_id)
    db.execute(
        text("""
            INSERT INTO sessoes (id, tenant_id, usuario_id, expira_em, ip, user_agent)
            VALUES (:id, :tenant, :usuario, :expira, CAST(:ip AS inet), :ua)
        """),
        {
            "id": str(sessao.jti),
            "tenant": str(sessao.tenant_id),
            "usuario": str(sessao.usuario_id),
            "expira": sessao.expira_em,
            "ip": _ip_valido(ip),
            "ua": (user_agent or "")[:500] or None,
        },
    )
    db.execute(
        text("UPDATE usuarios SET ultimo_login = NOW() WHERE id = :id"),
        {"id": str(sessao.usuario_id)},
    )

    token = criar_token_sessao(str(sessao.jti), expira_em=int(sessao.expira_em.timestamp()))
    return token, token_csrf(str(sessao.jti))


# ---------------------------------------------------------------------------
# Validação (a cada requisição)
# ---------------------------------------------------------------------------


def validar_token(db: Session, token: str | None) -> SessaoAtual | None:
    """
    Reconstroi a sessão a partir do cookie.

    Retorna None para qualquer situação inválida — assinatura, expiração,
    revogação, usuário inativo, tenant inativo. Não distingue os casos para
    quem chama de fora; o log registra o motivo.
    """
    try:
        dados = ler_token_sessao(token)
    except TokenInvalido as exc:
        logger.info("sessão rejeitada: %s", exc)
        return None

    jti = dados["jti"]
    try:
        jti_uuid = UUID(str(jti))
    except ValueError:
        logger.warning("sessão com jti não-UUID rejeitada")
        return None

    row = db.execute(
        text("SELECT * FROM auth_validar_sessao(:jti)"), {"jti": str(jti_uuid)}
    ).mappings().first()
    if row is None:
        logger.info("sessão inexistente: %s", jti_uuid)
        return None

    if row["revogada"]:
        logger.info("sessão revogada: %s", jti_uuid)
        return None
    if not row["usuario_ativo"] or not row["tenant_ativo"]:
        logger.warning("sessão de usuário/tenant inativo: %s", jti_uuid)
        return None

    expira_em: datetime = row["expira_em"]
    if expira_em.tzinfo is None:
        expira_em = expira_em.replace(tzinfo=timezone.utc)
    if expira_em < datetime.now(timezone.utc):
        logger.info("sessão expirada no banco: %s", jti_uuid)
        return None

    return SessaoAtual(
        jti=jti_uuid,
        usuario_id=row["usuario_id"],
        tenant_id=row["tenant_id"],
        papel_global=row["papel_global"],
        nome=row["nome"],
        email=row["email"],
        expira_em=expira_em,
    )


def revogar(db: Session, jti: UUID | str, *, motivo: str = "logout") -> bool:
    """Revoga a sessão no servidor. Funciona mesmo sem contexto de tenant."""
    resultado = db.execute(
        text("SELECT auth_revogar_sessao(:jti, :motivo)"),
        {"jti": str(jti), "motivo": motivo[:200]},
    ).scalar()
    db.commit()
    return bool(resultado)


# ---------------------------------------------------------------------------
# Autorização por obra
# ---------------------------------------------------------------------------


def papel_na_obra(db: Session, sessao: SessaoAtual, obra_id: UUID | str) -> str | None:
    """Papel do usuário naquela obra, ou None se não houver vínculo."""
    return db.execute(
        text("SELECT auth_papel_na_obra(:u, :o)"),
        {"u": str(sessao.usuario_id), "o": str(obra_id)},
    ).scalar()


def abrir_contexto(db: Session, sessao: SessaoAtual) -> None:
    """Abre o contexto de tenant da sessão autenticada (nunca o do corpo da requisição)."""
    vincular_sessao(db, sessao.tenant_id)


def contexto_para_log(sessao: SessaoAtual) -> dict[str, Any]:
    return {"usuario_id": str(sessao.usuario_id), "tenant_id": str(sessao.tenant_id)}
