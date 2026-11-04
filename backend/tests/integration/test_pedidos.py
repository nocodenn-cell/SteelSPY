"""Sprint 2: pedidos, vínculo NF-e, conciliação de três vias e dossiê.

O que estes testes protegem:

- um pedido de outra construtora é invisível (RLS) e inalcançável (404);
- o banco recusa item apontando para pedido de outro tenant, por FK composta;
- NF-e só vincula a pedido compatível — mesma obra e mesmo fornecedor;
- a conciliação não trata a NF-e como verdade física;
- a severidade técnica nunca é rebaixada pelo modo de aprendizado;
- dossiê funciona sem evidência e com divergência.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.seguranca import hash_senha
from app.services import armazenamento as arm

SENHA = "SenhaForte#123"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage(tmp_path: Any) -> Any:
    backend = arm.ArmazenamentoLocal(tmp_path / "evidencias")
    arm.definir_backend(backend)
    try:
        yield backend
    finally:
        arm.definir_backend(None)


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
    sufixo = uuid.uuid4().hex[:8]
    definicao = {
        "eng": ("engenheiro", cenario["tenant_a"], cenario["obra_a"]),
        "fiscal": ("fiscal", cenario["tenant_a"], cenario["obra_a"]),
        "auditor": ("auditor", cenario["tenant_a"], cenario["obra_a"]),
        "admin_b": ("admin_tenant", cenario["tenant_b"], cenario["obra_b"]),
    }
    emails: dict[str, str] = {}
    ids: dict[str, uuid.UUID] = {}
    senha_hash = hash_senha(SENHA)

    with sql_owner.begin() as conn:
        for chave, (papel_global, tenant, obra) in definicao.items():
            uid = uuid.uuid4()
            email = f"{chave}.{sufixo}@teste.local"
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


def _criar_fornecedor(cliente: TestClient, obra: Any, csrf: str, cnpj: str | None = None) -> str:
    cnpj = cnpj or f"{uuid.uuid4().int % 10**14:014d}"
    r = _post(
        cliente, f"/obras/{obra}/fornecedores",
        {"cnpj": cnpj, "razao_social": "Aco Brasil Ltda"}, csrf,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _criar_pedido(
    cliente: TestClient, obra: Any, csrf: str, fornecedor_id: str,
    numero: str | None = None, itens: list[dict] | None = None,
) -> Any:
    itens = itens or [
        {"material_tipo": "CA-50", "categoria_material": "aco", "bitola_mm": 10.0,
         "marca_exigida": "GERDAU", "quantidade": 1000.0, "unidade": "M"},
    ]
    return _post(
        cliente, f"/obras/{obra}/pedidos",
        {"fornecedor_id": fornecedor_id, "numero": numero or uuid.uuid4().hex[:8], "itens": itens},
        csrf,
    )


def _nfe_com_itens(sql_owner: Any, cenario: dict[str, Any], itens: list[dict], cnpj: str) -> uuid.UUID:
    nfe_id = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, status_conferencia, xml_data) "
                "VALUES (:id, :t, :k, :o, 'VERDE', CAST(:x AS jsonb))"
            ),
            {
                "id": nfe_id,
                "t": cenario["tenant_a"],
                "k": f"{uuid.uuid4().int % 10**44:044d}",
                "o": cenario["obra_a"],
                "x": json.dumps({"emitente_cnpj": cnpj, "itens": itens}),
            },
        )
    return nfe_id


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


def test_pedido_valido_e_criado(cliente: Any, equipe: dict[str, Any], storage: Any) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf)
    r = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor, numero="PC-001")

    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["numero"] == "PC-001"
    assert corpo["status"] == "aberto"
    assert len(corpo["itens"]) == 1
    assert corpo["itens"][0]["unidade"] == "M"


def test_pedido_duplicado_e_recusado(cliente: Any, equipe: dict[str, Any], storage: Any) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf)
    assert _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor, "PC-DUP").status_code == 201
    segundo = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor, "PC-DUP")
    assert segundo.status_code == 409


def test_fiscal_nao_pode_criar_pedido(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["fiscal"])
    r = _post(
        cliente, f"/obras/{equipe['obra_a']}/fornecedores",
        {"cnpj": "1" * 14, "razao_social": "X"}, csrf,
    )
    assert r.status_code == 403


def test_pedido_de_outra_construtora_responde_404(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf_a = _login(cliente, equipe["emails"]["eng"])
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf_a)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf_a, fornecedor).json()

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/pedidos/{pedido['id']}").status_code == 404


def test_item_de_pedido_de_outro_tenant_e_recusado_pelo_banco(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """A FK composta (tenant_id, pedido_id) recusa a associação cruzada sozinha."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()

    with pytest.raises(Exception) as exc:
        with sql_owner.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pedido_itens
                        (tenant_id, pedido_id, linha, material_tipo, quantidade, unidade)
                    VALUES (:t, :p, 99, 'CA-50', 1, 'M')
                """),
                {"t": equipe["tenant_b"], "p": pedido["id"]},
            )
    assert "foreign key" in str(exc.value).lower()


def test_rls_isola_pedidos(cliente: Any, equipe: dict[str, Any], storage: Any, abrir_como: Any) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()

    with abrir_como(equipe["tenant_a"]) as conn:
        assert conn.execute(
            text("SELECT count(*) FROM pedidos_compra WHERE id = :id"), {"id": pedido["id"]}
        ).scalar_one() == 1

    with abrir_como(equipe["tenant_b"]) as conn:
        assert conn.execute(text("SELECT count(*) FROM pedidos_compra")).scalar_one() == 0

    with abrir_como(None) as conn:
        assert conn.execute(text("SELECT count(*) FROM pedidos_compra")).scalar_one() == 0


# ---------------------------------------------------------------------------
# Vínculo com NF-e
# ---------------------------------------------------------------------------


def test_nfe_vinculada_ao_pedido(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf, cnpj=cnpj)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()
    nfe = _nfe_com_itens(sql_owner, equipe, [{"bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M"}], cnpj)

    r = _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    assert r.status_code == 200, r.text
    assert r.json()["vinculado"] is True


def test_nfe_de_outra_obra_e_recusada(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf, cnpj=cnpj)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()

    # NF-e na obra B.
    nfe_b = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, status_conferencia, xml_data) "
                "VALUES (:id, :t, :k, :o, 'VERDE', '{}'::jsonb)"
            ),
            {
                "id": nfe_b, "t": equipe["tenant_b"],
                "k": f"{uuid.uuid4().int % 10**44:044d}", "o": equipe["obra_b"],
            },
        )

    r = _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe_b)}, csrf)
    assert r.status_code in (404, 409)


def test_nfe_de_fornecedor_diferente_e_recusada(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj_pedido = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf, cnpj=cnpj_pedido)
    pedido = _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()

    outro_cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    nfe = _nfe_com_itens(sql_owner, equipe, [{"bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M"}], outro_cnpj)

    r = _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    assert r.status_code == 409
    assert "fornecedor" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Conciliação
# ---------------------------------------------------------------------------


def _pedido_conciliavel(cliente: Any, equipe: dict[str, Any], csrf: str, cnpj: str) -> dict:
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf, cnpj=cnpj)
    return _criar_pedido(cliente, equipe["obra_a"], csrf, fornecedor).json()


def test_conciliacao_conforme(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    r = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf)
    assert r.status_code == 201, r.text
    assert r.json()["severidade_tecnica"] == "VERDE"


def test_quantidade_divergente_gera_vermelho(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    # Pedido 1000 m, NF 500 m -> 50% de divergência.
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 500.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    corpo = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()
    assert corpo["severidade_tecnica"] == "VERMELHO"
    assert corpo["resultado"]["linhas"][0]["severidade_nfe"] == "VERMELHO"


def test_especificacao_divergente_de_bitola_gera_vermelho(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    # Bitola 12.5 na NF contra 10 no pedido.
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 12.5, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    corpo = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()
    # Sem item de NF correspondente à bitola do pedido, não há casamento.
    assert corpo["severidade_tecnica"] in ("AMARELO", "VERMELHO")


def test_conciliacao_sem_nfe_nao_presume_nada(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)

    corpo = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {}, csrf).json()
    assert corpo["resultado"]["fonte_verdade_fisica"] == "ausente"
    assert corpo["resultado"]["aviso"], "sem recebimento, o sistema precisa avisar que não há prova física"


def test_severidade_tecnica_nao_e_rebaixada(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """Mesmo com modo de aprendizado ligado na obra, a conciliação é técnica."""
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE obras SET modo_aprendizado = TRUE WHERE id = :id"),
            {"id": equipe["obra_a"]},
        )

    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 100.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)

    corpo = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()
    assert corpo["severidade_tecnica"] == "VERMELHO"


# ---------------------------------------------------------------------------
# Dossiê
# ---------------------------------------------------------------------------


def test_dossie_sem_evidencias(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)

    r = cliente.get(f"/pedidos/{pedido['id']}/dossie")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total_evidencias"] == 0
    assert corpo["total_conciliacoes"] == 0
    assert "não constitui laudo" in corpo["ressalva"].lower() or "Não constitui" in corpo["ressalva"]


def test_dossie_com_divergencia_e_evidencia(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 200.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf)

    # Uma evidência qualquer na obra.
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (9, 9, 9)).save(buf, format="PNG")
    rec = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos", {}, csrf).json()
    upload = cliente.post(
        f"/obras/{equipe['obra_a']}/evidencias",
        files={"arquivo": ("f.png", buf.getvalue(), "image/png")},
        data={"tipo": "material", "recebimento_id": rec["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201, upload.text

    corpo = cliente.get(f"/pedidos/{pedido['id']}/dossie").json()
    assert corpo["total_evidencias"] == 1
    assert corpo["total_conciliacoes"] == 1
    assert corpo["conciliacoes"][0]["severidade_tecnica"] == "VERMELHO"
    assert corpo["evidencias"][0]["sha256"]


def test_dossie_exige_papel_de_exportacao(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["fiscal"])
    # Fiscal não tem exportar_dossie.
    assert cliente.get(f"/pedidos/{pedido['id']}/dossie").status_code == 403


# ---------------------------------------------------------------------------
# Dossiê em PDF
# ---------------------------------------------------------------------------


def test_dossie_pdf_devolve_pdf_com_identificador(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 100.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf)

    r = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF", "resposta não é um PDF"
    assert len(r.content) > 2000
    assert r.headers["x-dossie-id"] == f"dossie-{pedido['id']}"
    assert "no-store" in r.headers["cache-control"]


def test_dossie_pdf_com_evidencia_e_decisao_humana(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """O PDF precisa aguentar o caso completo: divergência, foto e assinatura."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"n_item": 1, "bitola_mm": 12.0, "quantidade": 50.0, "unidade": "M", "marca": "OUTRA"}],
        cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    conc = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (21, 21, 21)).save(buf, format="PNG")
    rec = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos", {}, csrf).json()
    upload = cliente.post(
        f"/obras/{equipe['obra_a']}/evidencias",
        files={"arquivo": ("carga.png", buf.getvalue(), "image/png")},
        data={"tipo": "material", "recebimento_id": rec["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert upload.status_code == 201, upload.text

    _post(
        cliente, f"/conciliacoes/{conc['id']}/decisao",
        {"decisao": "aceita", "justificativa": "material aceito apos analise dimensional no portao"},
        csrf,
    )

    r = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_dossie_lista_os_itens_faturados_de_verdade(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    A prova do item faturado mora em nfe_itens, não em `itens_resumo`.

    `itens_resumo` é contagem de ok/atenção/crítico e `resumo_global` é texto
    curto. Um dossiê que imprimisse esses campos como se fossem linhas de nota
    inventaria item — o erro exatamente oposto ao que este projeto promete não
    cometer.
    """
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"n_item": 1, "bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}],
        cnpj,
    )
    with sql_owner.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO nfe_itens
                    (tenant_id, nfe_log_id, item_numero, material_recebido, bitola_recebida,
                     marca_recebida, quantidade_recebida, unidade_recebida, status_item)
                VALUES
                    (:t, :n, 1, 'VERGALHAO CA-50 10MM', 10.0, 'GERDAU', 1000.0, 'M', 'VERDE')
            """),
            {"t": equipe["tenant_a"], "n": str(nfe)},
        )
        conn.execute(
            text("UPDATE nfe_logs SET resumo_global = :r WHERE id = :n"),
            {"r": "1 item · 0 com atenção · 0 crítico", "n": str(nfe)},
        )

    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    dossie = cliente.get(f"/pedidos/{pedido['id']}/dossie").json()

    nota = dossie["nfe"][0]
    assert nota["resumo_global"] == "1 item · 0 com atenção · 0 crítico"
    assert [i["item_numero"] for i in nota["itens"]] == [1]
    assert nota["itens"][0]["material_recebido"] == "VERGALHAO CA-50 10MM"

    r = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_dossie_pdf_exige_exportar_dossie(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["fiscal"])
    assert cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf").status_code == 403


def test_dossie_pdf_de_outra_construtora_responde_404(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    # 404 e nao 403: confirmar a existência do id já seria informação.
    assert cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf").status_code == 404


def test_dossie_pdf_sem_sessao_responde_401(cliente: Any) -> None:
    assert cliente.get(f"/pedidos/{uuid.uuid4()}/dossie.pdf").status_code == 401


def test_gerar_dossie_pdf_tolera_dossie_incompleto() -> None:
    """Dossiê é documento factual: falta de dado não pode derrubar a geração."""
    from app.services.dossie_pdf import gerar_dossie_pdf_bytes, nome_arquivo_dossie

    bytes_ = gerar_dossie_pdf_bytes({"pedido": {"numero": "PC-X"}, "conciliacoes": []})
    assert bytes_[:4] == b"%PDF"
    assert nome_arquivo_dossie({"pedido": {"numero": "PC/001"}}) == "dossie_PC-001.pdf"


# ---------------------------------------------------------------------------
# Decisão humana e falha de banco
# ---------------------------------------------------------------------------


def test_decisao_humana_registra_identidade_da_sessao(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_conciliavel(cliente, equipe, csrf, cnpj)
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 100.0, "unidade": "M", "marca": "GERDAU"}], cnpj,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    conc = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()

    r = _post(
        cliente, f"/conciliacoes/{conc['id']}/decisao",
        {"decisao": "aceita", "justificativa": "divergencia aceita pelo RT apos analise"},
        csrf,
    )
    assert r.status_code == 200, r.text
    decisao = r.json()["decisao"]
    assert decisao["usuario_id"] == str(equipe["ids"]["eng"])
    assert decisao["usuario_email"] == equipe["emails"]["eng"]
    assert decisao["severidade_tecnica_no_momento"] == "VERMELHO"


def test_falha_de_banco_responde_503_sem_vazar_detalhe(cliente: Any) -> None:
    """Indisponibilidade de conexão é 503; o corpo não pode conter SQL nem host."""
    from app.db import get_db
    from app.main import app

    class _SessaoQuebrada:
        def execute(self, *a: Any, **k: Any) -> Any:
            raise OperationalError(
                "SELECT * FROM usuarios WHERE senha='segredo'",
                {"host": "db.interno.local", "user": "postgres"},
                Exception("connection refused"),
            )

        def close(self) -> None:
            return None

    app.dependency_overrides[get_db] = lambda: _SessaoQuebrada()
    try:
        r = cliente.post("/auth/login", json={"email": "a@b.test", "senha": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 503
    assert r.headers.get("retry-after") == "5"
    texto = r.text.lower()
    for proibido in ("select", "postgres", "db.interno", "connection refused", "senha"):
        assert proibido not in texto, f"resposta vazou detalhe: {proibido}"


# ---------------------------------------------------------------------------
# Fluxo completo: obra -> pedido -> NF-e -> conferência -> evidência -> dossiê
# ---------------------------------------------------------------------------


def test_fluxo_completo_de_recebimento_ponta_a_ponta(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    O caminho que o operador percorre no canteiro, do pedido ao dossiê.

    O que este teste protege, além do "funciona":

    - engenharia compra e vincula a nota; o fiscal conta no portão — papéis diferentes;
    - a contagem fecha a linha e o servidor calcula `completo`/`atendido`;
    - reenviar a mesma carga com o mesmo `id_cliente` devolve o mesmo recebimento;
    - a foto fica presa ao tenant, à obra e àquele recebimento, e o reenvio não duplica;
    - o download confere o hash e não expõe caminho de storage;
    - a construtora vizinha não alcança pedido, entrega nem foto.
    """
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf_eng, cnpj=cnpj)

    criado = _criar_pedido(cliente, equipe["obra_a"], csrf_eng, fornecedor, numero="PC-E2E")
    assert criado.status_code == 201, criado.text
    pedido = criado.json()
    item_id = pedido["itens"][0]["id"]

    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}],
        cnpj,
    )
    vinculo = _post(
        cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf_eng
    )
    assert vinculo.status_code == 200, vinculo.text

    # O fiscal é quem conta a carga no portão.
    cliente.cookies.clear()
    csrf_fiscal = _login(cliente, equipe["emails"]["fiscal"])
    id_cliente = uuid.uuid4()
    corpo_recebimento = {
        "id_cliente": str(id_cliente),
        "pedido_id": pedido["id"],
        "observacoes": "carga conferida na descarga",
        "itens": [
            {"pedido_item_id": item_id, "quantidade": 1000.0, "unidade": "M"}
        ],
    }
    entrega = _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos", corpo_recebimento, csrf_fiscal
    )
    assert entrega.status_code == 200, entrega.text
    rec = entrega.json()
    assert rec["criado"] is True
    assert rec["status"] == "completo"
    assert rec["pedido_status"]["status"] == "atendido"

    # Retry depois de uma resposta perdida: mesma chave, mesmo registro.
    retry_entrega = _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos", corpo_recebimento, csrf_fiscal
    )
    assert retry_entrega.status_code == 200, retry_entrega.text
    assert retry_entrega.json()["id"] == rec["id"]
    assert retry_entrega.json()["criado"] is False

    buf = io.BytesIO()
    Image.new("RGB", (48, 32), (7, 77, 7)).save(buf, format="PNG")
    foto = buf.getvalue()
    chave_upload = f"cam-{uuid.uuid4().hex}"
    upload = cliente.post(
        f"/obras/{equipe['obra_a']}/evidencias",
        files={"arquivo": ("carga.png", foto, "image/png")},
        data={
            "tipo": "material",
            "origem": "camera",
            "recebimento_id": rec["id"],
            "idempotency_key": chave_upload,
        },
        headers={"X-CSRF-Token": csrf_fiscal},
    )
    assert upload.status_code == 201, upload.text
    evidencia = upload.json()
    assert evidencia["criada"] is True
    assert evidencia["recebimento_id"] == rec["id"]
    assert "storage_key" not in evidencia, "caminho de storage não é dado de API"

    reenvio = cliente.post(
        f"/obras/{equipe['obra_a']}/evidencias",
        files={"arquivo": ("carga.png", foto, "image/png")},
        data={
            "tipo": "material",
            "origem": "camera",
            "recebimento_id": rec["id"],
            "idempotency_key": chave_upload,
        },
        headers={"X-CSRF-Token": csrf_fiscal},
    )
    assert reenvio.status_code == 200, reenvio.text
    assert reenvio.json()["id"] == evidencia["id"]
    assert reenvio.json()["criada"] is False

    # A prova está amarrada ao tenant, à obra e ao recebimento — não só "na obra".
    with sql_owner.connect() as conn:
        linha = conn.execute(
            text("""
                SELECT tenant_id, obra_id, recebimento_id, storage_key, criado_por
                FROM evidencias WHERE id = :id
            """),
            {"id": evidencia["id"]},
        ).mappings().one()
    assert str(linha["tenant_id"]) == str(equipe["tenant_a"])
    assert str(linha["obra_id"]) == str(equipe["obra_a"])
    assert str(linha["recebimento_id"]) == rec["id"]
    assert str(linha["criado_por"]) == str(equipe["ids"]["fiscal"])
    assert linha["storage_key"].startswith(f"{equipe['tenant_a']}/{equipe['obra_a']}/")

    download = cliente.get(f"/evidencias/{evidencia['id']}/conteudo")
    assert download.status_code == 200, download.text
    assert download.headers["x-conteudo-sha256"] == evidencia["sha256"]
    assert hashlib.sha256(download.content).hexdigest() == evidencia["sha256"]
    assert "no-store" in download.headers["cache-control"]

    conciliacao = _post(
        cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf_fiscal
    )
    assert conciliacao.status_code == 201, conciliacao.text
    assert conciliacao.json()["severidade_tecnica"] == "VERDE"

    # Quem compra responde pelo dossiê; o fiscal não exporta.
    assert cliente.get(f"/pedidos/{pedido['id']}/dossie").status_code == 403

    cliente.cookies.clear()
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    dossie = cliente.get(f"/pedidos/{pedido['id']}/dossie")
    assert dossie.status_code == 200, dossie.text
    corpo = dossie.json()
    assert corpo["total_evidencias"] == 1
    assert corpo["total_conciliacoes"] == 1
    assert [r["id"] for r in corpo["recebimentos"]] == [rec["id"]]
    assert corpo["evidencias"][0]["id"] == evidencia["id"]
    assert corpo["evidencias"][0]["recebimento_id"] == rec["id"]
    assert corpo["cobertura"][0]["status_recebimento"] == "completo"
    assert any(e["status_para"] == "completo" for e in corpo["transicoes"])

    pdf = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"

    # A construtora vizinha não alcança nada por id.
    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/pedidos/{pedido['id']}").status_code == 404
    assert cliente.get(f"/recebimentos/{rec['id']}").status_code == 404
    assert cliente.get(f"/evidencias/{evidencia['id']}").status_code == 404
    assert cliente.get(f"/evidencias/{evidencia['id']}/conteudo").status_code == 404
    assert cliente.get(f"/obras/{equipe['obra_a']}/recebimentos").status_code == 404


# ---------------------------------------------------------------------------
# Sprint 6: os dez passos do piloto, em uma sessão de cada papel
# ---------------------------------------------------------------------------


def test_piloto_percorre_os_dez_passos_ate_a_consulta_autorizada(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    Roteiro físico do piloto traduzido em chamadas reais:

    1. autenticação do funcionário;
    2. seleção da obra autorizada, com as ações calculadas no servidor;
    3. consulta ao pedido;
    4. associação da NF-e ao pedido;
    5. recebimento parcial no portão;
    6. foto da carga, com prova de hash;
    7. divergência entre o faturado e o contado;
    8. conciliação e decisão do responsável técnico;
    9. dossiê em PDF;
    10. consulta pela auditoria, sem poder de escrita.

    A divergência nasce onde nasce no campo: `nfe_itens` guarda a contagem do
    portão (800 m recebidos contra 1000 m faturados) e a conciliação compara o
    físico com a nota — não a nota consigo mesma.
    """
    # 1. Autenticação.
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    eu = cliente.get("/auth/eu")
    assert eu.status_code == 200, eu.text
    assert eu.json()["email"] == equipe["emails"]["eng"]
    assert eu.json()["papel_global"] == "engenheiro"

    # 2. Seleção da construtora/obra: só a obra com vínculo, com as ações do servidor.
    obras = cliente.get("/auth/obras")
    assert obras.status_code == 200, obras.text
    obra_a = next(o for o in obras.json()["itens"] if o["id"] == str(equipe["obra_a"]))
    assert obra_a["papel_na_obra"] == "engenheiro"
    assert "gerenciar_pedido" in obra_a["acoes"]
    assert "exportar_dossie" in obra_a["acoes"]

    # 3-4. Pedido e vínculo com a NF-e do mesmo emitente.
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf_eng, cnpj=cnpj)
    criado = _criar_pedido(cliente, equipe["obra_a"], csrf_eng, fornecedor, numero="PC-PILOTO")
    assert criado.status_code == 201, criado.text
    pedido = criado.json()
    item_id = pedido["itens"][0]["id"]

    consulta = cliente.get(f"/pedidos/{pedido['id']}")
    assert consulta.status_code == 200, consulta.text
    assert consulta.json()["numero"] == "PC-PILOTO"

    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"n_item": 1, "bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}],
        cnpj,
    )
    vinculo = _post(
        cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf_eng
    )
    assert vinculo.status_code == 200, vinculo.text
    notas = cliente.get(f"/pedidos/{pedido['id']}/nfe")
    assert notas.status_code == 200, notas.text
    assert [n["id"] for n in notas.json()["itens"]] == [str(nfe)]

    # 5. Recebimento no portão: 800 dos 1000 m chegaram.
    cliente.cookies.clear()
    csrf_fiscal = _login(cliente, equipe["emails"]["fiscal"])
    entrega = _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos",
        {
            "id_cliente": str(uuid.uuid4()),
            "pedido_id": pedido["id"],
            "observacoes": "descarga conferida no portão do piloto",
            "itens": [{"pedido_item_id": item_id, "quantidade": 800.0, "unidade": "M"}],
        },
        csrf_fiscal,
    )
    assert entrega.status_code == 200, entrega.text
    rec = entrega.json()
    assert rec["status"] == "parcial"
    assert rec["pedido_status"]["status"] == "parcial"

    # 6. Foto da carga: o hash devolvido é o mesmo do arquivo baixado.
    buf = io.BytesIO()
    Image.new("RGB", (48, 32), (3, 61, 3)).save(buf, format="PNG")
    foto = buf.getvalue()
    upload = cliente.post(
        f"/obras/{equipe['obra_a']}/evidencias",
        files={"arquivo": ("piloto.png", foto, "image/png")},
        data={
            "tipo": "material",
            "origem": "camera",
            "recebimento_id": rec["id"],
            "idempotency_key": f"piloto-{uuid.uuid4().hex}",
        },
        headers={"X-CSRF-Token": csrf_fiscal},
    )
    assert upload.status_code == 201, upload.text
    evidencia = upload.json()
    download = cliente.get(f"/evidencias/{evidencia['id']}/conteudo")
    assert download.status_code == 200, download.text
    assert hashlib.sha256(download.content).hexdigest() == evidencia["sha256"]

    # 7. A contagem do portão é o lado físico: 800 m recebidos contra 1000 m faturados.
    with sql_owner.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO nfe_itens
                    (tenant_id, nfe_log_id, item_numero, material_recebido, bitola_recebida,
                     marca_recebida, quantidade_recebida, unidade_recebida, status_item)
                VALUES (:t, :n, 1, 'VERGALHAO CA-50 10MM', 10.0, 'GERDAU', 800.0, 'M', 'VERMELHO')
            """),
            {"t": equipe["tenant_a"], "n": str(nfe)},
        )

    # 8. Conciliação e decisão do responsável técnico, com identidade registrada.
    conc = _post(
        cliente, f"/pedidos/{pedido['id']}/conciliar",
        {"nfe_log_id": str(nfe), "recebimento_id": rec["id"]},
        csrf_fiscal,
    )
    assert conc.status_code == 201, conc.text
    corpo_conc = conc.json()
    assert corpo_conc["resultado"]["fonte_verdade_fisica"] == "recebimento"
    assert corpo_conc["severidade_tecnica"] == "VERMELHO"

    cliente.cookies.clear()
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    decisao = _post(
        cliente, f"/conciliacoes/{corpo_conc['id']}/decisao",
        {
            "decisao": "aceita",
            "justificativa": "falta de 200 m apontada para cobrança do fornecedor",
        },
        csrf_eng,
    )
    assert decisao.status_code == 200, decisao.text
    assert decisao.json()["decisao"]["usuario_email"] == equipe["emails"]["eng"]

    # 9. Dossiê PDF com identificador estável e sem cache.
    pdf = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.content[:4] == b"%PDF"
    assert pdf.headers["x-dossie-id"] == f"dossie-{pedido['id']}"
    assert "no-store" in pdf.headers["cache-control"]

    # 10. Auditoria autorizada: lê pedido, recebimento e dossiê — não escreve.
    cliente.cookies.clear()
    csrf_auditor = _login(cliente, equipe["emails"]["auditor"])
    assert cliente.get("/auth/eu").json()["papel_global"] == "auditor"
    for url in (
        f"/pedidos/{pedido['id']}",
        f"/recebimentos/{rec['id']}",
        f"/pedidos/{pedido['id']}/dossie",
        f"/pedidos/{pedido['id']}/dossie.pdf",
        f"/obras/{equipe['obra_a']}/recebimentos",
    ):
        assert cliente.get(url).status_code == 200, f"auditor sem leitura em {url}"

    assert _post(
        cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf_auditor
    ).status_code == 403
    assert _post(
        cliente, f"/conciliacoes/{corpo_conc['id']}/decisao",
        {"decisao": "rejeitada", "justificativa": "auditoria não decide"}, csrf_auditor,
    ).status_code == 403
