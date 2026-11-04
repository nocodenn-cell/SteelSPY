"""Homologação controlada do staging — dados sintéticos, isolados e idempotentes.

O script nunca roda a suíte destrutiva: ele faz diagnóstico somente-leitura e,
quando pedido, cria DUAS construtoras de homologação próprias (prefixo
`hml-...`), prova o isolamento entre elas conectando com a role real da
aplicação e só apaga o que ele mesmo criou — e apenas com `--confirmar-limpeza`.

    python scripts/hml_staging.py --acao diagnostico
    python scripts/hml_staging.py --acao semear
    python scripts/hml_staging.py --acao provar
    python scripts/hml_staging.py --acao limpar --confirmar-limpeza

Credenciais vêm de `--admin-url` / `--app-url`, ou das variáveis
HML_ADMIN_URL / HML_APP_URL, ou de `.devtmp/staging.env` (DATABASE_URL e
APP_DATABASE_URL). Nenhuma URL é impressa.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psycopg2

RAIZ_REPO = Path(__file__).resolve().parents[2]
DIR_MIGRACOES = RAIZ_REPO / "supabase" / "migrations"
ENV_STAGING = RAIZ_REPO / ".devtmp" / "staging.env"
sys.path.insert(0, str(RAIZ_REPO / "backend"))

PREFIXO_PADRAO = "hml-vc-2026-11-03"

TABELAS_ESPERADAS = (
    "construtoras", "obras", "usuarios", "obra_usuarios", "sessoes",
    "fornecedores", "pedidos_compra", "pedido_itens", "pedido_eventos",
    "nfe_logs", "nfe_itens", "fila_nfe", "conciliacoes", "especificacoes",
    "sinonimos", "normalizacao_materiais", "correlacoes_humanas",
    "evidencias", "evidencia_eventos", "recebimentos", "recebimento_itens",
    "recebimento_eventos", "schema_migrations",
)


def _do_env(chave: str) -> str | None:
    if ENV_STAGING.is_file():
        for linha in ENV_STAGING.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha.startswith(f"{chave}="):
                return linha.split("=", 1)[1].strip().strip('"')
    return None


def _url(explicita: str | None, envs: tuple[str, ...], chaves_env_file: tuple[str, ...]) -> str:
    if explicita:
        return explicita
    for nome in envs:
        if os.getenv(nome):
            return os.environ[nome]
    for chave in chaves_env_file:
        valor = _do_env(chave)
        if valor:
            return valor
    raise SystemExit(f"credencial ausente: informe --{'/--'.join(envs)} ou defina {envs[0]} / .devtmp/staging.env")


def _identidade(url: str) -> dict:
    p = urlsplit(url)
    return {"host": p.hostname, "porta": p.port or 5432, "banco": (p.path or "/").lstrip("/"), "usuario": p.username}


def _q(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    colunas = [d[0] for d in cur.description]
    return [dict(zip(colunas, linha, strict=True)) for linha in cur.fetchall()]


def _mascarar(email: str | None) -> str:
    if not email or "@" not in email:
        return "***"
    local, dominio = email.split("@", 1)
    return f"{local[:1]}***@{dominio}"


def _diferenca_migrations(locais: list[str], versoes: set[str]) -> dict[str, list[str]]:
    """Compara nome completo do arquivo com `schema_migrations.versao`."""
    return {
        "faltando_no_servidor": sorted(set(locais) - versoes),
        "no_servidor_sem_arquivo_local": sorted(versoes - set(locais)),
    }


# ---------------------------------------------------------------------------
# Diagnóstico (somente leitura)
# ---------------------------------------------------------------------------
def diagnostico(con) -> dict:
    cur = con.cursor()
    cur.execute("SET TRANSACTION READ ONLY")
    cur.execute("SELECT version(), current_user, current_database()")
    versao, usuario, banco = cur.fetchone()

    locais = sorted(p.stem for p in DIR_MIGRACOES.glob("*.sql"))
    aplicadas = _q(cur, "SELECT versao::text AS versao, nome_arquivo FROM schema_migrations ORDER BY versao")
    versoes = {a["versao"] for a in aplicadas}
    diferenca = _diferenca_migrations(locais, versoes)

    existentes = {r["table_name"] for r in _q(
        cur, "SELECT table_name FROM information_schema.tables WHERE table_schema='public'")}
    contagens = {}
    for tabela in TABELAS_ESPERADAS:
        if tabela in existentes:
            cur.execute(f'SELECT count(*) FROM public."{tabela}"')
            contagens[tabela] = cur.fetchone()[0]

    rls = _q(
        cur,
        "SELECT c.relname AS tabela, c.relrowsecurity AS habilitado, c.relforcerowsecurity AS forcado, "
        "(SELECT count(*) FROM pg_policies p WHERE p.schemaname='public' AND p.tablename=c.relname) AS policies "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r' ORDER BY 1",
    )
    roles = _q(
        cur,
        "SELECT rolname, rolsuper, rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname NOT LIKE 'pg\\\\_%%' ORDER BY 1",
    )
    try:
        cur.execute("SAVEPOINT storage_ok")
        storage = {
            "buckets": _q(cur, "SELECT id, name, public, file_size_limit FROM storage.buckets ORDER BY id"),
            "objetos": _q(cur, "SELECT bucket_id, count(*) AS objetos FROM storage.objects GROUP BY 1 ORDER BY 1"),
        }
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT storage_ok")
        storage = {"erro": type(exc).__name__}

    integridade = {
        "obras_sem_tenant": _q(cur, "SELECT count(*) AS n FROM obras WHERE tenant_id IS NULL")[0]["n"] if "obras" in existentes else None,
        "usuarios_sem_tenant": _q(cur, "SELECT count(*) AS n FROM usuarios WHERE tenant_id IS NULL")[0]["n"] if "usuarios" in existentes else None,
        "construtoras": _q(cur, "SELECT nome, plano, ativo FROM construtoras ORDER BY nome") if "construtoras" in existentes else [],
        "usuarios_mascarados": [
            {**linha, "email": _mascarar(linha["email"])}
            for linha in _q(
                cur,
                "SELECT u.email, u.papel_global, c.nome AS construtora, u.ativo FROM usuarios u "
                "LEFT JOIN construtoras c ON c.id=u.tenant_id ORDER BY c.nome, u.email",
            )
        ] if "usuarios" in existentes else [],
    }
    tabelas_com_tenant = {
        r["table_name"]
        for r in _q(
            cur,
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='tenant_id'",
        )
    }
    con.rollback()
    return {
        "servidor": {"versao": versao.split(",")[0], "usuario_efetivo": usuario, "banco": banco},
        "migrations": {
            "locais": len(locais),
            "aplicadas": len(aplicadas),
            "ultima_aplicada": aplicadas[-1] if aplicadas else None,
            **diferenca,
        },
        "tabelas": {
            "ausentes": [t for t in TABELAS_ESPERADAS if t not in existentes],
            "contagens": contagens,
        },
        "rls": rls,
        "tabelas_tenant_sem_rls_ou_sem_policy": [
            r["tabela"]
            for r in rls
            if r["tabela"] in tabelas_com_tenant
            and (not r["habilitado"] or not r["forcado"] or not r["policies"])
        ],
        "roles": roles,
        "storage": storage,
        "integridade": integridade,
    }


# ---------------------------------------------------------------------------
# Semeadura HML (idempotente)
# ---------------------------------------------------------------------------
def semear(con, prefixo: str) -> dict:
    from app.seguranca import hash_senha

    senha = os.getenv("HML_SENHA", "").strip()
    if len(senha) < 12:
        raise SystemExit("defina HML_SENHA (mínimo 12 caracteres) para semear as contas de homologação")
    cur = con.cursor()
    ids: dict = {}

    def _cnpj(serie: int) -> str:
        return f"{serie:012d}{uuid.uuid4().int % 100:02d}"[:14]

    def _tenant(sufixo: str, nome: str) -> str:
        slug = f"{prefixo}-{sufixo}"
        cur.execute("SELECT id FROM construtoras WHERE slug = %s", (slug,))
        linha = cur.fetchone()
        if linha:
            return str(linha[0])
        novo = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO construtoras (id, nome, cnpj, slug, plano) VALUES (%s, %s, %s, %s, 'piloto')",
            (novo, nome, _cnpj(97 + len(sufixo)), slug),
        )
        return novo

    def _usuario(tenant: str, email: str, nome: str, papel_global: str, obra: str, papel_obra: str) -> str:
        cur.execute("SELECT id FROM usuarios WHERE tenant_id = %s AND lower(email) = lower(%s)", (tenant, email))
        linha = cur.fetchone()
        uid = str(linha[0]) if linha else str(uuid.uuid4())
        if not linha:
            cur.execute(
                "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (uid, tenant, nome, email, hash_senha(senha), papel_global),
            )
        cur.execute(
            "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (obra_id, usuario_id) DO NOTHING",
            (tenant, obra, uid, papel_obra),
        )
        return uid

    def _obra(tenant: str, nome: str) -> str:
        cur.execute("SELECT id FROM obras WHERE tenant_id = %s AND nome = %s", (tenant, nome))
        linha = cur.fetchone()
        if linha:
            return str(linha[0])
        novo = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO obras (id, tenant_id, nome, cnpj_destinatario, api_key, modo_aprendizado) "
            "VALUES (%s, %s, %s, %s, %s, false)",
            (novo, tenant, nome, _cnpj(55), f"{prefixo}-{uuid.uuid4().hex[:10]}"),
        )
        return novo

    tenant_a = _tenant("a", "HML Construtora Alfa (homologação)")
    tenant_b = _tenant("b", "HML Construtora Beta (homologação)")
    obra_a = _obra(tenant_a, "HML Obra Alfa — Torre H1")
    obra_b = _obra(tenant_b, "HML Obra Beta — Bloco H2")

    _usuario(tenant_a, "hml-alfa-admin@staging.invalid", "HML Admin Alfa", "admin_tenant", obra_a, "engenheiro")
    _usuario(tenant_a, "hml-alfa-fiscal@staging.invalid", "HML Fiscal Alfa", "fiscal", obra_a, "fiscal")
    _usuario(tenant_b, "hml-beta-admin@staging.invalid", "HML Admin Beta", "admin_tenant", obra_b, "engenheiro")

    cur.execute("SELECT id FROM fornecedores WHERE tenant_id = %s ORDER BY criado_em LIMIT 1", (tenant_a,))
    linha = cur.fetchone()
    if linha:
        fornecedor = str(linha[0])
    else:
        fornecedor = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO fornecedores (id, tenant_id, cnpj, razao_social, nome_fantasia) "
            "VALUES (%s, %s, %s, 'HML Aço Brasil S/A', 'HML AcoBrasil')",
            (fornecedor, tenant_a, _cnpj(66)),
        )

    cur.execute("SELECT id FROM pedidos_compra WHERE tenant_id = %s AND numero = 'HML-PC-0001'", (tenant_a,))
    linha = cur.fetchone()
    if linha:
        pedido = str(linha[0])
    else:
        pedido = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO pedidos_compra (id, tenant_id, obra_id, fornecedor_id, numero, status, "
            "valor_total, emitido_em, previsao_entrega) VALUES "
            "(%s, %s, %s, %s, 'HML-PC-0001', 'aberto', 1000.00, CURRENT_DATE - 2, CURRENT_DATE + 2)",
            (pedido, tenant_a, obra_a, fornecedor),
        )
        for numero, bitola in ((1, 10.0), (2, 12.5)):
            cur.execute(
                "INSERT INTO pedido_itens (id, tenant_id, pedido_id, linha, material_tipo, "
                "categoria_material, bitola_mm, marca_exigida, quantidade, unidade) "
                "VALUES (%s, %s, %s, %s, 'CA-50', 'aco', %s, 'HML', %s, 'M')",
                (str(uuid.uuid4()), tenant_a, pedido, numero, bitola, 100.0 * numero),
            )

    cur.execute("SELECT id FROM nfe_logs WHERE tenant_id = %s AND pedido_id = %s LIMIT 1", (tenant_a, pedido))
    linha = cur.fetchone()
    if linha:
        nota = str(linha[0])
    else:
        nota = str(uuid.uuid4())
        chave = f"{uuid.uuid4().int % 10**44:044d}"
        cur.execute(
            "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, pedido_id, status_conferencia, "
            "resumo_global, xml_data, tipo) VALUES (%s, %s, %s, %s, %s, 'AMARELO', "
            "'HML: 1 item sintético', %s::jsonb, 'entrada')",
            (
                nota, tenant_a, chave, obra_a, pedido,
                json.dumps({"emitente_cnpj": "00000000000000", "chave": chave,
                            "itens": [{"n_item": 1, "descricao": "VERGALHAO HML CA-50 10MM", "bitola_mm": 10.0,
                                       "marca": "HML", "quantidade": 100.0, "unidade": "M"}]}),
            ),
        )

    con.commit()
    ids.update({
        "prefixo": prefixo,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "obra_a": obra_a,
        "obra_b": obra_b,
        "fornecedor_a": fornecedor,
        "pedido_a": pedido,
        "nota_a": nota,
        "usuarios": {
            "alfa_admin": "hml-alfa-admin@staging.invalid",
            "alfa_fiscal": "hml-alfa-fiscal@staging.invalid",
            "beta_admin": "hml-beta-admin@staging.invalid",
        },
        "senha_definida_por_env": "HML_SENHA" if os.getenv("HML_SENHA") else "padrao",
    })
    return ids


# ---------------------------------------------------------------------------
# Prova de isolamento com a role real da aplicação
# ---------------------------------------------------------------------------
def provar(con_app, ids: dict) -> list[dict]:
    tenant_a, tenant_b = ids["tenant_a"], ids["tenant_b"]
    checks: list[dict] = []

    def _registrar(nome: str, esperado, obtido) -> None:
        checks.append({"check": nome, "esperado": esperado, "obtido": obtido, "resultado": "PASS" if esperado == obtido else "FAIL"})

    def _com_tenant(tenant: str | None):
        con_app.rollback()
        cur = con_app.cursor()
        if tenant:
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        return cur

    # 1. Sem contexto, RLS fecha tudo.
    cur = _com_tenant(None)
    cur.execute("SELECT count(*) FROM usuarios")
    _registrar("sem_contexto_usuarios_invisiveis", 0, cur.fetchone()[0])
    con_app.rollback()

    # 2. Cada tenant enxerga só os próprios usuários.
    cur = _com_tenant(tenant_a)
    cur.execute("SELECT count(*) FROM usuarios")
    _registrar("tenant_a_ve_apenas_proprios", 2, cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM usuarios WHERE tenant_id = %s", (tenant_b,))
    _registrar("tenant_a_nao_ve_b", 0, cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM construtoras")
    _registrar("tenant_a_ve_uma_construtora", 1, cur.fetchone()[0])
    con_app.rollback()

    cur = _com_tenant(tenant_b)
    cur.execute("SELECT count(*) FROM usuarios")
    _registrar("tenant_b_ve_apenas_proprios", 1, cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM usuarios WHERE tenant_id = %s", (tenant_a,))
    _registrar("tenant_b_nao_ve_a", 0, cur.fetchone()[0])
    con_app.rollback()

    # 3. Escrita cruzada é bloqueada; escrita no próprio tenant passa.
    cur = _com_tenant(tenant_a)
    cur.execute("UPDATE usuarios SET nome = nome WHERE tenant_id = %s", (tenant_b,))
    _registrar("update_cruzado_afeta_zero_linhas", 0, cur.rowcount)
    con_app.rollback()

    cur = _com_tenant(tenant_a)
    cur.execute("UPDATE usuarios SET nome = nome WHERE tenant_id = %s", (tenant_a,))
    _registrar("update_proprio_afeta_duas_linhas", 2, cur.rowcount)
    con_app.rollback()

    cur = _com_tenant(tenant_a)
    cur.execute("SAVEPOINT insercao_cruzada")
    try:
        cur.execute(
            "INSERT INTO usuarios (tenant_id, nome, email) VALUES (%s, 'intruso', 'intruso@staging.invalid')",
            (tenant_b,),
        )
        _registrar("insert_cruzado_bloqueado", "erro", "inseriu")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT insercao_cruzada")
        _registrar("insert_cruzado_bloqueado", "erro", "erro")
    con_app.rollback()

    # 4. Pedido/NF-e do tenant A invisíveis para B (operações, não só cadastro).
    cur = _com_tenant(tenant_b)
    cur.execute("SELECT count(*) FROM pedidos_compra WHERE id = %s", (ids["pedido_a"],))
    _registrar("pedido_a_invisivel_para_b", 0, cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM nfe_logs WHERE id = %s", (ids["nota_a"],))
    _registrar("nota_a_invisivel_para_b", 0, cur.fetchone()[0])
    con_app.rollback()

    cur = _com_tenant(tenant_a)
    cur.execute("SELECT count(*) FROM pedidos_compra WHERE id = %s", (ids["pedido_a"],))
    _registrar("pedido_a_visivel_para_a", 1, cur.fetchone()[0])
    con_app.rollback()
    return checks


# ---------------------------------------------------------------------------
# Limpeza controlada (só o que o prefixo criou)
# ---------------------------------------------------------------------------
def limpar(con, prefixo: str, confirmar: bool) -> dict:
    if not confirmar:
        return {"executado": False, "motivo": "use --confirmar-limpeza"}
    if not prefixo.startswith(("hml-", "HML-")):
        return {"executado": False, "motivo": "prefixo fora do padrão hml-*"}
    cur = con.cursor()
    cur.execute("SELECT id, nome, slug FROM construtoras WHERE slug LIKE %s AND nome LIKE 'HML %%'", (f"{prefixo}-%",))
    alvos = cur.fetchall()
    if not alvos:
        return {"executado": False, "motivo": "nenhuma construtora de homologação encontrada"}
    try:
        cur.execute(
            "DELETE FROM construtoras WHERE id = ANY(%s) AND slug LIKE %s AND nome LIKE 'HML %%'",
            ([a[0] for a in alvos], f"{prefixo}-%"),
        )
        con.commit()
    except Exception as exc:
        con.rollback()
        return {"executado": False, "motivo": f"bloqueado: {type(exc).__name__}: {exc}"}
    return {"executado": True, "removidas": [{"nome": a[1], "slug": a[2]} for a in alvos]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hml_staging", description="Homologação controlada em staging")
    p.add_argument("--acao", choices=["diagnostico", "semear", "provar", "tudo", "limpar"], required=True)
    p.add_argument("--admin-url")
    p.add_argument("--app-url")
    p.add_argument("--prefixo", default=PREFIXO_PADRAO)
    p.add_argument("--saida", default=str(RAIZ_REPO / ".devtmp" / "hml"))
    p.add_argument("--confirmar-limpeza", action="store_true")
    args = p.parse_args(argv)

    admin_url = _url(args.admin_url, ("HML_ADMIN_URL", "DATABASE_URL"), ("DATABASE_URL",))
    app_url = _url(args.app_url, ("HML_APP_URL", "APP_DATABASE_URL"), ("APP_DATABASE_URL",))
    if app_url == admin_url:
        raise SystemExit("a URL da aplicação não pode ser igual à administrativa: RLS seria ignorado")

    resultado: dict = {"gerado_em": datetime.now(timezone.utc).isoformat(), "admin": _identidade(admin_url),
                       "app": _identidade(app_url), "prefixo": args.prefixo}

    con_admin = psycopg2.connect(admin_url, connect_timeout=15)
    con_app = psycopg2.connect(app_url, connect_timeout=15)
    try:
        if args.acao in ("diagnostico", "tudo"):
            resultado["diagnostico"] = diagnostico(con_admin)
        if args.acao in ("semear", "tudo"):
            resultado["semeadura"] = semear(con_admin, args.prefixo)
        if args.acao in ("provar", "tudo"):
            if "semeadura" not in resultado:
                raise SystemExit("--acao provar exige ids da semeadura: use --acao tudo ou rode semear e prove na sequência")
            resultado["isolamento"] = provar(con_app, resultado["semeadura"])
        if args.acao == "limpar":
            resultado["limpeza"] = limpar(con_admin, args.prefixo, args.confirmar_limpeza)
    finally:
        con_app.close()
        con_admin.close()

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{args.acao}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    arquivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    resumo = {
        "administrativo": resultado["admin"],
        "aplicacao": resultado["app"],
        "arquivo": str(arquivo),
    }
    if "diagnostico" in resultado:
        d = resultado["diagnostico"]
        resumo["diagnostico"] = {
            "servidor": d["servidor"],
            "migrations": {k: d["migrations"][k] for k in ("locais", "aplicadas", "ultima_aplicada", "faltando_no_servidor", "no_servidor_sem_arquivo_local")},
            "tabelas_ausentes": d["tabelas"]["ausentes"],
            "tabelas_tenant_sem_rls_ou_sem_policy": d["tabelas_tenant_sem_rls_ou_sem_policy"],
            "construtoras": [c["nome"] for c in d["integridade"]["construtoras"]],
            "usuarios": len(d["integridade"]["usuarios_mascarados"]),
        }
    if "semeadura" in resultado:
        s = resultado["semeadura"]
        resumo["semeadura"] = {k: s[k] for k in ("tenant_a", "tenant_b", "obra_a", "obra_b", "pedido_a", "nota_a")}
    if "isolamento" in resultado:
        checks = resultado["isolamento"]
        resumo["isolamento"] = {
            "pass": sum(1 for c in checks if c["resultado"] == "PASS"),
            "fail": sum(1 for c in checks if c["resultado"] == "FAIL"),
            "falhas": [c for c in checks if c["resultado"] == "FAIL"],
        }
    if "limpeza" in resultado:
        resumo["limpeza"] = resultado["limpeza"]
    print(json.dumps(resumo, ensure_ascii=False, indent=2, default=str))
    return 0 if not resumo.get("isolamento", {}).get("fail") and not resumo.get("limpeza", {}).get("motivo") else 1


if __name__ == "__main__":
    raise SystemExit(main())
