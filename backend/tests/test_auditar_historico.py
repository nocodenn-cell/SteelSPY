"""Contrato do scanner de histórico Git.

Cada teste monta um repositório git descartável, comita um caso e confere a
classificação. Os valores são inventados: o que se prova é a regra, e que a
saída nunca reproduz o segredo encontrado.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
SEGREDO = "SenhaRealDoSistema9x"


def _carregar() -> Any:
    caminho = RAIZ / "scripts" / "auditar_historico.py"
    spec = importlib.util.spec_from_file_location("_auditar_historico", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


auditoria = _carregar()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Teste", "-c", "user.email=teste@example.invalid", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _comitar(repo: Path, caminho: str, conteudo: str, mensagem: str = "carga") -> None:
    arquivo = repo / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(conteudo, encoding="utf-8")
    _git(repo, "add", caminho)
    _git(repo, "commit", "-q", "-m", mensagem)


def _analisar(repo: Path):
    return auditoria.analisar(repo, "--all")


def _rodar(capsys, repo: Path) -> tuple[int, str]:
    codigo = auditoria.main(["--repo", str(repo), "--verboso"])
    return codigo, capsys.readouterr().out


def _jwt(papel: str) -> str:
    def parte(dados: dict[str, str]) -> str:
        bruto = json.dumps(dados).encode()
        return base64.urlsafe_b64encode(bruto).rstrip(b"=").decode()

    return f"{parte({'alg': 'HS256'})}.{parte({'role': papel})}.c2lnbmF0dXJhLWRlLXRlc3Rl"


def test_repositorio_sem_segredo_passa(tmp_path, capsys):
    repo = _repo(tmp_path)
    _comitar(repo, "app/leiame.py", "VALOR = 1\n")

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 0
    assert "0 bloqueio(s)" in saida


def test_env_versionado_bloqueia_sem_reproduzir_o_valor(tmp_path, capsys):
    repo = _repo(tmp_path)
    _comitar(repo, ".env", f"PWA_SESSION_SECRET={SEGREDO}\n")

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 2
    assert ".env" in saida
    assert "arquivo .env versionado" in saida
    assert SEGREDO not in saida


def test_url_de_banco_real_em_codigo_bloqueia(tmp_path, capsys):
    repo = _repo(tmp_path)
    url = f"postgresql://stellspy_app.ref:{SEGREDO}@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    _comitar(repo, "app/config.py", f'DATABASE_URL = "{url}"\n')

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 2
    assert "URL de banco com senha" in saida
    assert SEGREDO not in saida
    assert ":***@" in saida


def test_atribuicao_de_segredo_em_codigo_bloqueia(tmp_path, capsys):
    repo = _repo(tmp_path)
    _comitar(repo, "app/config.py", f"PWA_SESSION_SECRET={SEGREDO}\n")

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 2
    assert "atribuição de segredo" in saida
    assert SEGREDO not in saida


def test_fixture_sintetica_em_teste_nao_bloqueia(tmp_path, capsys):
    repo = _repo(tmp_path)
    url = "postgresql://postgres.ref:s3cr3t@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    _comitar(repo, "tests/test_exemplo.py", f'URL = "{url}"\n')

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 0
    assert "1 sintético(s)" in saida


def test_placeholder_de_documentacao_nao_bloqueia(tmp_path, capsys):
    repo = _repo(tmp_path)
    _comitar(
        repo,
        "docs/SETUP.md",
        "export DATABASE_URL='postgresql://app:[SENHA]@aws-0-<regiao>.pooler.supabase.com:5432/postgres'\n",
    )

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 0
    assert "1 sintético(s)" in saida


def test_jwt_service_role_bloqueia_sem_imprimir_token(tmp_path, capsys):
    repo = _repo(tmp_path)
    token = _jwt("service_role")
    _comitar(repo, "app/config.py", f'CHAVE = "{token}"\n')

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 2
    assert "JWT" in saida
    assert "role=service_role" in saida
    assert token not in saida


def test_mensagem_de_commit_tambem_e_varrida(tmp_path, capsys):
    repo = _repo(tmp_path)
    url = f"postgresql://postgres.ref:{SEGREDO}@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    _comitar(repo, "app/leiame.py", "VALOR = 1\n", mensagem=f"config {url}")

    codigo, saida = _rodar(capsys, repo)

    assert codigo == 2
    assert "(mensagem do commit)" in saida
    assert SEGREDO not in saida
