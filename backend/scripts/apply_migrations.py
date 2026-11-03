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
    set DATABASE_URL=postgresql://user:senha@host:porta/banco
    python scripts/apply_migrations.py

    # ou explícito
    python scripts/apply_migrations.py --url postgresql://... --dir ../supabase/migrations
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


def conectar(url: str):
    return psycopg2.connect(normalizar_url(url))


def versoes_aplicadas(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(DDL_CONTROLE)
        cur.execute("SELECT versao FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}
    # o commit é feito pelo chamador


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
    p.add_argument("--url", default=os.getenv("DATABASE_URL", ""), help="URL do PostgreSQL")
    p.add_argument("--dir", default=str(DIR_PADRAO), help="diretório das migrações")
    args = p.parse_args(argv)

    if not args.url:
        print("ERRO: defina --url ou DATABASE_URL", file=sys.stderr)
        return 2

    diretorio = Path(args.dir)
    if not diretorio.is_dir():
        print(f"ERRO: diretório inexistente: {diretorio}", file=sys.stderr)
        return 2

    arquivos = sorted(diretorio.glob("*.sql"))
    if not arquivos:
        print(f"ERRO: nenhum .sql em {diretorio}", file=sys.stderr)
        return 2

    conn = conectar(args.url)
    try:
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
