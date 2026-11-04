"""Grava a senha administrativa no .env sem exibi-la e testa a autenticação.

Por que existe: a senha do PostgreSQL pode conter `@`, `:`, `/`, `#`, `%` etc.
Colada crua dentro da URL, ela quebra o parser do libpq (ou vira parte do host).
Aqui a senha é lida no prompt oculto, percent-encoded e só então gravada; o
resto da URL (usuário, host, porta, banco) é preservado.

Uso:

    cd backend
    python scripts/configurar_senha_admin.py

A senha nunca é aceita por argumento de linha de comando (ficaria no histórico)
e nunca é impressa. Ao final, uma conexão read-only confirma a autenticação.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg2

PADRAO = Path(__file__).resolve().parents[1] / ".env"
CHAVE = "SUPABASE_DB_ADMIN_URL"


def montar_url(url_atual: str, senha: str) -> str:
    """Substitui apenas a senha, codificando os caracteres reservados."""
    esquema, _, resto = url_atual.partition("://")
    userinfo, separador, hostport = resto.rpartition("@")
    usuario, _, _ = userinfo.partition(":")
    if not (esquema and separador and usuario and hostport):
        raise ValueError("URL administrativa incompleta: falta esquema, usuário ou host")
    return f"{esquema}://{usuario}:{quote(senha, safe='')}@{hostport}"


def normalizar(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgres+psycopg2://", "postgresql://"
    )


def testar(url: str) -> tuple[bool, str]:
    try:
        conn = psycopg2.connect(normalizar(url), connect_timeout=15)
    except psycopg2.Error as exc:
        texto = str(exc).strip().splitlines()[0]
        return False, texto
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()
    return True, "autenticação aceita"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=PADRAO)
    args = p.parse_args(argv)

    if not args.env_file.is_file():
        print(f"ERRO: {args.env_file} não existe", file=sys.stderr)
        return 2

    linhas = args.env_file.read_text(encoding="utf-8").splitlines()
    atual = next((l.split("=", 1)[1].strip() for l in linhas if l.startswith(f"{CHAVE}=")), "")
    if not atual:
        print(f"ERRO: {CHAVE} ausente em {args.env_file}", file=sys.stderr)
        return 2

    senha = getpass.getpass("Senha de postgres.<ref> (não será exibida): ")
    if not senha:
        print("ERRO: senha vazia", file=sys.stderr)
        return 2

    nova = montar_url(atual, senha)
    saida = [f"{CHAVE}={nova}" if l.startswith(f"{CHAVE}=") else l for l in linhas]
    args.env_file.write_text("\n".join(saida) + "\n", encoding="utf-8")
    print(f"senha gravada com percent-encoding ({len(senha)} caracteres)")

    ok, detalhe = testar(nova)
    if ok:
        print("conexão administrativa: OK")
        return 0
    print(f"conexão administrativa: FALHOU — {detalhe}", file=sys.stderr)
    print("A senha foi gravada, mas o servidor não a aceitou. Confira no painel.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
