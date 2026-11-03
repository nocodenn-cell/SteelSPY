"""
Sessão SQLAlchemy (sync). Defina DATABASE_URL no ambiente.

Além do engine, este módulo instala o listener que aplica o contexto de tenant
(`app.tenant_id`) no início de cada transação. Sem esse contexto, o RLS não tem
como saber de qual construtora é a requisição — e, por segurança, nenhuma linha
é visível.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.tenant import CHAVE_TENANT, aplicar_contexto_na_conexao

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


@event.listens_for(Session, "after_begin")
def _aplicar_tenant_na_transacao(session: Session, transaction, connection) -> None:
    """
    Executa `set_config('app.tenant_id', ..., true)` no início de cada transação.

    O `true` final é escopo local: o valor morre com a transação, não vaza para
    a próxima nem para outra conexão do pool. Se a sessão não tem tenant, nada
    é executado e as policies negam tudo.
    """
    tenant = session.info.get(CHAVE_TENANT)
    if tenant:
        aplicar_contexto_na_conexao(connection, tenant)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
