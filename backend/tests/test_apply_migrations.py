"""Leitura do arquivo local e recusa de URL-modelo no runner de migrations."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_migrations.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("_apply_migrations_env", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


runner = _modulo()


def test_ler_env_retorna_pares(tmp_path: Path):
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "# comentário\nSUPABASE_DB_ADMIN_URL=postgresql://u:p@h:5432/db\nVAZIA=\n",
        encoding="utf-8",
    )
    valores = runner.ler_env(arquivo)
    assert valores["SUPABASE_DB_ADMIN_URL"] == "postgresql://u:p@h:5432/db"
    assert valores["VAZIA"] == ""


def test_ler_env_ausente_nao_falha(tmp_path: Path):
    assert runner.ler_env(tmp_path / "nao-existe") == {}


def test_main_recusa_url_com_placeholder(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_ADMIN_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "SUPABASE_DB_ADMIN_URL=postgresql://postgres.ref:[SENHA_POSTGRES]@host:5432/postgres\n",
        encoding="utf-8",
    )
    assert runner.main(["--env-file", str(arquivo), "--dir", str(tmp_path)]) == 2


def test_main_recusa_senha_com_arroba_sem_codificacao(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_ADMIN_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "SUPABASE_DB_ADMIN_URL=postgresql://postgres.ref:se@nha@host:5432/postgres\n",
        encoding="utf-8",
    )
    assert runner.main(["--env-file", str(arquivo), "--dir", str(tmp_path)]) == 2
