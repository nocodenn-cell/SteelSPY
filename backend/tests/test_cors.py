"""CORS de publicação: origens exatas, sem curinga e sem credencial embutida."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.cors import configurar_cors, origens_permitidas

ORIGEM_PWA = "http://localhost:8080"


def _cliente(valor: str | None) -> TestClient:
    aplicacao = FastAPI()

    @aplicacao.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @aplicacao.delete("/correlacoes/1")
    def apagar() -> dict[str, bool]:
        return {"ok": True}

    @aplicacao.post("/evidencias")
    def enviar() -> dict[str, bool]:
        return {"ok": True}

    @aplicacao.get("/dossie.pdf")
    def dossie() -> Response:
        return Response(
            b"%PDF",
            headers={
                "X-Dossie-Id": "abc",
                "X-Conteudo-Sha256": "def",
                "Content-Disposition": "attachment; filename=dossie.pdf",
            },
        )

    configurar_cors(aplicacao, valor)
    return TestClient(aplicacao)


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


def test_origem_permitida_recebe_credencial() -> None:
    resposta = _cliente(ORIGEM_PWA).get("/ping", headers={"Origin": ORIGEM_PWA})
    assert resposta.status_code == 200
    assert resposta.headers["access-control-allow-origin"] == ORIGEM_PWA
    assert resposta.headers["access-control-allow-credentials"] == "true"


def test_preflight_libera_delete_da_correlacao() -> None:
    """O PWA desfaz correlação com DELETE; sem ele o navegador barra a chamada."""
    resposta = _cliente(ORIGEM_PWA).options(
        "/correlacoes/1",
        headers={
            "Origin": ORIGEM_PWA,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "x-csrf-token",
        },
    )
    assert resposta.status_code == 200
    assert "DELETE" in resposta.headers["access-control-allow-methods"]
    assert "x-csrf-token" in resposta.headers["access-control-allow-headers"].lower()


def test_preflight_libera_upload_com_csrf() -> None:
    resposta = _cliente(ORIGEM_PWA).options(
        "/evidencias",
        headers={
            "Origin": ORIGEM_PWA,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert resposta.status_code == 200
    assert "POST" in resposta.headers["access-control-allow-methods"]
    assert "x-csrf-token" in resposta.headers["access-control-allow-headers"].lower()


def test_origem_fora_da_lista_nao_recebe_cabecalho() -> None:
    resposta = _cliente(ORIGEM_PWA).get(
        "/ping", headers={"Origin": "https://outra.example"}
    )
    assert resposta.status_code == 200
    assert "access-control-allow-origin" not in resposta.headers


def test_sem_origem_configurada_nao_ha_cors() -> None:
    resposta = _cliente("").get("/ping", headers={"Origin": ORIGEM_PWA})
    assert "access-control-allow-origin" not in resposta.headers


def test_cabecalhos_do_dossie_ficam_visiveis_ao_pwa() -> None:
    resposta = _cliente(ORIGEM_PWA).get(
        "/dossie.pdf", headers={"Origin": ORIGEM_PWA}
    )
    expostos = resposta.headers["access-control-expose-headers"].lower()
    assert "x-dossie-id" in expostos
    assert "x-conteudo-sha256" in expostos
    assert "content-disposition" in expostos


def test_configuracao_ambigua_falha_antes_de_subir() -> None:
    with pytest.raises(ValueError):
        configurar_cors(FastAPI(), "*")
