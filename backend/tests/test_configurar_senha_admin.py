"""A senha entra na URL percent-encoded, e o resto da URL é preservado."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "configurar_senha_admin.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("_configurar_senha", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


config = _modulo()


def test_arroba_e_dois_pontos_sao_codificados():
    url = config.montar_url(
        "postgresql://postgres.ref:antiga@aws-0-us-east-2.pooler.supabase.com:5432/postgres",  # credencial-de-exemplo
        "a@b:c",
    )
    assert url == "postgresql://postgres.ref:a%40b%3Ac@aws-0-us-east-2.pooler.supabase.com:5432/postgres"  # credencial-de-exemplo


def test_preserva_scheme_e_host():
    url = config.montar_url(
        "postgresql+psycopg2://postgres.ref:[SENHA]@host.example:6543/db",
        "s3nh@",
    )
    assert url.startswith("postgresql+psycopg2://postgres.ref:")
    assert url.endswith("@host.example:6543/db")
    assert "s3nh%40" in url


def test_url_incompleta_falha():
    try:
        config.montar_url("postgresql://postgres.ref", "x")
    except ValueError as exc:
        assert "incompleta" in str(exc)
    else:
        raise AssertionError("deveria recusar URL sem host")
