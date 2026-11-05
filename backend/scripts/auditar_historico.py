"""Auditoria read-only do histórico Git atrás de segredos.

A árvore atual pode estar limpa e o histórico não: um `.env` apagado, uma chave
trocada ou um token removido continuam no commit antigo e no clone de qualquer
pessoa. Este script percorre as linhas *adicionadas* por cada commit e as
mensagens, sem imprimir o valor encontrado.

Uso:

    cd backend
    python scripts/auditar_historico.py
    python scripts/auditar_historico.py --range bce0155..c2cdfd2 --verboso

Sai 2 quando há bloqueio real; 0 quando só há fixtures sintéticas ou nada.
Nunca altera o repositório e nunca conecta em serviço nenhum.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

RAIZ_REPO = Path(__file__).resolve().parents[2]

_PEM = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_PG_URL = re.compile(r"postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?://([^:/@\s]+):([^@\s]+)@([^/\s'\"]+)")
_SEGREDO_ENV = re.compile(
    r"^\s*(STELLSPY_APP_PASSWORD|STELLSPY_DASHBOARD_PASSWORD|DASHBOARD_PASSWORD|"
    r"PWA_SESSION_SECRET|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_ANON_KEY|NFE_IO_TOKEN|"
    r"SMTP_PASSWORD|DATABASE_URL|DASHBOARD_DATABASE_URL|SUPABASE_DB_ADMIN_URL)"
    r"=(\S.*)$"
)
_TOKEN_PREFIX = re.compile(
    r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
    r"sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,})\b"
)
_TEMPLATES = ("[", "<", "$", "{", "senha", "SENHA", "PASSWORD", "change-me", "troque")

MARCA_EXEMPLO = "credencial-de-exemplo"


def _placeholder(valor: str) -> bool:
    """Modelo de configuração, não segredo: `[SENHA]`, `<host>`, `${VAR}`, `***`."""
    return any(marca in valor for marca in ("[", "<", "$", "{", "***", "..."))


@dataclass(frozen=True)
class Achado:
    commit: str
    data: str
    caminho: str
    linha: int | None
    tipo: str
    situacao: str
    evidencia: str
    valor: str = ""


def _git(raiz: Path, *args: str) -> str:
    resultado = subprocess.run(
        ["git", *args],
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return resultado.stdout


def _papel_do_jwt(token: str) -> str | None:
    try:
        parte = token.split(".")[1]
        dados = json.loads(base64.urlsafe_b64decode(parte + "=" * (-len(parte) % 4)))
    except (ValueError, IndexError, json.JSONDecodeError):
        return None
    papel = dados.get("role") if isinstance(dados, dict) else None
    return papel if isinstance(papel, str) else None


def _mascarar_url(linha: str) -> str:
    return _PG_URL.sub(lambda m: f"{m.group(1)}:***@{m.group(3)}", linha)


def _host(host: str) -> str:
    return host.split(":", 1)[0].lower()


def _valor_fake(valor: str) -> bool:
    baixo = valor.lower()
    if len(baixo.strip()) <= 3:
        return True
    if baixo.strip() in {"test", "teste", "senha", "segredo", "antiga", "changeme"}:
        return True
    if any(t in baixo for t in _TEMPLATES):
        return True
    if "..." in baixo or "***" in baixo or "%40" in baixo or "%3a" in baixo:
        return True
    return any(
        marca in baixo
        for marca in (
            "s3cr3t",
            "dev-local",
            "test-only",
            "senhaforte#123",
            "segredo",
            "antiga",
            "s3nh",
            "exemplo",
            "example",
            "placeholder",
            "dummy",
            "fake",
        )
    )


def _sintetico(caminho: str, valor: str) -> bool:
    partes = Path(caminho).parts
    em_teste = "tests" in partes or "test" in partes
    em_doc = "docs" in partes
    return (em_teste or em_doc) and _valor_fake(valor)


def _documentado(linha: str) -> bool:
    return linha.lstrip().startswith(("#", "set ", "export "))


def _situacao(tipo: str, caminho: str, linha: str, valor: str = "") -> str:
    if tipo == "arquivo .env versionado":
        return "BLOQUEADO"
    if MARCA_EXEMPLO in linha or _placeholder(valor):
        return "SINTÉTICO"
    if tipo == "chave privada":
        return "SINTÉTICO" if _sintetico(caminho, linha) else "BLOQUEADO"
    if _sintetico(caminho, valor):
        return "SINTÉTICO"
    if _documentado(linha) and _valor_fake(valor):
        return "SINTÉTICO"
    return "BLOQUEADO"


def _evidencia(tipo: str, linha: str) -> str:
    if tipo == "URL de banco com senha":
        return _mascarar_url(linha).strip()[:160]
    if tipo == "JWT":
        for token in _JWT.findall(linha):
            return f"JWT role={_papel_do_jwt(token) or '?'} (token omitido)"
        return "JWT (token omitido)"
    if tipo == "chave privada":
        return "bloco PEM (conteúdo omitido)"
    if tipo == "atribuição de segredo":
        nome = linha.split("=", 1)[0].strip()
        return f"{nome}=***"
    if tipo == "token com prefixo conhecido":
        for token in _TOKEN_PREFIX.findall(linha):
            return f"{token[:4]}… (valor omitido)"
    return "(conteúdo omitido)"


def _analisar_linha(caminho: str, linha: str) -> list[Achado]:
    achados: list[Achado] = []
    if _PEM.search(linha):
        achados.append(Achado("", "", caminho, None, "chave privada", "", "", linha))
        return achados

    for token in _JWT.findall(linha):
        papel = _papel_do_jwt(token)
        if papel in {"service_role", "anon"}:
            achados.append(Achado("", "", caminho, None, "JWT", "", f"role={papel}", token))

    for prefixo in _TOKEN_PREFIX.findall(linha):
        achados.append(
            Achado("", "", caminho, None, "token com prefixo conhecido", "", "", prefixo)
        )

    url_encontrada = False
    for _usuario, senha, host in _PG_URL.findall(linha):
        url_encontrada = True
        if _host(host) in {"localhost", "127.0.0.1", "db"}:
            continue
        # Fixtures de teste também aparecem aqui e são classificadas depois;
        # filtrar pela senha esconderia um segredo real em código de produção.
        achados.append(Achado("", "", caminho, None, "URL de banco com senha", "", "", senha))

    if not url_encontrada:
        achado = _SEGREDO_ENV.match(linha)
        if achado:
            _nome, valor = achado.group(1), achado.group(2).strip().strip('"').strip("'")
            if valor and not _placeholder(valor):
                achados.append(
                    Achado("", "", caminho, None, "atribuição de segredo", "", "", valor)
                )

    return achados


def _varrer_diffs(raiz: Path, revisao: str) -> tuple[list[Achado], int, int]:
    log = _git(
        raiz,
        "log",
        "--no-merges",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--date=short",
        "--format=commit %H%x09%ad%x09%s",
        "-p",
        revisao,
    )
    achados: list[Achado] = []
    commits = 0
    linhas = 0
    commit = data = ""
    caminho = ""
    numero = 0
    env_visto: set[tuple[str, str]] = set()

    for bruta in log.splitlines():
        if bruta.startswith("commit "):
            partes = bruta.split("\t", 2)
            commit = partes[0][7:]
            data = partes[1] if len(partes) > 1 else ""
            commits += 1
            caminho = ""
            continue
        if bruta.startswith("diff --git "):
            resto = bruta[len("diff --git ") :]
            if " b/" in resto:
                caminho = resto.rsplit(" b/", 1)[1]
            numero = 0
            nome = Path(caminho).name
            if (nome == ".env" or (nome.startswith(".env.") and nome != ".env.example")) and (
                commit,
                caminho,
            ) not in env_visto:
                env_visto.add((commit, caminho))
                achados.append(
                    Achado(commit, data, caminho, None, "arquivo .env versionado", "BLOQUEADO", "")
                )
            continue
        if bruta.startswith("+++ "):
            alvo = bruta[4:]
            if alvo != "/dev/null":
                caminho = alvo[2:] if alvo.startswith("b/") else alvo
            continue
        if bruta.startswith("@@"):
            achado_hunk = re.search(r"\+(\d+)", bruta)
            numero = int(achado_hunk.group(1)) if achado_hunk else 0
            continue
        if bruta.startswith("+") and not bruta.startswith("+++"):
            linhas += 1
            linha = bruta[1:]
            for achado in _analisar_linha(caminho, linha):
                situacao = _situacao(achado.tipo, caminho, linha, achado.valor or linha)
                achados.append(
                    Achado(
                        commit,
                        data,
                        caminho,
                        numero,
                        achado.tipo,
                        situacao,
                        _evidencia(achado.tipo, linha),
                    )
                )
            numero += 1
        elif bruta.startswith(" "):
            numero += 1

    return achados, commits, linhas


def _varrer_mensagens(raiz: Path, revisao: str) -> list[Achado]:
    bruto = _git(raiz, "log", revisao, "--format=%H%x00%ad%x00%B%x00", "--date=short")
    pedacos = bruto.split("\x00")
    achados: list[Achado] = []
    for indice in range(0, len(pedacos) - 2, 3):
        commit, data, mensagem = pedacos[indice], pedacos[indice + 1], pedacos[indice + 2]
        for numero, linha in enumerate(mensagem.splitlines(), start=1):
            for achado in _analisar_linha("(mensagem do commit)", linha):
                achados.append(
                    Achado(
                        commit[:7],
                        data,
                        "(mensagem do commit)",
                        numero,
                        achado.tipo,
                        _situacao(
                            achado.tipo, "(mensagem do commit)", linha, achado.valor or linha
                        ),
                        _evidencia(achado.tipo, linha),
                    )
                )
    return achados


def analisar(raiz: Path, revisao: str) -> tuple[list[Achado], int, int]:
    achados, commits, linhas = _varrer_diffs(raiz, revisao)
    achados.extend(_varrer_mensagens(raiz, revisao))
    return achados, commits, linhas


def _imprimir(achados: list[Achado], commits: int, linhas: int, verboso: bool) -> int:
    reais = [a for a in achados if a.situacao == "BLOQUEADO"]
    sinteticos = [a for a in achados if a.situacao == "SINTÉTICO"]
    print(f"Commits analisados: {commits}; linhas adicionadas: {linhas}")
    print(f"Achados: {len(reais)} bloqueio(s), {len(sinteticos)} sintético(s)")
    for achado in reais:
        local = f"{achado.caminho}:{achado.linha}" if achado.linha else achado.caminho
        print(
            f"  BLOQUEADO  {achado.commit}  {achado.data}  {local}  "
            f"{achado.tipo}  {achado.evidencia}"
        )
    if verboso:
        for achado in sinteticos:
            local = f"{achado.caminho}:{achado.linha}" if achado.linha else achado.caminho
            print(
                f"  SINTÉTICO  {achado.commit}  {achado.data}  {local}  "
                f"{achado.tipo}  {achado.evidencia}"
            )
    return 2 if reais else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=RAIZ_REPO)
    p.add_argument("--range", dest="revisao", default="--all")
    p.add_argument("--verboso", action="store_true", help="mostra também as fixtures sintéticas")
    args = p.parse_args(argv)
    achados, commits, linhas = analisar(args.repo, args.revisao)
    return _imprimir(achados, commits, linhas, args.verboso)


if __name__ == "__main__":
    sys.exit(main())
