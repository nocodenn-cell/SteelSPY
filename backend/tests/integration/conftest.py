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
                "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, status_conferencia) VALUES "
                "(:la, :ta, :ka, :oa, 'VERDE'), (:lb, :tb, :kb, :ob, 'VERDE')"
            ),
            {
                "la": ids["nfe_a"], "ka": "1" * 44, "oa": ids["obra_a"], "ta": ids["tenant_a"],
                "lb": ids["nfe_b"], "kb": "2" * 44, "ob": ids["obra_b"], "tb": ids["tenant_b"],
            },
        )

        # Itens das conferências: é onde o dado de negócio realmente vive.
        conn.execute(
            text(
                "INSERT INTO nfe_itens (tenant_id, nfe_log_id, item_numero, material_recebido, "
                "status_item, divergencias) VALUES "
                "(:ta, :la, 1, 'Vergalhao CA-50 10mm', 'VERDE', '[]'::jsonb), "
                "(:tb, :lb, 1, 'Vergalhao CA-50 12.5mm', 'VERMELHO', '[]'::jsonb)"
            ),
            {
                "ta": ids["tenant_a"], "la": ids["nfe_a"],
                "tb": ids["tenant_b"], "lb": ids["nfe_b"],
            },
        )

        # Especificações por obra. A quantidade do tenant A casa com a entrega
        # de 100 m usada no teste de escrita — assim o status é VERDE de forma
        # determinística (com 1000 m a divergência seria de 90%).
        conn.execute(
            text(
                "INSERT INTO especificacoes (tenant_id, obra_id, material_tipo, bitola_mm, "
                "marca_exigida, qtd_planejada_metros) VALUES "
                "(:ta, :oa, 'CA-50', 10.0, 'GERDAU', 100.0), "
                "(:tb, :ob, 'CA-50', 12.5, 'GERDAU', 2000.0)"
            ),
            {
                "ta": ids["tenant_a"], "oa": ids["obra_a"],
                "tb": ids["tenant_b"], "ob": ids["obra_b"],
            },
        )

        # Fila de retentativa: uma linha pendente por tenant.
        # A fila é global (o worker reivindica por ordem de proxima_tentativa).
        # Para o cenário ser determinístico, as linhas pendentes de execuções
        # anteriores são encerradas antes de inserir as deste teste.
        conn.execute(
            text(
                "UPDATE fila_nfe SET status = 'processado', updated_at = NOW() "
                "WHERE status IN ('pendente', 'processando')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO fila_nfe (tenant_id, obra_id, chave_acesso, proxima_tentativa, status) "
                "VALUES (:ta, :oa, :ka, NOW() - INTERVAL '1 minute', 'pendente'), "
                "(:tb, :ob, :kb, NOW() - INTERVAL '1 minute', 'pendente')"
            ),
            {
                "ta": ids["tenant_a"], "oa": ids["obra_a"], "ka": "1" * 44,
                "tb": ids["tenant_b"], "ob": ids["obra_b"], "kb": "2" * 44,
            },
        )

    return ids
