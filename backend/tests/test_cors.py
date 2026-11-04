"""CORS de publicação: origens exatas, sem curinga e sem credencial embutida."""

from __future__ import annotations

import pytest

from app.cors import origens_permitidas


def test_sem_configuracao_nao_libera_origem_nenhuma() -> None:
    assert origens_permitidas(None) == []
    assert origens_permitidas("") == []
    assert origens_permitidas("  ,  ") == []


def test_lista_exata_e_normalizada() -> None:
    assert origens_permitidas(" https://app.steelspy.com.br , http://localhost:8080 ") == [
        "https://app.steelspy.com.br",
        "http://localhost:8080",
    ]


def test_origem_repetida_aparece_uma_vez() -> None:
    assert origens_permitidas("https://app.x, HTTPS://APP.X") == ["https://app.x"]


def test_barra_final_e_normalizada() -> None:
    """O navegador manda `origin` sem barra; a configuração com barra não pode virar CORS quebrado."""
    assert origens_permitidas("https://app.x/") == ["https://app.x"]


@pytest.mark.parametrize(
    "valor",
    [
        "*",
        "https://a.x, *",
        "null",
        "ftp://app.x",
        "app.x",
        "https://app.x/caminho",
        "https://app.x?x=1",
        "https://user:senha@app.x",
        "https://app.x:porta",
    ],
)
def test_configuracao_ambigua_e_recusada(valor: str) -> None:
    with pytest.raises(ValueError):
        origens_permitidas(valor)


def test_localhost_com_porta_serve_ao_adb() -> None:
    """O caminho de teste físico por `adb reverse` usa localhost, não um domínio."""
    assert origens_permitidas("http://localhost:8080") == ["http://localhost:8080"]
    assert origens_permitidas("http://127.0.0.1:8080") == ["http://127.0.0.1:8080"]
