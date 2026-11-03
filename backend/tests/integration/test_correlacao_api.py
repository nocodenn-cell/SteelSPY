"""Sprint 3 / P0: correlação determinística entre pedido e NF-e, pela API.

O que estes testes protegem é o defeito que o produto tinha: duas linhas do mesmo
pedido, ambas de 10 mm, consumiam o *mesmo* item faturado. A conciliação respondia
VERDE com o ferro contado duas vezes.

A regra que se verifica aqui, na ordem do fluxo real do celular:

- duas linhas da mesma bitola com um item só -> ambiguidade, nunca VERDE;
- código de produto no pedido decide a associação sem intervenção humana;
- correlação explícita resolve a ambiguidade e fica auditada com autor;
- entrega parcial em duas NF-e soma uma vez só;
- item faturado sem pedido e linha pedida sem fatura aparecem na resposta;
- o que é de outra construtora responde 404, e o que o papel não permite responde 403.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.seguranca import hash_senha

SENHA = "SenhaForte#123"


# ---------------------------------------------------------------------------
# Fixtures e auxiliares (mesmo contrato de test_pedidos.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _limite_zerado() -> Any:
    from app.limite_tentativas import limite

    limite().resetar()
    yield
    limite().resetar()


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
def equipe(sql_owner: Any, cenario: dict[str, Any]) -> dict[str, Any]:
    """eng, fiscal e o admin da construtora concorrente, todos com senha."""
    sufixo = uuid.uuid4().hex[:8]
    definicao = {
        "eng": ("engenheiro", cenario["tenant_a"], cenario["obra_a"]),
        "fiscal": ("fiscal", cenario["tenant_a"], cenario["obra_a"]),
        "admin_b": ("admin_tenant", cenario["tenant_b"], cenario["obra_b"]),
    }
    emails: dict[str, str] = {}
    ids: dict[str, uuid.UUID] = {}
    senha_hash = hash_senha(SENHA)

    with sql_owner.begin() as conn:
        for chave, (papel_global, tenant, obra) in definicao.items():
            uid = uuid.uuid4()
            email = f"corr.{chave}.{sufixo}@teste.local"
            emails[chave], ids[chave] = email, uid
            conn.execute(
                text(
                    "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                    "VALUES (:id, :t, :n, :e, :h, :p)"
                ),
                {"id": uid, "t": tenant, "n": chave, "e": email, "h": senha_hash, "p": papel_global},
            )
            conn.execute(
                text(
                    "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) VALUES "
                    "(:t, :o, :u, :p)"
                ),
                {
                    "t": tenant, "o": obra, "u": uid,
                    "p": "engenheiro" if papel_global == "admin_tenant" else papel_global,
                },
            )
    return {**cenario, "emails": emails, "ids": ids}


def _login(cliente: TestClient, email: str) -> str:
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _post(cliente: TestClient, url: str, corpo: dict, csrf: str | None) -> Any:
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return cliente.post(url, json=corpo, headers=headers)


def _fornecedor(cliente: TestClient, obra: Any, csrf: str, cnpj: str) -> str:
    r = _post(
        cliente, f"/obras/{obra}/fornecedores",
        {"cnpj": cnpj, "razao_social": "Aco Brasil Ltda"}, csrf,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _linha(
    *, quantidade: float = 1000.0, unidade: str = "M", bitola: float | None = 10.0,
    codigo: str | None = None, material: str = "CA-50",
) -> dict:
    """Linha de pedido; a numeração da linha vem da ordem de envio."""
    return {
        "material_tipo": material,
        "categoria_material": "aco" if bitola is not None else "cimento",
        "bitola_mm": bitola,
        "marca_exigida": "GERDAU",
        "quantidade": quantidade,
        "unidade": unidade,
        "codigo_produto_fornecedor": codigo,
    }


def _pedido(cliente: TestClient, obra: Any, csrf: str, fornecedor: str, itens: list[dict]) -> dict:
    r = _post(
        cliente, f"/obras/{obra}/pedidos",
        {"fornecedor_id": fornecedor, "numero": uuid.uuid4().hex[:8], "itens": itens}, csrf,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _nota(
    sql_owner: Any, *, tenant: Any, obra: Any, itens: list[dict], cnpj: str,
    pedido_id: Any = None,
) -> uuid.UUID:
    """Insere nfe_log com os itens faturados em `xml_data` — o mesmo formato do parser."""
    nfe_id = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, pedido_id, "
                "status_conferencia, xml_data) VALUES "
                "(:id, :t, :k, :o, :p, 'VERDE', CAST(:x AS jsonb))"
            ),
            {
                "id": nfe_id, "t": tenant, "o": obra, "p": pedido_id,
                "k": f"{uuid.uuid4().int % 10**44:044d}",
                "x": json.dumps({"emitente_cnpj": cnpj, "itens": itens}),
            },
        )
    return nfe_id


def _item_nf(
    *, n_item: int, quantidade: float, unidade: str = "M", bitola: float | None = 10.0,
    codigo: str | None = None, marca: str = "GERDAU",
) -> dict:
    d = {
        "nItem": n_item,
        "quantidade": quantidade,
        "unidade": unidade,
        "bitola_mm": bitola,
        "marca": marca,
        "descricao": "Vergalhão CA-50",
    }
    if codigo:
        d["codigo_produto"] = codigo
    return d


def _concilia(cliente: TestClient, pedido_id: str, csrf: str, nfe_id: uuid.UUID | None = None) -> dict:
    corpo = {"nfe_log_id": str(nfe_id)} if nfe_id else {}
    r = _post(cliente, f"/pedidos/{pedido_id}/conciliar", corpo, csrf)
    assert r.status_code == 201, r.text
    return r.json()["resultado"]


# ---------------------------------------------------------------------------
# O defeito original: duas linhas da mesma bitola
# ---------------------------------------------------------------------------


def test_duas_linhas_mesma_bitola_nao_presumem_verde(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    """Um item de 10 mm para duas linhas de 10 mm: o motor não escolhe, e avisa."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=500.0), _linha(quantidade=500.0)],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0)],
    )
    assert _post(
        cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf
    ).status_code == 200

    resultado = _concilia(cliente, pedido["id"], csrf)
    assert resultado["severidade_tecnica"] != "VERDE"
    assert resultado["requer_revisao_humana"] is True
    assert len(resultado["ambiguidades"]) == 2
    revisao = [linha for linha in resultado["linhas"] if linha["status_linha"] == "revisao"]
    assert len(revisao) == 2


def test_quantidade_faturada_nao_e_consumida_duas_vezes(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    """Depois de decidir por código, o total atribuído não pode passar do faturado."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=500.0, codigo="ACO-10"), _linha(quantidade=500.0, codigo="ACO-12")],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0, codigo="ACO-10")],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    resultado = _concilia(cliente, pedido["id"], csrf)
    assert resultado["ambiguidades"] == []
    por_linha = {l["linha"]: l for l in resultado["linhas"]}
    assert len(por_linha[1]["nfe"]["itens"]) == 1
    assert por_linha[2]["nfe"]["itens"] == []
    assert por_linha[1]["nfe"]["divergencia"] is None or abs(por_linha[1]["nfe"]["divergencia"]) < 0.02


# ---------------------------------------------------------------------------
# Correlação explícita
# ---------------------------------------------------------------------------


def test_correlacao_explicita_resolve_ambiguidade(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=500.0), _linha(quantidade=500.0)],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0)],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    assert _concilia(cliente, pedido["id"], csrf)["requer_revisao_humana"] is True

    item_1 = pedido["itens"][0]["id"]
    r = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {
            "pedido_item_id": item_1, "nfe_log_id": str(nfe), "nfe_item_numero": 1,
            "observacao": "separado pelo romaneio do fornecedor",
        },
        csrf,
    )
    assert r.status_code == 201, r.text
    correlacao_id = r.json()["id"]

    resultado = _concilia(cliente, pedido["id"], csrf)
    assert resultado["ambiguidades"] == []
    assert resultado["requer_revisao_humana"] is False
    por_linha = {l["linha"]: l for l in resultado["linhas"]}
    atribuido = por_linha[1]["nfe"]["itens"][0]
    assert atribuido["origem"] == "humana"
    assert atribuido["confianca"] == "manual"
    assert por_linha[2]["status_linha"] == "pendente"

    auditadas = cliente.get(f"/pedidos/{pedido['id']}/correlacoes").json()["itens"]
    assert len(auditadas) == 1
    assert auditadas[0]["id"] == correlacao_id
    assert auditadas[0]["criado_por"] == str(equipe["ids"]["eng"])


def test_correlacao_parcial_divide_item_entre_duas_linhas(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    """Uma nota cobre meias entregas das duas linhas: 300 + 200 = 500, sem sobreposição."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=300.0), _linha(quantidade=200.0)],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0)],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    for item, q in zip(pedido["itens"], [300.0, 200.0]):
        r = _post(
            cliente, f"/pedidos/{pedido['id']}/correlacoes",
            {"pedido_item_id": item["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1,
             "quantidade": q},
            csrf,
        )
        assert r.status_code == 201, r.text

    resultado = _concilia(cliente, pedido["id"], csrf)
    assert resultado["ambiguidades"] == []
    por_linha = {l["linha"]: l for l in resultado["linhas"]}
    assert por_linha[1]["nfe"]["itens"][0]["quantidade_correlacionada_base"] == 300.0
    assert por_linha[2]["nfe"]["itens"][0]["quantidade_correlacionada_base"] == 200.0
    assert resultado["severidade_tecnica"] == "VERDE"


def test_desfazer_correlacao_nao_apaga_o_registro(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=500.0), _linha(quantidade=500.0)],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0)],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    cid = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {"pedido_item_id": pedido["itens"][0]["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1},
        csrf,
    ).json()["id"]

    r = cliente.delete(f"/correlacoes/{cid}", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    with sql_owner.begin() as conn:
        permaneceu = conn.execute(
            text("SELECT removido_em, removido_por FROM correlacoes_humanas WHERE id = :i"),
            {"i": cid},
        ).mappings().one()
    assert permaneceu["removido_em"] is not None
    assert str(permaneceu["removido_por"]) == str(equipe["ids"]["eng"])

    assert _concilia(cliente, pedido["id"], csrf)["requer_revisao_humana"] is True


# ---------------------------------------------------------------------------
# Validações e autorização
# ---------------------------------------------------------------------------


def test_correlacao_exige_csrf(cliente: Any, equipe: dict[str, Any]) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])

    r = cliente.post(
        f"/pedidos/{pedido['id']}/correlacoes",
        json={"pedido_item_id": pedido["itens"][0]["id"], "nfe_log_id": str(uuid.uuid4()),
              "nfe_item_numero": 1},
    )
    assert r.status_code in (403, 422)


def test_correlacao_sem_vinculo_da_nfe_e_recusada(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=1000.0)],
    )

    r = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {"pedido_item_id": pedido["itens"][0]["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1},
        csrf,
    )
    assert r.status_code == 409
    assert "vinculada" in r.json()["detail"].lower()


def test_correlacao_de_item_de_outro_pedido_e_recusada(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido_a = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])
    pedido_b = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=1000.0)],
    )
    _post(cliente, f"/pedidos/{pedido_a['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    r = _post(
        cliente, f"/pedidos/{pedido_a['id']}/correlacoes",
        {"pedido_item_id": pedido_b["itens"][0]["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1},
        csrf,
    )
    assert r.status_code == 422


def test_fiscal_nao_pode_correlacionar(cliente: Any, equipe: dict[str, Any]) -> None:
    """Correlacionar é decidir a que linha o ferro pertence — papel de engenharia."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])

    cliente.cookies.clear()
    csrf_f = _login(cliente, equipe["emails"]["fiscal"])
    r = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {"pedido_item_id": pedido["itens"][0]["id"], "nfe_log_id": str(uuid.uuid4()),
         "nfe_item_numero": 1},
        csrf_f,
    )
    assert r.status_code == 403


def test_fiscal_concilia_e_lee_divergencias(cliente: Any, equipe: dict[str, Any]) -> None:
    """Quem opera o recebimento precisa enxergar a divergência no celular."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])

    cliente.cookies.clear()
    csrf_f = _login(cliente, equipe["emails"]["fiscal"])
    assert _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {}, csrf_f).status_code == 201
    assert cliente.get(f"/pedidos/{pedido['id']}/conciliacoes").status_code == 200
    assert cliente.get(f"/pedidos/{pedido['id']}/nfe").status_code == 200
    assert cliente.get(f"/obras/{equipe['obra_a']}/nfe").status_code == 200


# ---------------------------------------------------------------------------
# Isolamento entre construtoras
# ---------------------------------------------------------------------------


def test_pedido_de_outra_construtora_nao_expoe_correlacoes(
    cliente: Any, equipe: dict[str, Any]
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/pedidos/{pedido['id']}/correlacoes").status_code == 404
    assert cliente.get(f"/pedidos/{pedido['id']}/nfe").status_code == 404
    assert cliente.get(f"/pedidos/{pedido['id']}/conciliacoes").status_code == 404


def test_correlacao_de_outro_tenant_nao_e_alcancavel(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(cliente, equipe["obra_a"], csrf, fornecedor, [_linha()])
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=1000.0)],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    cid = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {"pedido_item_id": pedido["itens"][0]["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1},
        csrf,
    ).json()["id"]

    cliente.cookies.clear()
    csrf_b = _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.delete(f"/correlacoes/{cid}", headers={"X-CSRF-Token": csrf_b}).status_code == 404

    with sql_owner.begin() as conn:
        assert conn.execute(
            text("SELECT removido_em FROM correlacoes_humanas WHERE id = :i"), {"i": cid}
        ).mappings().one()["removido_em"] is None


# ---------------------------------------------------------------------------
# Múltiplas NF-e e entregas parciais
# ---------------------------------------------------------------------------


def test_entrega_parcial_em_duas_notas_soma_uma_ve(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=1000.0, codigo="ACO-10")],
    )
    n1 = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=600.0, codigo="ACO-10")],
    )
    n2 = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=400.0, codigo="ACO-10")],
    )
    for n in (n1, n2):
        assert _post(
            cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(n)}, csrf
        ).status_code == 200

    resultado = _concilia(cliente, pedido["id"], csrf)
    itens = resultado["linhas"][0]["nfe"]["itens"]
    assert len(itens) == 2
    assert {i["nfe_log_id"] for i in itens} == {str(n1), str(n2)}
    assert resultado["linhas"][0]["nfe"]["divergencia"] is None or abs(
        resultado["linhas"][0]["nfe"]["divergencia"]
    ) < 0.02
    assert resultado["progresso"]["linhas"][0]["faturado_base"] == 1000.0


def test_item_faturado_sem_pedido_e_vermelho(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=1000.0, codigo="ACO-10")],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[
            _item_nf(n_item=1, quantidade=1000.0, codigo="ACO-10"),
            _item_nf(n_item=2, quantidade=50.0, codigo="ACO-25"),
        ],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    resultado = _concilia(cliente, pedido["id"], csrf)
    assert resultado["severidade_tecnica"] == "VERMELHO"
    assert resultado["requer_revisao_humana"] is True
    assert [i["n_item"] for i in resultado["faturados_sem_pedido"]] == [2]


def test_linha_pedida_sem_fatura_fica_pendente(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=500.0, codigo="ACO-10"), _linha(quantidade=500.0, codigo="ACO-12")],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=500.0, codigo="ACO-10")],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    resultado = _concilia(cliente, pedido["id"], csrf)
    por_linha = {l["linha"]: l for l in resultado["linhas"]}
    assert por_linha[2]["status_linha"] == "pendente"
    assert resultado["progresso"]["linhas"][1]["faturado_base"] == 0.0
    assert resultado["progresso"]["linhas"][1]["status"] == "pendente"


def test_endpoint_de_nfe_mostra_o_codigo_do_item(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    """Sem ver o item da nota com seu código, ninguém consegue correlacionar."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _fornecedor(cliente, equipe["obra_a"], csrf, cnpj)
    pedido = _pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        [_linha(quantidade=1000.0, codigo="ACO-10")],
    )
    nfe = _nota(
        sql_owner, tenant=equipe["tenant_a"], obra=equipe["obra_a"], cnpj=cnpj,
        itens=[_item_nf(n_item=1, quantidade=1000.0, codigo="ACO-10")],
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    notas = cliente.get(f"/pedidos/{pedido['id']}/nfe").json()["itens"]
    assert notas[0]["id"] == str(nfe)
    assert notas[0]["itens"][0]["codigo_produto"] == "ACO-10"
    assert notas[0]["itens"][0]["n_item"] == 1

    da_obra = cliente.get(f"/obras/{equipe['obra_a']}/nfe").json()["itens"]
    assert str(nfe) in [n["id"] for n in da_obra]
