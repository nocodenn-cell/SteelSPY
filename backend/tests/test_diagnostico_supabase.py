"""Funções puras do diagnóstico: ref, região, diff de migrations e máscara.

Não tocam rede nem banco — o que se testa aqui é que o relatório não confunde
projeto, não esconde migration pendente e não vaza senha em mensagem de erro.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnostico_supabase.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("_diagnostico_supabase", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


diag = _modulo()


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://akvbtceshpsvsuacueaq.supabase.co", "akvbtceshpsvsuacueaq"),
        ("https://akvbtceshpsvsuacueaq.supabase.co/", "akvbtceshpsvsuacueaq"),
        ("http://xgirdwumztdhksubjzhn.supabase.co", "xgirdwumztdhksubjzhn"),
        ("https://exemplo.com", None),
        ("https://akvbtceshpsvsuacueaq.supabase.co.evil.com", None),
        ("", None),
    ],
)
def test_ref_da_url(url: str, esperado: str | None):
    assert diag.ref_da_url(url) == esperado


def test_regiao_sai_do_host_do_pooler():
    assert diag.regiao_do_host("aws-0-sa-east-1.pooler.supabase.com") == "sa-east-1"
    assert diag.regiao_do_host("aws-1-us-east-1.pooler.supabase.com") == "us-east-1"
    assert diag.regiao_do_host("db.akvbtceshpsvsuacueaq.supabase.co") is None


def test_diferenca_aponta_pendente_e_orfao():
    diferenca = diag.diferenca_migrations(
        aplicadas=["1", "2", "3"],
        locais=["1", "2", "3", "4"],
    )
    assert diferenca == {"pendentes_no_banco": ["4"], "no_banco_sem_arquivo": []}

    diferenca = diag.diferenca_migrations(aplicadas=["1", "9"], locais=["1"])
    assert diferenca == {"pendentes_no_banco": [], "no_banco_sem_arquivo": ["9"]}


def test_senha_e_mascarada_em_mensagem_de_erro():
    texto = "could not connect to postgresql://postgres.akvbtceshpsvsuacueaq:segredo123@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
    mascarado = diag.mascarar(texto)
    assert "segredo123" not in mascarado
    assert "***@" in mascarado


@pytest.mark.parametrize(
    ("url", "trecho"),
    [
        (
            "postgresql://postgres.ref:senha-real@aws-0-sa-east-1.pooler.supabase.com:5432/postgres",
            None,
        ),
        (
            "postgresql://postgres.ref:[SENHA_POSTGRES]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres",
            "colchetes",
        ),
        (
            "postgresql+psycopg2://stellspy_app.ref:senha@<HOST_POOLER>:5432/postgres",
            "exemplo",
        ),
        ("postgresql://postgres.ref@host:5432/postgres", "senha ausente"),
        ("mysql://postgres.ref:senha@host:5432/postgres", "esquema"),
        ("postgresql://postgres.ref:senha@host:5432", "banco ausente"),
    ],
)
def test_problema_na_url_postgres(url: str, trecho: str | None):
    motivo = diag.problema_na_url_postgres(url)
    if trecho is None:
        assert motivo is None
    else:
        assert motivo is not None
        assert trecho in motivo


def test_motivo_da_url_nao_devolve_senha():
    motivo = diag.problema_na_url_postgres(
        "postgresql+psycopg2://stellspy_app.ref:segredo123@<HOST_POOLER>:5432/postgres"
    )
    assert motivo is not None
    assert "segredo123" not in motivo


def test_env_file_nao_sobrescreve_ambiente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("SUPABASE_URL=https://arquivo.supabase.co\nNOVA_CHAVE=abc\n", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_URL", "https://ambiente.supabase.co")
    monkeypatch.delenv("NOVA_CHAVE", raising=False)

    diag.carregar_env(arquivo)

    assert os.environ["SUPABASE_URL"] == "https://ambiente.supabase.co"
    assert os.environ["NOVA_CHAVE"] == "abc"
