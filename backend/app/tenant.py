"""Contexto de tenant para o isolamento multiempresa no PostgreSQL.

O isolamento real acontece no banco (RLS). Este módulo só faz uma coisa:
garantir que a transação declare `app.tenant_id` antes de qualquer consulta.

Como funciona:
1. `vincular_sessao(session, tenant_id)` registra o tenant no `session.info`.
2. O listener `after_begin` (registrado em `app/db.py`) executa
   `set_config('app.tenant_id', <uuid>, true)` no início de cada transação.
3. `SET LOCAL` vale só para a transação corrente — não vaza para a próxima
   nem para outra conexão do pool.

Sem contexto, `tenant_atual()` no banco devolve NULL e as policies não deixam
nenhuma linha passar. O padrão é fechar, não abrir.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Chave usada em Session.info e no SET LOCAL do PostgreSQL.
CHAVE_TENANT = "tenant_id"

# Usado por processos sem sessão HTTP (worker, jobs). O caminho de request
# usa `vincular_sessao`, que é mais seguro por ser local à sessão.
_tenant_contexto: ContextVar[UUID | None] = ContextVar("stellspy_tenant", default=None)


def definir_tenant_contexto(tenant_id: UUID | str | None) -> None:
    """Define o tenant para o código que não tem uma Session em mãos (workers)."""
    _tenant_contexto.set(UUID(str(tenant_id)) if tenant_id else None)


def obter_tenant_contexto() -> UUID | None:
    return _tenant_contexto.get()


def limpar_tenant_contexto() -> None:
    _tenant_contexto.set(None)


def vincular_sessao(session: Session, tenant_id: UUID | str) -> None:
    """
    Associa a sessão a um tenant e aplica o contexto imediatamente.

    Precisa ser chamado assim que o tenant é descoberto. Se já existe transação
    aberta (caso típico: o login acabou de ler a obra), o `set_config` é
    executado na hora, sem esperar a próxima transação.
    """
    tid = str(tenant_id)
    session.info[CHAVE_TENANT] = tid
    if session.in_transaction():
        session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": tid},
        )


def tenant_da_sessao(session: Session) -> str | None:
    valor = session.info.get(CHAVE_TENANT)
    return str(valor) if valor else None


def aplicar_contexto_na_conexao(connection: Any, tenant_id: UUID | str) -> None:
    """Aplica o contexto em uma conexão crua (usado pelo listener e por testes)."""
    connection.exec_driver_sql(
        "SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),)
    )


# ---------------------------------------------------------------------------
# Bootstrap: descobrir o tenant antes de existir contexto
# ---------------------------------------------------------------------------


def consultar_obra(session: Session, obra_id: UUID | str) -> dict[str, Any] | None:
    """
    Lê a obra pela função SECURITY DEFINER **sem** abrir contexto.

    Existe para o caminho autenticado por usuário: primeiro é preciso comparar
    o tenant da obra com o tenant da sessão e só depois abrir contexto. Abrir
    antes seria abrir o contexto errado, mesmo sem consultar nada.
    """
    row = session.execute(
        text("SELECT * FROM auth_lookup_obra(:id)"), {"id": str(obra_id)}
    ).mappings().first()
    return dict(row) if row else None


def resolver_tenant_de_obra(session: Session, obra_id: UUID | str) -> dict[str, Any] | None:
    """
    Lê a obra e vemcula a sessão ao tenant dela.

    Caminho legado (chave de obra / worker): a obra é a fonte do tenant porque
    não existe usuário autenticado.
    """
    dados = consultar_obra(session, obra_id)
    if dados is None:
        return None
    vincular_sessao(session, dados["tenant_id"])
    return dados


def consultar_contexto_nfe_log(session: Session, nfe_log_id: UUID | str) -> dict[str, Any] | None:
    """Descobre obra e tenant de um nfe_log **sem** abrir contexto."""
    row = session.execute(
        text("SELECT obra_id, tenant_id FROM auth_lookup_nfe_log_tenant(:id)"),
        {"id": str(nfe_log_id)},
    ).mappings().first()
    return dict(row) if row else None


def resolver_tenant_de_nfe_log(session: Session, nfe_log_id: UUID | str) -> UUID | None:
    """
    Descobre a que tenant pertence um `nfe_log` e abre o contexto.

    Retorna None quando o log não existe — o chamador decide o status HTTP.
    """
    ctx = consultar_contexto_nfe_log(session, nfe_log_id)
    if ctx is None:
        return None
    vincular_sessao(session, ctx["tenant_id"])
    return ctx["tenant_id"]
