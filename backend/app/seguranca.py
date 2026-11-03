"""Primitivas de segurança: senha, token de sessão e CSRF.

Tudo aqui é stdlib. Nenhuma dependência nova foi adicionada — a política de
dependências (ADR-010) continua valendo.

Modelo do token de sessão
-------------------------
O cookie carrega **apenas** um identificador opaco (`jti`) e a expiração,
assinados com HMAC-SHA256. Usuário, tenant e papel **não** vão no token: vêm
do banco a cada requisição (`auth_validar_sessao`).

Isso resolve três problemas de uma vez:

- o navegador não consegue trocar de tenant nem de papel (não há campo para isso);
- mudança de papel ou desligamento de usuário valem imediatamente, sem esperar
  o token expirar;
- logout revoga de verdade, porque a fonte da verdade é a tabela `sessoes`.

Um token autocontido com `tenant_id` e `papel` assinados seria mais simples —
e errado: ficaria válido até expirar mesmo após revogação.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

# Parâmetros do scrypt. N=2^14 (~16 ms por verificação em CPU comum) é o piso
# recomendado para senha de usuário e mantém o login abaixo de 100 ms.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_PREFIXO = "scrypt"


def _b64e(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def _b64d(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# ---------------------------------------------------------------------------
# Senha
# ---------------------------------------------------------------------------


def hash_senha(senha: str) -> str:
    """
    Gera `scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>`.

    Os parâmetros vão junto para permitir endurecer o custo no futuro sem
    invalidar as senhas já cadastradas.
    """
    if not senha:
        raise ValueError("senha vazia")
    salt = secrets.token_bytes(16)
    derivada = hashlib.scrypt(
        senha.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_DKLEN
    )
    return f"{_PREFIXO}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(derivada)}"


def verificar_senha(senha: str, armazenado: str | None) -> bool:
    """Comparação em tempo constante. Hash ausente ou malformado nunca autentica."""
    if not senha or not armazenado:
        return False
    try:
        prefixo, n, r, p, salt_b64, hash_b64 = armazenado.split("$")
        if prefixo != _PREFIXO:
            return False
        derivada = hashlib.scrypt(
            senha.encode("utf-8"),
            salt=_b64d(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_b64d(hash_b64)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada, _b64d(hash_b64))


# ---------------------------------------------------------------------------
# Token de sessão
# ---------------------------------------------------------------------------


class TokenInvalido(ValueError):
    """Assinatura, formato ou expiração inválidos."""


def _segredo() -> str:
    segredo = (os.getenv("PWA_SESSION_SECRET") or "").strip()
    if not segredo:
        raise RuntimeError("PWA_SESSION_SECRET não definido — sessão insegura")
    return segredo


def _assinar(corpo: str, segredo: str) -> str:
    return hmac.new(segredo.encode("utf-8"), corpo.encode("ascii"), hashlib.sha256).hexdigest()


def criar_token_sessao(jti: str, *, expira_em: int, segredo: str | None = None) -> str:
    """Monta `base64url(payload).hmac`. Payload tem só jti e exp."""
    segredo = segredo or _segredo()
    payload = {"jti": jti, "exp": int(expira_em)}
    corpo = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{corpo}.{_assinar(corpo, segredo)}"


def ler_token_sessao(token: str | None, *, segredo: str | None = None) -> dict[str, Any]:
    """Valida a assinatura e a expiração. Não consulta o banco."""
    if not token or "." not in token:
        raise TokenInvalido("token ausente ou malformado")
    segredo = segredo or _segredo()
    try:
        corpo, assinatura = token.rsplit(".", 1)
        esperada = _assinar(corpo, segredo)
        if not hmac.compare_digest(esperada, assinatura):
            raise TokenInvalido("assinatura inválida")
        dados = json.loads(_b64d(corpo).decode("utf-8"))
    except TokenInvalido:
        raise
    except Exception as exc:  # noqa: BLE001 - qualquer falha de parsing é token inválido
        raise TokenInvalido("token ilegível") from exc

    if int(dados.get("exp", 0)) < int(time.time()):
        raise TokenInvalido("sessão expirada")
    if not dados.get("jti"):
        raise TokenInvalido("token sem identificador de sessão")
    return dados


# ---------------------------------------------------------------------------
# CSRF (double submit)
# ---------------------------------------------------------------------------


def token_csrf(jti: str, *, segredo: str | None = None) -> str:
    """
    Deriva o token CSRF do `jti` e do segredo.

    Não precisa de armazenamento: o servidor recalcula e compara. O valor é
    entregue em cookie legível pelo JavaScript e o cliente devolve no header
    `X-CSRF-Token`. Um site terceiro não consegue ler o cookie (mesma origem),
    então não consegue montar o header.
    """
    segredo = segredo or _segredo()
    return hmac.new(
        segredo.encode("utf-8"), f"csrf:{jti}".encode("ascii"), hashlib.sha256
    ).hexdigest()[:40]


def csrf_valido(jti: str, recebido: str | None, *, segredo: str | None = None) -> bool:
    if not recebido:
        return False
    return hmac.compare_digest(token_csrf(jti, segredo=segredo), str(recebido).strip())
