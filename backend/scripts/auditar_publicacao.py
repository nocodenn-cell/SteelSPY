"""Auditoria read-only para publicação: variáveis e segredos versionados.

Duas perguntas, sem imprimir valor nenhum:

1. o `.env` tem o contrato que o piloto exige (role operacional, segredo de
   sessão, CORS exato, dashboard de menor privilégio)?
2. algum segredo real entrou no Git — chave `service_role`, chave privada,
   senha de banco em URL, `.env` versionado?

Uso:

    cd backend
    python scripts/auditar_publicacao.py
    python scripts/auditar_publicacao.py --env-file outro.env --repo ..

Sai 2 quando há bloqueio e 0 quando só há avisos ou tudo certo. Nunca conecta
no banco e nunca altera arquivo.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.cors import origens_permitidas  # noqa: E402  (depende do sys.path acima)

RAIZ_REPO = Path(__file__).resolve().parents[2]
PADRAO_ENV = Path(__file__).resolve().parents[1] / ".env"

Item = tuple[str, str, str]

IGNORAR_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"})
SUFIXOS_BINARIOS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".whl", ".exe", ".dll"}
)

_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PEM = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")
_PG_URL = re.compile(r"postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?://([^:/@\s]+):([^@\s]+)@([^/\s'\"]+)")
_SEGREDO_ENV = re.compile(
    r"^\s*(STELLSPY_APP_PASSWORD|STELLSPY_DASHBOARD_PASSWORD|PWA_SESSION_SECRET|SMTP_PASSWORD)\s*=\s*(\S.*)$"
)
_API_BASE = re.compile(r'"apiBaseUrl"\s*:\s*"([^"]*)"')

_TEMPLATES = ("[", "<", "$", "{", "senha", "SENHA", "PASSWORD", "change-me", "troque")

# Fixtures de teste precisam de URL com cara de produção para exercitar o código.
# A marca é uma afirmação humana explícita — não é heurística, e aparece no diff.
MARCA_EXEMPLO = "credencial-de-exemplo"


def ler_env(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        bruta = linha.strip()
        if not bruta or bruta.startswith("#") or "=" not in bruta:
            continue
        chave, valor = bruta.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _usuario(url: str) -> str:
    return urlsplit(url).username or ""


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _porta(url: str) -> int | None:
    try:
        return urlsplit(url).port
    except ValueError:
        return None


def _template(valor: str) -> bool:
    return any(marca in valor for marca in _TEMPLATES)


def _uuid(valor: str | None) -> bool:
    try:
        uuid.UUID(valor or "")
    except (ValueError, AttributeError):
        return False
    return True


def avaliar_env(valores: dict[str, str]) -> list[Item]:
    """Avalia o contrato de publicação. Só presença, formato e papel — nunca o valor."""
    itens: list[Item] = []

    def bloqueado(nome: str, detalhe: str) -> None:
        itens.append((nome, "BLOQUEADO", detalhe))

    def aviso(nome: str, detalhe: str) -> None:
        itens.append((nome, "AVISO", detalhe))

    def ok(nome: str, detalhe: str) -> None:
        itens.append((nome, "OK", detalhe))

    banco = valores.get("DATABASE_URL", "")
    if not banco:
        bloqueado("DATABASE_URL", "ausente — a API não conecta")
    elif _template(banco):
        bloqueado("DATABASE_URL", "ainda é modelo; preencha a senha fora do repositório")
    else:
        usuario = _usuario(banco)
        if usuario not in ("stellspy_app",) and not usuario.startswith("stellspy_app."):
            bloqueado(
                "DATABASE_URL",
                f"usuário {usuario!r} não é a role operacional stellspy_app",
            )
        elif _host(banco) in ("localhost", "127.0.0.1"):
            aviso("DATABASE_URL", "banco local; o piloto remoto usa o pooler do projeto oficial")
        elif "pooler.supabase.com" in _host(banco) and _porta(banco) == 5432:
            ok("DATABASE_URL", "role operacional via pooler, modo sessão")
        else:
            aviso("DATABASE_URL", "host/porta fora do contrato do pooler (5432)")

    admin = valores.get("SUPABASE_DB_ADMIN_URL", "")
    if admin and admin == banco:
        bloqueado("SUPABASE_DB_ADMIN_URL", "igual à DATABASE_URL da aplicação")
    elif admin:
        aviso("SUPABASE_DB_ADMIN_URL", "presente: use só no executor de migrations, nunca no processo da API")

    segredo = valores.get("PWA_SESSION_SECRET", "")
    if len(segredo) < 32:
        bloqueado("PWA_SESSION_SECRET", f"{len(segredo)} caracteres; mínimo 32")
    else:
        ok("PWA_SESSION_SECRET", f"{len(segredo)} caracteres")

    origens_raw = valores.get("CORS_ALLOW_ORIGINS", "")
    origens: list[str] = []
    try:
        origens = origens_permitidas(origens_raw)
    except ValueError as exc:
        bloqueado("CORS_ALLOW_ORIGINS", str(exc))
    else:
        if not origens:
            aviso("CORS_ALLOW_ORIGINS", "vazio; só funciona com PWA na mesma origem da API")
        elif any(o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o for o in origens):
            aviso("CORS_ALLOW_ORIGINS", "origem http fora de localhost: câmera e service worker não funcionam")
        else:
            ok("CORS_ALLOW_ORIGINS", f"{len(origens)} origem(ns) exata(s)")

    if valores.get("SKIP_API_KEY", "0").strip() == "0":
        ok("SKIP_API_KEY", "exigindo credencial")
    else:
        bloqueado("SKIP_API_KEY", "diferente de 0 — a API aceitaria chamada sem credencial")

    secure = valores.get("PWA_COOKIE_SECURE", "").strip()
    https = any(o.startswith("https://") for o in origens)
    if https and secure != "1":
        bloqueado("PWA_COOKIE_SECURE", "origem HTTPS com cookie sem Secure")
    elif secure == "1":
        ok("PWA_COOKIE_SECURE", "cookie só em TLS")
    else:
        aviso("PWA_COOKIE_SECURE", "0/ausente; aceitável apenas em HTTP local")

    modo_evidencia = (valores.get("EVIDENCIAS_STORAGE") or "local").strip().lower()
    if modo_evidencia == "supabase":
        ok("EVIDENCIAS_STORAGE", "bucket privado do projeto oficial")
    else:
        aviso("EVIDENCIAS_STORAGE", "local; o piloto remoto deve usar Storage privado")

    if valores.get("NFE_IO_MOCK", "0").strip() == "1":
        aviso("NFE_IO_MOCK", "dados simulados; não use para validar nota real")
    if not valores.get("NFE_IO_TOKEN") and valores.get("NFE_IO_MOCK", "0").strip() != "1":
        aviso("NFE_IO_TOKEN", "ausente com NFE_IO_MOCK != 1")

    dash_url = valores.get("DASHBOARD_DATABASE_URL", "")
    if dash_url:
        if _usuario(dash_url) != "stellspy_dashboard":
            bloqueado(
                "DASHBOARD_DATABASE_URL",
                "dashboard deve usar a role stellspy_dashboard, não credencial administrativa",
            )
        elif not _uuid(valores.get("DASHBOARD_TENANT_ID")):
            bloqueado("DASHBOARD_TENANT_ID", "ausente ou não é UUID; o dashboard exige um tenant explícito")
        else:
            ok("DASHBOARD_DATABASE_URL", "role de dashboard, presa a um tenant")
    else:
        aviso("DASHBOARD_DATABASE_URL", "não configurado; dashboard não abre")

    service = valores.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if service:
        aviso("SUPABASE_SERVICE_ROLE_KEY", "presente; mantenha apenas no servidor e nunca no PWA")

    return itens


def _papel_do_jwt(token: str) -> str | None:
    try:
        parte = token.split(".")[1]
        dados = json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))
    except (ValueError, IndexError, json.JSONDecodeError):
        return None
    papel = dados.get("role") if isinstance(dados, dict) else None
    return papel if isinstance(papel, str) else None


def _url_producao_com_senha(usuario: str, senha: str, host: str) -> bool:
    if host.startswith(("localhost", "127.0.0.1", "db:")):
        return False
    if _template(senha):
        return False
    return "supabase.co" in host or "pooler.supabase.com" in host


def auditar_arquivos(raiz: Path, caminhos: list[Path]) -> list[Item]:
    """Varre arquivos versionados atrás de segredo real. Não segue binário nem symlink."""
    itens: list[Item] = []
    vistos: set[Path] = set()

    for bruto in caminhos:
        caminho = (raiz / bruto).resolve() if not bruto.is_absolute() else bruto.resolve()
        if caminho in vistos or not caminho.is_file():
            continue
        vistos.add(caminho)
        try:
            relativo = caminho.relative_to(raiz.resolve())
        except ValueError:
            continue
        if any(parte in IGNORAR_DIRS for parte in relativo.parts):
            continue
        if caminho.suffix.lower() in SUFIXOS_BINARIOS or caminho.stat().st_size > 2 * 1024 * 1024:
            continue
        dados = caminho.read_bytes()
        if b"\x00" in dados[:8192]:
            continue
        texto = dados.decode("utf-8", errors="replace")
        nome = relativo.name

        if nome == ".env" or (nome.startswith(".env.") and nome != ".env.example"):
            itens.append((str(relativo), "BLOQUEADO", "arquivo de ambiente versionado"))
            continue

        for numero, linha in enumerate(texto.splitlines(), start=1):
            local = f"{relativo}:{numero}"

            if _PEM.search(linha):
                itens.append((local, "BLOQUEADO", "chave privada no repositório"))

            for token in _JWT.findall(linha):
                papel = _papel_do_jwt(token)
                if papel == "service_role":
                    itens.append((local, "BLOQUEADO", "JWT com role service_role"))
                elif papel == "anon":
                    itens.append((local, "AVISO", "chave anon versionada (publicável, mas não é código)"))
                else:
                    itens.append((local, "AVISO", "JWT versionado; confira se é chave real"))

            if MARCA_EXEMPLO in linha:
                continue

            for usuario, senha, host in _PG_URL.findall(linha):
                if _url_producao_com_senha(usuario, senha, host):
                    itens.append((local, "BLOQUEADO", f"senha de banco em URL para host {host}"))

            achado = _SEGREDO_ENV.match(linha)
            if achado and achado.group(2).strip() and not _template(achado.group(2)):
                itens.append((local, "BLOQUEADO", f"{achado.group(1)} com valor no repositório"))

            if nome == "index.html":
                base = _API_BASE.search(linha)
                if base and base.group(1).strip():
                    itens.append(
                        (local, "AVISO", "apiBaseUrl preenchido no index.html; reverta antes do commit")
                    )

    return itens


def _arquivos_git(raiz: Path) -> list[Path]:
    try:
        resultado = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=raiz,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if resultado.returncode != 0:
        return []
    return [Path(p) for p in resultado.stdout.decode("utf-8", "replace").split("\0") if p]


def _imprimir(itens: list[Item]) -> tuple[int, int]:
    largura = max((len(nome) for nome, _, _ in itens), default=10)
    for nome, situacao, detalhe in itens:
        print(f"  {nome.ljust(largura)}  {situacao:<9}  {detalhe}")
    bloqueios = sum(1 for _, s, _ in itens if s == "BLOQUEADO")
    avisos = sum(1 for _, s, _ in itens if s == "AVISO")
    return bloqueios, avisos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=PADRAO_ENV)
    p.add_argument("--repo", type=Path, default=RAIZ_REPO)
    p.add_argument("--sem-scan", action="store_true", help="avalia só o .env, sem varrer o Git")
    args = p.parse_args(argv)

    itens: list[Item] = []
    if args.env_file.is_file():
        itens.extend(avaliar_env(ler_env(args.env_file)))
    else:
        itens.append((str(args.env_file), "BLOQUEADO", "arquivo .env não existe"))

    if not args.sem_scan:
        itens.extend(auditar_arquivos(args.repo, _arquivos_git(args.repo)))

    bloqueios, avisos = _imprimir(itens)
    print(f"\n{bloqueios} bloqueio(s), {avisos} aviso(s)")
    return 2 if bloqueios else 0


if __name__ == "__main__":
    sys.exit(main())
