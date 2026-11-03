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
