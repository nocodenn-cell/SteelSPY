"""Contrato do portão de entrada do dashboard.

O painel falha fechado: sem senha configurada ele não abre. Estes testes não
carregam Streamlit — exercitam a regra pura em `dashboard/auth.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]


def _carregar() -> Any:
    caminho = RAIZ / "dashboard" / "auth.py"
    spec = importlib.util.spec_from_file_location("_dashboard_auth", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


auth = _carregar()


def test_sem_senha_o_painel_nao_abre():
    for valor in (None, "", "   "):
        recusa = auth.motivo_recusa(valor)
        assert recusa is not None
        assert "DASHBOARD_PASSWORD" in recusa


def test_senha_curta_e_recusada():
    recusa = auth.motivo_recusa("x" * (auth.MINIMO_SENHA - 1))
    assert recusa is not None
    assert str(auth.MINIMO_SENHA) in recusa


def test_senha_no_limite_minimo_e_aceita():
    assert auth.motivo_recusa("x" * auth.MINIMO_SENHA) is None


def test_espacos_ao_redor_sao_ignorados():
    senha = "x" * auth.MINIMO_SENHA
    assert auth.senha_configurada(f"  {senha}  ") == senha


def test_comparacao_reconhece_igual_e_diferente():
    senha = "senha-de-piloto-1234"
    assert auth.senha_confere(senha, senha) is True
    assert auth.senha_confere("outra-senha-qualquer", senha) is False
    assert auth.senha_confere("", senha) is False


def test_mensagem_de_recusa_nao_reproduz_o_valor():
    curta = "curta"
    recusa = auth.motivo_recusa(curta)
    assert recusa is not None
    assert curta not in recusa
