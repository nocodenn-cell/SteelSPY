"""Aplica as migrações SQL do projeto em um banco PostgreSQL.

Por que existe: a máquina não tem `psql` instalado, e o projeto precisa de um
caminho reproduzível para aplicar `supabase/migrations/*.sql` em banco
descartável (testes) e, futuramente, em ambiente controlado.

Garantias:
- cada arquivo roda em sua própria transação;
- o que já foi aplicado fica registrado em `schema_migrations` e não roda de novo;
- falha em um arquivo aborta aquele arquivo e não grava o registro;
- a ordem é lexicográfica pelo nome (timestamp), igual ao padrão do projeto.

Uso:
    # lê SUPABASE_DB_ADMIN_URL e STELLSPY_APP_PASSWORD do .env local
    python scripts/apply_migrations.py --env-file .env

    # ou explícito
    python scripts/apply_migrations.py --url postgresql://... --dir ../supabase/migrations

O runner prefere `SUPABASE_DB_ADMIN_URL` a `DATABASE_URL`: a segunda é da role
operacional, e usá-la para DDL seria justamente o que a RLS impede.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

RAIZ_REPO = Path(__file__).resolve().parents[2]
DIR_PADRAO = RAIZ_REPO / "supabase" / "migrations"

DDL_CONTROLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    versao      TEXT PRIMARY KEY,
    nome_arquivo TEXT NOT NULL,
    aplicado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def normalizar_url(url: str) -> str:
    """Remove o sufixo de driver do SQLAlchemy que o psycopg2 não entende."""
    return url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgres+psycopg2://", "postgresql://"
    )


def ler_env(caminho: Path | None) -> dict[str, str]:
    """Lê KEY=VALUE sem sobrescrever o que já veio do ambiente."""
    if caminho is None or not caminho.is_file():
        return {}
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        bruta = linha.strip()
        if not bruta or bruta.startswith("#") or "=" not in bruta:
            continue
        chave, valor = bruta.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def conectar(url: str, app_password: str | None = None):
    """
    Abre a conexão e, se houver senha de aplicação, publica a configuração que
    a migração M23 lê (`stellspy.app_password`). Assim a senha nunca vive no
    repositório: ela vem do ambiente do executor.
    """
    conn = psycopg2.connect(normalizar_url(url))
    if app_password:
        with conn.cursor() as cur:
            # false = escopo de sessão: vale para todas as migrações desta execução.
            cur.execute("SELECT set_config('stellspy.app_password', %s, false)", (app_password,))
    return conn


def versoes_aplicadas(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(DDL_CONTROLE)
        cur.execute("SELECT versao FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}
    # o commit é feito pelo chamador


ROLES_SEM_DDL = frozenset({"stellspy_app", "anon", "authenticated"})


def validar_role_migracao(conn) -> None:
    """Recusa rodar DDL com a role operacional — RLS e privilégios seriam contornados."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, has_schema_privilege(current_user, 'public', 'CREATE')")
        usuario, pode_criar = cur.fetchone()
    if usuario in ROLES_SEM_DDL:
        raise RuntimeError(
            f"migrações não podem rodar como {usuario!r}; use a role administrativa "
            "(--url ou SUPABASE_DB_ADMIN_URL)"
        )
    if not pode_criar:
        raise RuntimeError(f"role {usuario!r} sem CREATE no schema public")


def aplicar(conn, arquivo: Path, versao: str) -> None:
    sql = arquivo.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (versao, nome_arquivo) VALUES (%s, %s) "
            "ON CONFLICT (versao) DO NOTHING",
            (versao, arquivo.name),
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="", help="URL administrativa do PostgreSQL")
    p.add_argument("--dir", default=str(DIR_PADRAO), help="diretório das migrações")
    p.add_argument("--env-file", type=Path, default=None, help="arquivo KEY=VALUE local")
    args = p.parse_args(argv)

    valores = ler_env(args.env_file)
    url = (
        args.url
        or os.getenv("SUPABASE_DB_ADMIN_URL")
        or os.getenv("DATABASE_URL")
        or valores.get("SUPABASE_DB_ADMIN_URL")
        or valores.get("DATABASE_URL")
        or ""
    )
    if not url:
        print(
            "ERRO: defina --url, SUPABASE_DB_ADMIN_URL ou --env-file com a URL administrativa",
            file=sys.stderr,
        )
        return 2
    if "[" in url or "]" in url or "<HOST" in url.upper():
        print(
            "ERRO: a URL administrativa ainda contém placeholder. "
            "Substitua a senha em SUPABASE_DB_ADMIN_URL no arquivo local.",
            file=sys.stderr,
        )
        return 2

    diretorio = Path(args.dir)
    if not diretorio.is_dir():
        print(f"ERRO: diretório inexistente: {diretorio}", file=sys.stderr)
        return 2

    arquivos = sorted(diretorio.glob("*.sql"))
    if not arquivos:
        print(f"ERRO: nenhum .sql em {diretorio}", file=sys.stderr)
        return 2

    app_password = (
        os.getenv("STELLSPY_APP_PASSWORD")
        or valores.get("STELLSPY_APP_PASSWORD")
        or ""
    ).strip() or None

    conn = conectar(url, app_password)
    try:
        try:
            validar_role_migracao(conn)
        except RuntimeError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 2
        aplicadas = versoes_aplicadas(conn)
        conn.commit()

        pendentes = [a for a in arquivos if a.stem not in aplicadas]
        print(f"migrações: {len(arquivos)}  já aplicadas: {len(aplicadas)}  pendentes: {len(pendentes)}")

        for arquivo in pendentes:
            try:
                aplicar(conn, arquivo, arquivo.stem)
                conn.commit()
                print(f"  OK   {arquivo.name}")
            except Exception as exc:  # noqa: BLE001 - queremos reportar e parar
                conn.rollback()
                print(f"  FALHA {arquivo.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1

        print(f"concluído: {len(pendentes)} aplicada(s)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
