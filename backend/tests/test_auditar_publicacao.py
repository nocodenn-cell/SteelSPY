"""Contrato da auditoria de publicação: contrato de env e segredos versionados.

Os testes usam valores inventados. Nenhum teste aqui autentica, conecta ou lê
credencial real — o que se prova é a regra: o que bloqueia, o que só avisa e o
que passa.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import pathlib
import uuid
from typing import Any

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _carregar() -> Any:
    caminho = RAIZ / "scripts" / "auditar_publicacao.py"
    spec = importlib.util.spec_from_file_location("_auditar_publicacao", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


auditoria = _carregar()

BASE: dict[str, str] = {
    "DATABASE_URL": (
        "postgresql+psycopg2://stellspy_app.ref:s3cr3t-abc-123"
        "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    ),
    "PWA_SESSION_SECRET": "x" * 40,
    "CORS_ALLOW_ORIGINS": "https://app.steelspy.com.br",
    "SKIP_API_KEY": "0",
    "PWA_COOKIE_SECURE": "1",
    "EVIDENCIAS_STORAGE": "supabase",
    "DASHBOARD_DATABASE_URL": (
        "postgresql+psycopg2://stellspy_dashboard:s3cr3t-dash-1@localhost:55432/stellspy"
    ),
    "DASHBOARD_TENANT_ID": str(uuid.uuid4()),
}


def _situacoes(itens: list[tuple[str, str, str]], nome: str) -> set[str]:
    return {s for n, s, _ in itens if n == nome}


def _com(**mudancas: str) -> list[tuple[str, str, str]]:
    valores = {**BASE, **mudancas}
    return auditoria.avaliar_env(valores)


def _jwt(papel: str) -> str:
    def parte(dados: dict[str, str]) -> str:
        bruto = json.dumps(dados).encode()
        return base64.urlsafe_b64encode(bruto).rstrip(b"=").decode()

    return f"{parte({'alg': 'HS256'})}.{parte({'role': papel})}.{'a' * 16}"


# ---------------------------------------------------------------------------
# Contrato do .env
# ---------------------------------------------------------------------------


def test_configuracao_completa_nao_bloqueia() -> None:
    itens = auditoria.avaliar_env(BASE)
    assert not [i for i in itens if i[1] == "BLOQUEADO"], itens


def test_credencial_administrativa_na_api_bloqueia() -> None:
    itens = _com(
        DATABASE_URL="postgresql+psycopg2://postgres.ref:s3cr3t-abc-123@pooler.supabase.com:5432/postgres"  # credencial-de-exemplo
    )
    assert "BLOQUEADO" in _situacoes(itens, "DATABASE_URL")


def test_placeholder_de_senha_bloqueia() -> None:
    itens = _com(DATABASE_URL="postgresql+psycopg2://stellspy_app:[SENHA_APP]@host:5432/db")
    assert "BLOQUEADO" in _situacoes(itens, "DATABASE_URL")


def test_segredo_de_sessao_curto_bloqueia() -> None:
    assert "BLOQUEADO" in _situacoes(_com(PWA_SESSION_SECRET="curto"), "PWA_SESSION_SECRET")


def test_curinga_de_cors_bloqueia() -> None:
    assert "BLOQUEADO" in _situacoes(_com(CORS_ALLOW_ORIGINS="*"), "CORS_ALLOW_ORIGINS")


def test_https_com_cookie_sem_secure_bloqueia() -> None:
    assert "BLOQUEADO" in _situacoes(_com(PWA_COOKIE_SECURE="0"), "PWA_COOKIE_SECURE")


def test_desligar_credencial_da_api_bloqueia() -> None:
    assert "BLOQUEADO" in _situacoes(_com(SKIP_API_KEY="1"), "SKIP_API_KEY")


def test_dashboard_com_credencial_administrativa_bloqueia() -> None:
    itens = _com(
        DASHBOARD_DATABASE_URL="postgresql+psycopg2://postgres.ref:x@pooler.supabase.com:5432/postgres"  # credencial-de-exemplo
    )
    assert "BLOQUEADO" in _situacoes(itens, "DASHBOARD_DATABASE_URL")


def test_dashboard_com_usuario_do_pooler_nao_bloqueia() -> None:
    # O pooler do Supabase exige o usuário no formato <role>.<ref>.
    itens = _com(
        DASHBOARD_DATABASE_URL=(
            "postgresql+psycopg2://stellspy_dashboard.ref:s3cr3t-dash-1"
            "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
        )
    )
    assert "BLOQUEADO" not in _situacoes(itens, "DASHBOARD_DATABASE_URL")


def test_dashboard_sem_tenant_explicito_bloqueia() -> None:
    assert "BLOQUEADO" in _situacoes(_com(DASHBOARD_TENANT_ID="qualquer-obra"), "DASHBOARD_TENANT_ID")


def test_banco_local_apenas_avisa() -> None:
    itens = _com(DATABASE_URL="postgresql+psycopg2://stellspy_app:x@localhost:55432/stellspy")
    assert "BLOQUEADO" not in _situacoes(itens, "DATABASE_URL")
    assert "AVISO" in _situacoes(itens, "DATABASE_URL")


def test_mock_de_nfe_apenas_avisa() -> None:
    assert "BLOQUEADO" not in _situacoes(_com(NFE_IO_MOCK="1"), "NFE_IO_MOCK")


# ---------------------------------------------------------------------------
# Varredura de segredos versionados
# ---------------------------------------------------------------------------


def _varrer(tmp_path: pathlib.Path, nome: str, conteudo: str) -> list[tuple[str, str, str]]:
    (tmp_path / nome).write_text(conteudo, encoding="utf-8")
    return auditoria.auditar_arquivos(tmp_path, [pathlib.Path(nome)])


def test_jwt_de_service_role_bloqueia(tmp_path: pathlib.Path) -> None:
    itens = _varrer(tmp_path, "config.py", f"CHAVE = '{_jwt('service_role')}'\n")
    assert any(s == "BLOQUEADO" and "service_role" in d for _, s, d in itens)


def test_jwt_anon_apenas_avisa(tmp_path: pathlib.Path) -> None:
    itens = _varrer(tmp_path, "config.py", f"CHAVE = '{_jwt('anon')}'\n")
    assert any(s == "AVISO" and "anon" in d for _, s, d in itens)


def test_chave_privada_bloqueia(tmp_path: pathlib.Path) -> None:
    # Montada em runtime para o próprio arquivo de teste não parecer uma chave.
    chave = "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIE...\n"
    itens = _varrer(tmp_path, "id.pem", chave)
    assert any(s == "BLOQUEADO" for _, s, _ in itens)


def test_senha_real_de_producao_em_url_bloqueia(tmp_path: pathlib.Path) -> None:
    conteudo = (
        "DATABASE_URL=postgresql://stellspy_app.ref:s3cr3t-abc-123"
        "@aws-0-sa-east-1.pooler.supabase.com:5432/postgres\n"
    )
    itens = _varrer(tmp_path, "anota.txt", conteudo)
    assert any(s == "BLOQUEADO" and "senha de banco" in d for _, s, d in itens)


def test_senha_local_e_placeholder_nao_bloqueiam(tmp_path: pathlib.Path) -> None:
    conteudo = (
        "DATABASE_URL=postgresql://stellspy_app:dev-local-app-password@localhost:55432/stellspy\n"
        "SUPABASE_DB_ADMIN_URL=postgresql://postgres.ref:[SENHA_POSTGRES]@pooler.supabase.com:5432/postgres\n"
    )
    itens = _varrer(tmp_path, "teste.py", conteudo)
    assert not [i for i in itens if i[1] == "BLOQUEADO"], itens


def test_fixture_marcada_como_exemplo_nao_bloqueia(tmp_path: pathlib.Path) -> None:
    """A marca é explícita e visível no diff; senha real sem marca continua bloqueando."""
    conteudo = (
        "url = postgresql://postgres.ref:s3cr3t-abc-123@pooler.supabase.com:5432/x"  # credencial-de-exemplo
        "  # credencial-de-exemplo\n"
    )
    itens = _varrer(tmp_path, "test_exemplo.py", conteudo)
    assert not [i for i in itens if i[1] == "BLOQUEADO"], itens


def test_env_versionado_bloqueia(tmp_path: pathlib.Path) -> None:
    itens = _varrer(tmp_path, ".env", "PWA_SESSION_SECRET=abc\n")
    assert any(s == "BLOQUEADO" and "ambiente" in d for _, s, d in itens)


def test_exemplo_de_env_nao_bloqueia(tmp_path: pathlib.Path) -> None:
    itens = _varrer(tmp_path, ".env.example", "PWA_SESSION_SECRET=\nSTELLSPY_APP_PASSWORD=\n")
    assert not [i for i in itens if i[1] == "BLOQUEADO"], itens


def test_segredo_atribuido_no_codigo_bloqueia(tmp_path: pathlib.Path) -> None:
    itens = _varrer(tmp_path, "settings.py", "PWA_SESSION_SECRET=abc123def456ghi789\n")
    assert any(s == "BLOQUEADO" for _, s, _ in itens)


def test_api_base_preenchido_no_index_avisa(tmp_path: pathlib.Path) -> None:
    itens = _varrer(
        tmp_path, "index.html", '{"apiBaseUrl": "http://localhost:8000"}'
    )
    assert any(s == "AVISO" and "apiBaseUrl" in d for _, s, d in itens)


def test_repositorio_versionado_nao_tem_segredo_bloqueante() -> None:
    """O próprio teste entra na varredura: fixture sintética precisa da marca."""
    arquivos = auditoria._arquivos_git(auditoria.RAIZ_REPO)
    itens = auditoria.auditar_arquivos(auditoria.RAIZ_REPO, arquivos)
    bloqueios = [i for i in itens if i[1] == "BLOQUEADO"]
    assert not bloqueios, bloqueios


# ---------------------------------------------------------------------------
# Código de saída
# ---------------------------------------------------------------------------


def test_main_bloqueia_com_env_incompleto(tmp_path: pathlib.Path) -> None:
    env = tmp_path / ".env"
    env.write_text("SKIP_API_KEY=1\n", encoding="utf-8")
    assert auditoria.main(["--env-file", str(env), "--sem-scan"]) == 2


def test_main_aprova_env_completo(tmp_path: pathlib.Path) -> None:
    env = tmp_path / ".env"
    env.write_text("\n".join(f"{k}={v}" for k, v in BASE.items()) + "\n", encoding="utf-8")
    assert auditoria.main(["--env-file", str(env), "--sem-scan"]) == 0
