"""Diagnóstico read-only do projeto Supabase oficial do SteelSPY.

Por que existe: o briefing exige confirmar projeto, região, versão, migrations,
RLS, roles, Storage e Auth **antes** de qualquer escrita. Este script só lê:
abre transação READ ONLY, não cria nada e não imprime credencial.

Uso (credenciais em `backend/.env`, arquivo ignorado pelo Git):

    python scripts/diagnostico_supabase.py --env-file .env

    # ou explícito, sem colocar segredo no histórico do shell:
    DATABASE_URL=... SUPABASE_URL=... SUPABASE_ANON_KEY=... \\
        python scripts/diagnostico_supabase.py

O relatório completo vai para `.devtmp/supabase_oficial_diag.json` (ignorado).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import psycopg2

RAIZ_REPO = Path(__file__).resolve().parents[2]
REF_OFICIAL = "akvbtceshpsvsuacueaq"
URL_OFICIAL = f"https://{REF_OFICIAL}.supabase.co"
SAIDA_PADRAO = RAIZ_REPO / ".devtmp" / "supabase_oficial_diag.json"

# Tabelas que o fluxo operacional precisa encontrar no banco.
TABELAS_ESPERADAS = (
    "construtoras",
    "obras",
    "usuarios",
    "obra_usuarios",
    "sessoes",
    "fornecedores",
    "pedidos_compra",
    "pedido_itens",
    "nfe_logs",
    "nfe_itens",
    "recebimentos",
    "evidencias",
    "evidencia_eventos",
    "conciliacoes",
    "fila_nfe",
    "especificacoes",
    "sinonimos",
    "normalizacao_materiais",
    "schema_migrations",
)

_RE_SEGREDO = re.compile(r"(postgres(?:ql)?(?:\+psycopg2)?://[^:/@\s]+:)[^@\s]+@", re.IGNORECASE)


def normalizar_url(url: str) -> str:
    """Remove o sufixo de driver do SQLAlchemy que o psycopg2 não entende."""
    return url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgres+psycopg2://", "postgresql://"
    )


def mascarar(texto: str) -> str:
    """Remove senha de qualquer URL antes de logar/gravar."""
    return _RE_SEGREDO.sub(r"\1***@", texto)


_PLACEHOLDERS = ("<host", "sua_senha", "coloque", "preencha", "changeme", "senha_aqui")


def problema_na_url_postgres(url: str) -> str | None:
    """Motivo pelo qual a URL não serve para conectar, ou None se parece válida.

    Nunca devolve o valor da senha: só descreve o defeito. Colchetes são
    rejeitados porque `urlsplit` os interpreta como host IPv6 e lança
    ValueError — um placeholder `[SENHA]` derrubava o script com traceback.
    """
    if "[" in url or "]" in url:
        return "a URL contém colchetes — placeholder não substituído ou senha sem codificação"
    if any(marca in url.lower() for marca in _PLACEHOLDERS):
        return "há texto de exemplo no lugar de host ou senha"
    try:
        partes = urlparse(normalizar_url(url))
    except ValueError as exc:
        return f"URL inválida ({type(exc).__name__})"
    if partes.scheme not in ("postgres", "postgresql"):
        return f"esquema inesperado {partes.scheme!r}; use postgresql://"
    if not partes.username:
        return "usuário ausente"
    if not partes.password:
        return "senha ausente"
    if not partes.hostname:
        return "host ausente"
    if not (partes.path or "").strip("/"):
        return "nome do banco ausente"
    return None


def ref_da_url(url: str) -> str | None:
    host = (urlparse((url or "").strip()).hostname or "").lower()
    encontrado = re.fullmatch(r"([a-z0-9]{20})\.supabase\.co", host)
    return encontrado.group(1) if encontrado else None


def regiao_do_host(host: str) -> str | None:
    """`aws-0-sa-east-1.pooler.supabase.com` → `sa-east-1`."""
    encontrado = re.match(r"aws-\d+-([a-z0-9-]+)\.pooler\.supabase\.com", (host or "").lower())
    return encontrado.group(1) if encontrado else None


def diferenca_migrations(aplicadas: list[str], locais: list[str]) -> dict[str, list[str]]:
    conjunto_aplicadas = set(aplicadas)
    conjunto_locais = set(locais)
    return {
        "pendentes_no_banco": sorted(conjunto_locais - conjunto_aplicadas),
        "no_banco_sem_arquivo": sorted(conjunto_aplicadas - conjunto_locais),
    }


def carregar_env(caminho: Path | None) -> None:
    """Carrega KEY=VALUE sem sobrescrever o que já veio do ambiente."""
    if caminho is None or not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def _primeiro(*chaves: str) -> str:
    for chave in chaves:
        valor = (os.getenv(chave) or "").strip()
        if valor:
            return valor
    return ""


def _consulta(cur, sql: str, parametros: tuple[Any, ...] | None = None) -> list[tuple]:
    cur.execute(sql, parametros)
    return cur.fetchall()


def _tabelas(cur) -> list[dict[str, Any]]:
    linhas = _consulta(
        cur,
        """
        SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity,
               (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname IN ('public', 'private')
        ORDER BY 1, 2
        """,
    )
    return [
        {
            "schema": schema,
            "tabela": tabela,
            "rls": bool(rls),
            "force_rls": bool(force),
            "policies": int(policies),
        }
        for schema, tabela, rls, force, policies in linhas
    ]


def _extensoes(cur) -> list[dict[str, str]]:
    linhas = _consulta(
        cur,
        """
        SELECT e.extname, e.extversion, n.nspname
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        ORDER BY 1
        """,
    )
    return [{"nome": nome, "versao": versao, "schema": schema} for nome, versao, schema in linhas]


def _schemas(cur) -> list[str]:
    return [linha[0] for linha in _consulta(cur, "SELECT nspname FROM pg_namespace ORDER BY 1")]


def _roles(cur) -> list[dict[str, Any]]:
    linhas = _consulta(
        cur,
        """
        SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
        FROM pg_roles
        WHERE rolname = ANY(%s)
        ORDER BY 1
        """,
        (["stellspy_app", "stellspy_owner", "postgres", "anon", "authenticated", "service_role"],),
    )
    return [
        {"nome": nome, "superuser": bool(superuser), "bypassrls": bool(bypass), "login": bool(login)}
        for nome, superuser, bypass, login in linhas
    ]


def _migrations(cur) -> dict[str, Any]:
    if not _consulta(cur, "SELECT to_regclass('public.schema_migrations') IS NOT NULL")[0][0]:
        return {"tabela_existe": False, "aplicadas": []}
    linhas = _consulta(cur, "SELECT versao, nome_arquivo, aplicado_em FROM schema_migrations ORDER BY versao")
    locais = sorted(p.stem for p in (RAIZ_REPO / "supabase" / "migrations").glob("*.sql"))
    aplicadas = [linha[0] for linha in linhas]
    return {
        "tabela_existe": True,
        "aplicadas": aplicadas,
        "ultima": linhas[-1][2].isoformat() if linhas else None,
        "locais": len(locais),
        **diferenca_migrations(aplicadas, locais),
    }


def _storage(cur) -> dict[str, Any]:
    if not _consulta(cur, "SELECT to_regclass('storage.buckets') IS NOT NULL")[0][0]:
        return {"schema_presente": False, "buckets": []}
    buckets = _consulta(
        cur,
        "SELECT id, name, public, file_size_limit FROM storage.buckets ORDER BY id",
    )
    objetos = dict(
        _consulta(cur, "SELECT bucket_id, count(*) FROM storage.objects GROUP BY bucket_id")
    )
    policies = _consulta(
        cur,
        "SELECT count(*) FROM pg_policy WHERE polrelid = 'storage.objects'::regclass",
    )[0][0]
    return {
        "schema_presente": True,
        "buckets": [
            {
                "id": bucket_id,
                "nome": nome,
                "publico": bool(publico),
                "limite_bytes": limite,
                "objetos": int(objetos.get(bucket_id, 0)),
            }
            for bucket_id, nome, publico, limite in buckets
        ],
        "policies_em_objects": int(policies),
    }


def _auth(cur) -> dict[str, Any]:
    existe = _consulta(cur, "SELECT to_regclass('auth.users') IS NOT NULL")[0][0]
    if not existe:
        return {"schema_presente": False, "usuarios": None}
    return {
        "schema_presente": True,
        "usuarios": int(_consulta(cur, "SELECT count(*) FROM auth.users")[0][0]),
    }


def _http(url: str, chave: str, caminho: str) -> dict[str, Any]:
    if not chave:
        return {"status": "nao_configurado"}
    try:
        resposta = httpx.get(
            f"{url.rstrip('/')}{caminho}",
            headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
            timeout=15.0,
        )
    except httpx.RequestError as exc:
        return {"status": "erro_rede", "erro": type(exc).__name__}
    resultado: dict[str, Any] = {"status": resposta.status_code}
    try:
        dados = resposta.json()
    except ValueError:
        return resultado
    if caminho == "/auth/v1/settings" and isinstance(dados, dict):
        resultado["email_autoconfirmar"] = dados.get("mailer_autoconfirm")
        resultado["cadastro_aberto"] = dados.get("disable_signup") is False
        resultado["provedores"] = sorted(
            nome for nome, ativo in (dados.get("external") or {}).items() if ativo
        )
    if caminho == "/storage/v1/bucket" and isinstance(dados, list):
        resultado["buckets"] = sorted(b.get("id", "?") for b in dados if isinstance(b, dict))
    return resultado


def diagnosticar(admin_url: str, supabase_url: str, anon_key: str, service_key: str) -> dict[str, Any]:
    ref = ref_da_url(supabase_url)
    host = (urlparse(admin_url).hostname or "").lower()
    relatorio: dict[str, Any] = {
        "projeto": {
            "url": supabase_url,
            "ref_declarado": ref,
            "ref_oficial": REF_OFICIAL,
            "confere": ref == REF_OFICIAL,
            "host_banco": host,
            "regiao": regiao_do_host(host),
            "pooler": "pooler.supabase.com" in host,
        },
        "http": {
            "auth_settings": _http(supabase_url, anon_key, "/auth/v1/settings") if supabase_url else {"status": "nao_configurado"},
            "storage_buckets": _http(supabase_url, service_key, "/storage/v1/bucket") if supabase_url else {"status": "nao_configurado"},
        },
    }

    conn = psycopg2.connect(normalizar_url(admin_url))
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '20s'")
            relatorio["banco"] = {
                "versao": _consulta(cur, "SELECT current_setting('server_version')")[0][0],
                "extensoes": _extensoes(cur),
                "schemas": _schemas(cur),
                "tabelas": _tabelas(cur),
                "roles": _roles(cur),
                "migrations": _migrations(cur),
                "storage": _storage(cur),
                "auth": _auth(cur),
            }
            tabelas = {t["tabela"] for t in relatorio["banco"]["tabelas"]}
            relatorio["ausentes"] = [t for t in TABELAS_ESPERADAS if t not in tabelas]
            relatorio["sem_force_rls"] = sorted(
                t["schema"] + "." + t["tabela"]
                for t in relatorio["banco"]["tabelas"]
                if t["rls"] and not t["force_rls"]
            )
            com_tenant = {
                tabela
                for schema, tabela in _consulta(
                    cur,
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.columns
                    WHERE column_name = 'tenant_id'
                    """,
                )
                if schema in ("public", "private")
            }
            sem_rls = {
                (t["schema"], t["tabela"])
                for t in relatorio["banco"]["tabelas"]
                if not t["rls"]
            }
            relatorio["tenant_sem_rls"] = sorted(
                f"{schema}.{tabela}" for schema, tabela in sem_rls if tabela in com_tenant
            )
        conn.rollback()
    finally:
        conn.close()

    postgis = next(
        (e for e in relatorio["banco"]["extensoes"] if e["nome"] == "postgis"), None
    )
    relatorio["resumo"] = {
        "projeto_confere": relatorio["projeto"]["confere"],
        "postgres": relatorio["banco"]["versao"],
        "postgis": postgis["versao"] if postgis else None,
        "migrations_aplicadas": len(relatorio["banco"]["migrations"].get("aplicadas", [])),
        "migrations_pendentes": relatorio["banco"]["migrations"].get("pendentes_no_banco", []),
        "tabelas_esperadas_ausentes": relatorio["ausentes"],
        "app_sem_bypassrls": next(
            (r["bypassrls"] is False and r["superuser"] is False
             for r in relatorio["banco"]["roles"] if r["nome"] == "stellspy_app"),
            None,
        ),
        "bucket_evidencias_privado": next(
            (not b["publico"] for b in relatorio["banco"]["storage"]["buckets"] if b["id"] == "evidencias"),
            None,
        ),
    }
    return relatorio


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    p.add_argument("--admin-url", default="")
    p.add_argument("--supabase-url", default="")
    p.add_argument("--anon-key", default="")
    p.add_argument("--service-key", default="")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = p.parse_args(argv)

    carregar_env(args.env_file)

    admin_url = args.admin_url or _primeiro(
        "SUPABASE_DB_ADMIN_URL", "MIGRATION_DATABASE_URL", "DATABASE_URL"
    )
    supabase_url = args.supabase_url or _primeiro("SUPABASE_URL") or URL_OFICIAL
    anon_key = args.anon_key or _primeiro("SUPABASE_ANON_KEY")
    service_key = args.service_key or _primeiro("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")

    ref = ref_da_url(supabase_url)
    print(f"projeto: {supabase_url}  ref={ref or '?'}  oficial={REF_OFICIAL}")
    if ref and ref != REF_OFICIAL:
        print("ATENÇÃO: a URL não corresponde ao projeto oficial do SteelSPY.", file=sys.stderr)
    if not admin_url:
        print(
            "BLOQUEADO: SUPABASE_DB_ADMIN_URL ausente. Copie a URI do pooler "
            "(Project Settings → Database → Connection string → Session pooler) "
            "para backend/.env.",
            file=sys.stderr,
        )
        return 2
    defeito = problema_na_url_postgres(admin_url)
    if defeito:
        print(
            f"BLOQUEADO: SUPABASE_DB_ADMIN_URL não conecta — {defeito}. "
            "Substitua na cópia local (backend/.env) pela URI real do "
            "Project Settings > Database > Connection string > Session pooler; "
            "nada foi conectado ou alterado.",
            file=sys.stderr,
        )
        return 2
    if "stellspy_app" in admin_url:
        print(
            "AVISO: a URL informada usa stellspy_app. O diagnóstico precisa da role "
            "administrativa para ler auth/storage; como operacional, partes do "
            "relatório virão vazias.",
            file=sys.stderr,
        )

    try:
        relatorio = diagnosticar(admin_url, supabase_url, anon_key, service_key)
    except psycopg2.Error as exc:
        print(f"ERRO de conexão: {type(exc).__name__}: {mascarar(str(exc).strip())}", file=sys.stderr)
        return 3

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(relatorio["resumo"], ensure_ascii=False, indent=2))
    print(f"relatório completo: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
