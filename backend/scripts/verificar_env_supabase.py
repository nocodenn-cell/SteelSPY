"""Verifica a configuração local do Supabase oficial sem imprimir segredos.

Responde à pergunta da Etapa 1: o `.env` existe, está fora do Git, tem as
variáveis que o código usa e nenhuma delas ainda é um placeholder? Só imprime
presença, formato e tamanho — nunca o valor.

Uso:

    cd backend
    python scripts/verificar_env_supabase.py

Sai 0 quando não há bloqueio e 2 quando alguma variável obrigatória falta ou
ainda é modelo. Avisos não impedem a execução local.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from diagnostico_supabase import (
    REF_OFICIAL,
    carregar_env,
    normalizar_url,
    problema_na_url_postgres,
)

RAIZ_REPO = Path(__file__).resolve().parents[2]
PADRAO = Path(__file__).resolve().parents[1] / ".env"
APP_ROLE = f"stellspy_app.{REF_OFICIAL}"


def ler_env(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        bruta = linha.strip()
        if not bruta or bruta.startswith("#") or "=" not in bruta:
            continue
        chave, valor = bruta.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def ignorado_pelo_git(caminho: Path) -> bool | None:
    try:
        resultado = subprocess.run(
            ["git", "check-ignore", "-q", str(caminho)],
            cwd=RAIZ_REPO,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return resultado.returncode == 0


def _host(url: str) -> str:
    return (urlparse(normalizar_url(url)).hostname or "").lower()


def _usuario(url: str) -> str:
    return urlparse(normalizar_url(url)).username or ""


def avaliar(valores: dict[str, str]) -> list[tuple[str, str, str]]:
    """Lista (variável, situação, detalhe) sem expor valores."""
    itens: list[tuple[str, str, str]] = []

    def bloqueado(nome: str, detalhe: str) -> None:
        itens.append((nome, "BLOQUEADO", detalhe))

    def aviso(nome: str, detalhe: str) -> None:
        itens.append((nome, "AVISO", detalhe))

    def ok(nome: str, detalhe: str) -> None:
        itens.append((nome, "OK", detalhe))

    url = valores.get("SUPABASE_URL", "")
    if not url:
        bloqueado("SUPABASE_URL", "ausente")
    elif url.startswith("https://") and _host(url) == f"{REF_OFICIAL}.supabase.co":
        ok("SUPABASE_URL", f"projeto {REF_OFICIAL}")
    else:
        bloqueado("SUPABASE_URL", "não aponta para o projeto oficial")

    chave = valores.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not chave:
        bloqueado("SUPABASE_SERVICE_ROLE_KEY", "ausente (só no servidor)")
    elif len(chave) >= 40:
        ok("SUPABASE_SERVICE_ROLE_KEY", "presente (valor não exibido)")
    else:
        bloqueado("SUPABASE_SERVICE_ROLE_KEY", "curta demais para ser uma chave real")

    admin = valores.get("SUPABASE_DB_ADMIN_URL", "")
    if not admin:
        bloqueado("SUPABASE_DB_ADMIN_URL", "ausente — migrations não rodam")
    else:
        defeito = problema_na_url_postgres(admin)
        if defeito:
            bloqueado("SUPABASE_DB_ADMIN_URL", defeito)
        elif _usuario(admin) != f"postgres.{REF_OFICIAL}":
            bloqueado("SUPABASE_DB_ADMIN_URL", "usuário não é postgres.<ref> oficial")
        elif "pooler.supabase.com" not in _host(admin):
            bloqueado("SUPABASE_DB_ADMIN_URL", "host não é o Session Pooler")
        else:
            ok("SUPABASE_DB_ADMIN_URL", "postgres.<ref> via pooler")

    senha_app = valores.get("STELLSPY_APP_PASSWORD", "")
    if len(senha_app) < 12:
        bloqueado("STELLSPY_APP_PASSWORD", f"{len(senha_app)} caracteres; mínimo 12")
    else:
        ok("STELLSPY_APP_PASSWORD", f"{len(senha_app)} caracteres")

    banco = valores.get("DATABASE_URL", "")
    if not banco:
        bloqueado("DATABASE_URL", "ausente — a API não conecta")
    else:
        defeito = problema_na_url_postgres(banco)
        if defeito:
            bloqueado("DATABASE_URL", defeito)
        elif _usuario(banco) != APP_ROLE:
            bloqueado("DATABASE_URL", f"usuário deveria ser {APP_ROLE}")
        elif "pooler.supabase.com" not in _host(banco):
            bloqueado("DATABASE_URL", "host não é o Session Pooler")
        elif urlparse(normalizar_url(banco)).port != 5432:
            bloqueado("DATABASE_URL", "porta deveria ser 5432 (modo sessão)")
        else:
            ok("DATABASE_URL", "role operacional via pooler, porta 5432")

    segredo = valores.get("PWA_SESSION_SECRET", "")
    if len(segredo) >= 32:
        ok("PWA_SESSION_SECRET", f"{len(segredo)} caracteres")
    else:
        bloqueado("PWA_SESSION_SECRET", "ausente ou curto (mínimo 32)")

    modo = (valores.get("EVIDENCIAS_STORAGE") or "local").strip().lower()
    if modo == "supabase":
        if valores.get("EVIDENCIAS_BUCKET"):
            ok("EVIDENCIAS_STORAGE", "supabase; bucket criado pela migração 30")
        else:
            bloqueado("EVIDENCIAS_BUCKET", "ausente com EVIDENCIAS_STORAGE=supabase")
    elif modo == "local":
        aviso("EVIDENCIAS_STORAGE", "local — não é homologação remota")
    else:
        bloqueado("EVIDENCIAS_STORAGE", f"modo inválido: {modo!r}")

    if not valores.get("SUPABASE_ANON_KEY"):
        aviso("SUPABASE_ANON_KEY", "ausente; o backend atual não a usa")
    if not valores.get("CORS_ALLOW_ORIGINS"):
        aviso("CORS_ALLOW_ORIGINS", "vazio; defina origens exatas antes do deploy")
    if not valores.get("NFE_IO_TOKEN") and valores.get("NFE_IO_MOCK") != "1":
        aviso("NFE_IO_TOKEN", "vazio com NFE_IO_MOCK != 1")

    return itens


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=PADRAO)
    args = p.parse_args(argv)

    if not args.env_file.is_file():
        print(f"BLOQUEADO: {args.env_file} não existe. Copie .env.example e preencha.")
        return 2

    ignorado = ignorado_pelo_git(args.env_file)
    if ignorado is False:
        print(f"BLOQUEADO: {args.env_file} NÃO está no .gitignore — não prossiga.")
        return 2
    estado_git = "ignorado pelo Git" if ignorado else "não foi possível confirmar via git"

    itens = avaliar(ler_env(args.env_file))
    largura = max(len(nome) for nome, _, _ in itens)
    print(f"{args.env_file} ({estado_git})")
    for nome, situacao, detalhe in itens:
        print(f"  {nome.ljust(largura)}  {situacao:<9}  {detalhe}")

    bloqueios = sum(1 for _, s, _ in itens if s == "BLOQUEADO")
    avisos = sum(1 for _, s, _ in itens if s == "AVISO")
    print(f"\n{bloqueios} bloqueio(s), {avisos} aviso(s)")
    return 2 if bloqueios else 0


if __name__ == "__main__":
    sys.exit(main())
