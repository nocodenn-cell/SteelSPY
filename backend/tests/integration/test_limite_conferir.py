"""M4: teto de consultas pagas por obra em /conferir e correlation_id por requisição.

Cada consulta que vai à NFe.io tem custo. O limite conta só essas consultas:
respostas idempotentes (NF já conferida) não gastam cota.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.utils.chave_nfe import _digito_verificador_chave

PAYLOAD_NF = {
    "itens": [
        {
            "descricao": "VERGALHAO CA-50 10MM",
            "bitola_mm": 10.0,
            "quantidade": 10.0,
            "unidade": "KG",
            "marca": "GERDAU",
        }
    ]
}


def _chave_valida(base43: str) -> str:
    return base43 + str(_digito_verificador_chave(base43))


@pytest.fixture()
def cliente(sessao_app_factory: Any) -> Any:
    from app.db import get_db
    from app.main import app

    def _get_db():
        session = sessao_app_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def buscas(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from app.routers import conferencia as rota

    chamadas: list[str] = []

    def _buscar_xml(c: str) -> dict[str, Any]:
        chamadas.append(c)
        return PAYLOAD_NF

    monkeypatch.setattr(rota, "buscar_xml_ou_json_por_chave", _buscar_xml)
    monkeypatch.setattr(rota, "_notificar_pos_conferencia", lambda *a, **k: None)
    return chamadas


@pytest.fixture()
def limite_pequeno(monkeypatch: pytest.MonkeyPatch) -> int:
    from app.limite_tentativas import limite

    monkeypatch.setenv("CONFERIR_LIMITE_POR_OBRA", "2")
    monkeypatch.setenv("CONFERIR_JANELA_SEGUNDOS", "3600")
    limite().resetar()
    yield 2
    limite().resetar()


def _corpo(obra: Any, chave: str) -> dict[str, Any]:
    return {"obra_id": str(obra), "chave_acesso": chave}


def test_consultas_acima_do_teto_por_obra_viram_429(
    cliente: TestClient,
    cenario: dict[str, Any],
    buscas: list[str],
    limite_pequeno: int,
) -> None:
    chaves = [_chave_valida(str(n) * 43) for n in range(1, 4)]

    assert cliente.post("/conferir", json=_corpo(cenario["obra_a"], chaves[0])).status_code == 200
    assert cliente.post("/conferir", json=_corpo(cenario["obra_a"], chaves[1])).status_code == 200

    r = cliente.post("/conferir", json=_corpo(cenario["obra_a"], chaves[2]))
    assert r.status_code == 429, r.text
    assert int(r.headers["Retry-After"]) >= 1
    # a consulta bloqueada não chegou à API paga
    assert chaves[2] not in buscas
    assert len(buscas) == 2


def test_resposta_idempotente_nao_gasta_cota_nem_e_bloqueada(
    cliente: TestClient,
    cenario: dict[str, Any],
    buscas: list[str],
    limite_pequeno: int,
) -> None:
    chave_1 = _chave_valida("5" * 43)
    chave_2 = _chave_valida("6" * 43)
    assert cliente.post("/conferir", json=_corpo(cenario["obra_a"], chave_1)).status_code == 200
    assert cliente.post("/conferir", json=_corpo(cenario["obra_a"], chave_2)).status_code == 200

    # teto atingido, mas a NF já conferida é devolvida do banco
    r = cliente.post("/conferir", json=_corpo(cenario["obra_a"], chave_1))
    assert r.status_code == 200, r.text
    assert len(buscas) == 2


def test_teto_e_por_obra_outra_obra_continua_consultando(
    cliente: TestClient,
    cenario: dict[str, Any],
    buscas: list[str],
    limite_pequeno: int,
) -> None:
    for n in range(1, 3):
        cliente.post("/conferir", json=_corpo(cenario["obra_a"], _chave_valida(str(n) * 43)))
    assert cliente.post("/conferir", json=_corpo(cenario["obra_a"], _chave_valida("9" * 43))).status_code == 429

    r = cliente.post("/conferir", json=_corpo(cenario["obra_b"], _chave_valida("8" * 43)))
    assert r.status_code == 200, r.text


def test_correlation_id_do_cliente_e_devolvido(
    cliente: TestClient, cenario: dict[str, Any], buscas: list[str]
) -> None:
    r = cliente.post(
        "/conferir",
        json=_corpo(cenario["obra_a"], _chave_valida("3" * 43)),
        headers={"X-Correlation-ID": "req-abc-12345678"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["X-Correlation-ID"] == "req-abc-12345678"


def test_correlation_id_invalido_e_substituido_por_um_gerado(
    cliente: TestClient, cenario: dict[str, Any], buscas: list[str]
) -> None:
    # espaço e caractere de controle não entram no log nem no cabeçalho
    r = cliente.post(
        "/conferir",
        json=_corpo(cenario["obra_a"], _chave_valida("4" * 43)),
        headers={"X-Correlation-ID": "ruim com espaco"},
    )
    assert r.status_code == 200, r.text
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Correlation-ID"])
