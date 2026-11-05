"""Portão de entrada do painel, sem Streamlit — testável isoladamente.

Falha fechada: sem `DASHBOARD_PASSWORD` o painel não abre. Essa senha é do
painel e não deve ser a da role do banco (`STELLSPY_DASHBOARD_PASSWORD`) nem a
da API: reutilizar credencial amplia o alcance de um eventual vazamento.
"""

from __future__ import annotations

import hashlib
import hmac

MINIMO_SENHA = 12


def senha_configurada(valor: str | None) -> str | None:
    pwd = (valor or "").strip()
    return pwd or None


def motivo_recusa(valor: str | None) -> str | None:
    pwd = senha_configurada(valor)
    if pwd is None:
        return (
            "Defina `DASHBOARD_PASSWORD` para abrir o painel. Sem senha o "
            "painel não inicia — expor o dashboard sem autenticação não é opção."
        )
    if len(pwd) < MINIMO_SENHA:
        return (
            f"`DASHBOARD_PASSWORD` tem {len(pwd)} caracteres; use ao menos "
            f"{MINIMO_SENHA}. Gere um valor aleatório e dedicado ao painel."
        )
    return None


def senha_confere(informada: str, esperada: str) -> bool:
    """Compara digests de tamanho fixo em tempo constante."""
    return hmac.compare_digest(
        hashlib.sha256((informada or "").encode()).digest(),
        hashlib.sha256(esperada.encode()).digest(),
    )
