"""Fixtures de integração: PostgreSQL real, RLS ligado, role de aplicação.

Estes testes NÃO usam mocks de banco. O ponto do isolamento multiempresa é que
ele acontece no PostgreSQL, não no Python — então o teste precisa de um servidor
de verdade, conectado com a role que a aplicação usaria.

Container esperado (já criado no ambiente de desenvolvimento):

    docker run -d --name stellspy-pg \
      -e POSTGRES_PASSWORD=stellspy_dev \
      -e POSTGRES_USER=stellspy_owner \
      -e POSTGRES_DB=stellspy -p 55432:5432 postgres:16-alpine

Se o banco não estiver acessível, os testes são pulados com a instrução acima —
nunca silenciosamente aprovados.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import pathlib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Importar `app.db` é o que registra o listener `after_begin` que injeta
# `app.tenant_id` em cada transação. Sem este import, a sessão de teste não
# teria o comportamento da aplicação — e o teste de isolamento passaria a
# medir outra coisa.
import app.db  # noqa: F401  (efeito colateral necessário)

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]
DIR_MIGRACOES = RAIZ_BACKEND.parent / "supabase" / "migrations"

URL_OWNER = os.getenv(
    "STELLSPY_TEST_DB_OWNER",
    "postgresql+psycopg2://stellspy_owner:stellspy_dev@localhost:55432/stellspy",
)
URL_APP = os.getenv(
    "STELLSPY_TEST_DB_APP",
    "postgresql+psycopg2://stellspy_app:stellspy_app_dev_only@localhost:55432/stellspy",
)


def _carregar_runner():
    caminho = RAIZ_BACKEND / "scripts" / "apply_migrations.py"
    spec = importlib.util.spec_from_file_location("_apply_migrations", caminho)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def sql_owner() -> Iterator[Any]:
    """Engine com a role dona (superuser no container) — uso restrito a preparação."""
    engine = create_engine(URL_OWNER, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexão vira skip
        pytest.skip(
            "PostgreSQL de testes inacessível. Suba o container com:\n"
            "  docker run -d --name stellspy-pg -e POSTGRES_PASSWORD=stellspy_dev "
            "-e POSTGRES_USER=stellspy_owner -e POSTGRES_DB=stellspy -p 55432:5432 "
            f"postgres:16-alpine\nErro: {type(exc).__name__}: {exc}"
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def banco_limpo(sql_owner: Any) -> Iterator[Any]:
    """Recria o schema public e aplica todas as migrações do zero."""
    with sql_owner.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    runner = _carregar_runner()
    codigo = runner.main(["--url", URL_OWNER, "--dir", str(DIR_MIGRACOES)])
    assert codigo == 0, "as migrações falharam ao aplicar em banco limpo"
    yield sql_owner


@pytest.fixture(scope="session")
def sql_app(banco_limpo: Any) -> Iterator[Any]:
    """Engine com a role de aplicação: sem BYPASSRLS, sujeita às policies."""
    engine = create_engine(URL_APP, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def sessao_app_factory(sql_app: Any) -> sessionmaker:
    """Sessionmaker igual ao da aplicação (dispara o listener after_begin)."""
    return sessionmaker(bind=sql_app, autocommit=False, autoflush=False, class_=Session)


@pytest.fixture(scope="session", autouse=True)
def _garantir_banco_pronto(banco_limpo: Any) -> Iterator[None]:
    """Garante schema limpo + migrações aplicadas antes de qualquer teste do diretório."""
    yield


@pytest.fixture(scope="session")
def runner_migracoes() -> Any:
    return _carregar_runner()


@pytest.fixture(scope="session")
def caminho_migracoes() -> pathlib.Path:
    return DIR_MIGRACOES


@pytest.fixture(scope="session")
def url_owner() -> str:
    return URL_OWNER


@pytest.fixture()
def abrir_como(sql_app: Any) -> Any:
    """
    Devolve um context manager que abre uma transação já com o tenant definido.

    `set_config(..., true)` = escopo local: vale só até o fim da transação.
    """

    @contextlib.contextmanager
    def _abrir(tenant_id: uuid.UUID | None) -> Iterator[Any]:
        with sql_app.connect() as conn:
            with conn.begin():
                if tenant_id is not None:
                    conn.execute(
                        text("SELECT set_config('app.tenant_id', :t, true)"),
                        {"t": str(tenant_id)},
                    )
                yield conn

    return _abrir


@pytest.fixture()
def cenario(sql_owner: Any, banco_limpo: Any) -> dict[str, Any]:
    """
    Duas construtoras completas, com obra, usuário, vínculo e nfe_log cada uma.

    Os dados são gravados com a role dona de propósito: o RLS é do teste, não
    da preparação. Cada execução usa UUIDs novos, então não há colisão.
    """
    ids = {
        "tenant_a": uuid.uuid4(),
        "tenant_b": uuid.uuid4(),
        "obra_a": uuid.uuid4(),
        "obra_b": uuid.uuid4(),
        "usuario_a": uuid.uuid4(),
        "usuario_b": uuid.uuid4(),
        "nfe_a": uuid.uuid4(),
        "nfe_b": uuid.uuid4(),
    }

    # CNPJ da construtora tem índice único: cada execução precisa do seu,
    # senão o segundo teste a usar a fixture quebra na inserção.
    cnpj_a = f"{uuid.uuid4().int % 10**14:014d}"
    cnpj_b = f"{uuid.uuid4().int % 10**14:014d}"
    # api_key da obra também tem índice único.
    chave_a = f"alfa-{uuid.uuid4().hex[:16]}"
    chave_b = f"beta-{uuid.uuid4().hex[:16]}"

    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO construtoras (id, nome, cnpj) "
                "VALUES (:a, 'Construtora Alfa', :ca), (:b, 'Construtora Beta', :cb)"
            ),
            {"a": ids["tenant_a"], "b": ids["tenant_b"], "ca": cnpj_a, "cb": cnpj_b},
        )
        conn.execute(
            text(
                "INSERT INTO obras (id, tenant_id, nome, cnpj_destinatario, api_key) VALUES "
                "(:oa, :ta, 'Obra Alfa 1', :ca, :ka),"
                "(:ob, :tb, 'Obra Beta 1', :cb, :kb)"
            ),
            {
                "oa": ids["obra_a"], "ta": ids["tenant_a"], "ca": cnpj_a, "ka": chave_a,
                "ob": ids["obra_b"], "tb": ids["tenant_b"], "cb": cnpj_b, "kb": chave_b,
            },
        )
        conn.execute(
            text(
                "INSERT INTO usuarios (id, tenant_id, nome, email, papel_global) VALUES "
                "(:ua, :ta, 'Ana Alfa', 'ana@alfa.test', 'admin_tenant'),"
                "(:ub, :tb, 'Bruno Beta', 'bruno@beta.test', 'admin_tenant')"
            ),
            {
                "ua": ids["usuario_a"], "ta": ids["tenant_a"],
                "ub": ids["usuario_b"], "tb": ids["tenant_b"],
            },
        )
        conn.execute(
            text(
                "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) VALUES "
                "(:ta, :oa, :ua, 'engenheiro'), (:tb, :ob, :ub, 'engenheiro')"
            ),
            {
                "ta": ids["tenant_a"], "oa": ids["obra_a"], "ua": ids["usuario_a"],
                "tb": ids["tenant_b"], "ob": ids["obra_b"], "ub": ids["usuario_b"],
            },
        )
        # Um nfe_log por obra, para exercitar o bootstrap que resolve o tenant
        # a partir de um log de conferência.
        conn.execute(
            text(
                "INSERT INTO nfe_logs (id, chave_acesso, obra_id, status_conferencia) VALUES "
                "(:la, :ka, :oa, 'VERDE'), (:lb, :kb, :ob, 'VERDE')"
            ),
            {
                "la": ids["nfe_a"], "ka": "1" * 44, "oa": ids["obra_a"],
                "lb": ids["nfe_b"], "kb": "2" * 44, "ob": ids["obra_b"],
            },
        )

    return ids
