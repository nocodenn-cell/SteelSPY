"""P-08 (A4): a idempotência de /conferir considera `tipo`.

Antes, uma devolução com a mesma chave da entrada devolvia o resultado da entrada
e nunca era registrada. Agora cada (obra, NF, tipo) é uma conferência própria.
"""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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
    """TestClient com a role de aplicação (RLS ligado), como nos demais testes de API."""
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
def preparo(sql_owner: Any, cenario: dict[str, Any], monkeypatch) -> dict[str, Any]:
    """Entrada já conferida na obra A, com a mesma chave que virá na devolução."""
    from app.routers import conferencia as rota

    chave = _chave_valida("7" * 43)
    entrada_id = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, status_conferencia, "
                "xml_data, tipo) VALUES (:id, :t, :k, :o, 'VERDE', CAST(:x AS jsonb), 'entrada')"
            ),
            {
                "id": entrada_id,
                "t": cenario["tenant_a"],
                "k": chave,
                "o": cenario["obra_a"],
                "x": json.dumps(
                    {"resumo": {"total": 1, "verdes": 1, "amarelos": 0, "vermelhos": 0},
                     "alerta": "CONFORME", "detalhes": [], "motivos": [],
                     "modo_aprendizado": False, "itens_processados": []}
                ),
            },
        )

    buscas: list[str] = []

    def _buscar_xml(c: str) -> dict[str, Any]:
        buscas.append(c)
        return PAYLOAD_NF

    monkeypatch.setattr(rota, "buscar_xml_ou_json_por_chave", _buscar_xml)
    monkeypatch.setattr(rota, "_notificar_pos_conferencia", lambda *a, **k: None)
    return {"chave": chave, "entrada_id": entrada_id, "buscas": buscas}


def _linhas_da_chave(sql_owner: Any, obra: Any, chave: str) -> list[dict[str, Any]]:
    with sql_owner.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT id, tipo, status_conferencia, xml_data FROM nfe_logs "
                    "WHERE obra_id = :o AND chave_acesso = :k ORDER BY tipo"
                ),
                {"o": obra, "k": chave},
            ).mappings()
        ]


def test_devolucao_com_mesma_chave_da_entrada_vira_conferencia_propria(
    cliente: TestClient, cenario: dict[str, Any], sql_owner: Any, preparo: dict[str, Any]
) -> None:
    corpo = {
        "obra_id": str(cenario["obra_a"]),
        "chave_acesso": preparo["chave"],
        "tipo": "devolucao",
        "nf_original_id": str(preparo["entrada_id"]),
    }
    r = cliente.post("/conferir", json=corpo)
    assert r.status_code == 200, r.text
    devolucao_id = r.json()["nfe_log_id"]

    # Não é a entrada devolvida de volta.
    assert devolucao_id and devolucao_id != str(preparo["entrada_id"])
    assert preparo["buscas"] == [preparo["chave"]]  # a devolução foi de fato processada

    linhas = _linhas_da_chave(sql_owner, cenario["obra_a"], preparo["chave"])
    assert [l["tipo"] for l in linhas] == ["devolucao", "entrada"]

    entrada = next(l for l in linhas if l["tipo"] == "entrada")
    assert entrada["id"] == preparo["entrada_id"]
    assert entrada["status_conferencia"] == "VERDE"  # a entrada não foi sobrescrita


def test_entrada_repetida_continua_idempotente(
    cliente: TestClient, cenario: dict[str, Any], preparo: dict[str, Any]
) -> None:
    corpo = {"obra_id": str(cenario["obra_a"]), "chave_acesso": preparo["chave"], "tipo": "entrada"}
    r = cliente.post("/conferir", json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["nfe_log_id"] == str(preparo["entrada_id"])
    assert preparo["buscas"] == []  # devolveu o snapshot, sem buscar o XML de novo


def test_devolucao_repetida_devolve_a_propria_conferencia(
    cliente: TestClient, cenario: dict[str, Any], sql_owner: Any, preparo: dict[str, Any]
) -> None:
    corpo = {
        "obra_id": str(cenario["obra_a"]),
        "chave_acesso": preparo["chave"],
        "tipo": "devolucao",
        "nf_original_id": str(preparo["entrada_id"]),
    }
    primeira = cliente.post("/conferir", json=corpo).json()["nfe_log_id"]
    segunda = cliente.post("/conferir", json=corpo).json()["nfe_log_id"]
    assert primeira == segunda
    assert preparo["buscas"] == [preparo["chave"]]  # a segunda veio do snapshot


def test_banco_recusa_segunda_entrada_com_mesma_chave_na_obra(
    sql_owner: Any, cenario: dict[str, Any], preparo: dict[str, Any]
) -> None:
    """A unicidade passa a ser (obra, chave, tipo): duas entradas iguais continuam proibidas."""
    with pytest.raises(IntegrityError):
        with sql_owner.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO nfe_logs (tenant_id, chave_acesso, obra_id, status_conferencia, tipo) "
                    "VALUES (:t, :k, :o, 'PENDENTE', 'entrada')"
                ),
                {"t": cenario["tenant_a"], "k": preparo["chave"], "o": cenario["obra_a"]},
            )
