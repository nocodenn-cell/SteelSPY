"""Contrato de backend das telas do celular (Sprint 3 / P1).

O PWA não tem autoridade própria. Estas provas existem para que a frase
"escondi o botão" não seja confundida com "a pessoa não pode".

- `/auth/obras` só devolve obra em que há vínculo, com a permissão efetiva
  calculada no servidor (interseção dos dois papéis);
- `/obras/{obra}/recebimentos` e `.../evidencias` são leitura autorizada, e
  `storage_key` não aparece em lugar nenhum;
- obra de outra construtora some (404), não vira 403.
"""

from __future__ import annotations

import io
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.seguranca import hash_senha
from app.services import armazenamento as arm

SENHA = "SenhaForte#123"


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
    """eng e fiscal na obra A, auditor na obra A, admin só na obra B."""
    sufixo = uuid.uuid4().hex[:8]
    definicao = {
        "eng": ("engenheiro", "engenheiro", cenario["tenant_a"], cenario["obra_a"]),
        "fiscal": ("fiscal", "fiscal", cenario["tenant_a"], cenario["obra_a"]),
        "auditor": ("auditor", "auditor", cenario["tenant_a"], cenario["obra_a"]),
        "admin_b": ("admin_tenant", "engenheiro", cenario["tenant_b"], cenario["obra_b"]),
    }
    emails: dict[str, str] = {}
    ids: dict[str, uuid.UUID] = {}
    senha_hash = hash_senha(SENHA)

    with sql_owner.begin() as conn:
        for chave, (papel_global, papel_obra, tenant, obra) in definicao.items():
            uid = uuid.uuid4()
            email = f"pwa.{chave}.{sufixo}@teste.local"
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
                {"t": tenant, "o": obra, "u": uid, "p": papel_obra},
            )
    return {**cenario, "emails": emails, "ids": ids}


def _login(cliente: TestClient, email: str) -> str:
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _png(cor: int) -> bytes:
    """Cores diferentes porque o pipeline deduplica por sha256 — foto repetida é retry, não nova evidência."""
    buf = io.BytesIO()
    v = max(0, min(255, cor))
    Image.new("RGB", (48, 48), (v, v, v)).save(buf, format="PNG")
    return buf.getvalue()


def _recebimento(cliente: TestClient, obra: Any, csrf: str) -> str:
    r = cliente.post(
        f"/obras/{obra}/recebimentos", json={"tipo": "entrada"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _foto(cliente: TestClient, obra: Any, csrf: str, recebimento_id: str, *, cor: int = 7) -> str:
    r = cliente.post(
        f"/obras/{obra}/evidencias",
        files={"arquivo": ("carga.png", _png(cor), "image/png")},
        data={"tipo": "material", "origem": "camera", "recebimento_id": recebimento_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# /auth/obras
# ---------------------------------------------------------------------------


def test_quem_nao_tem_vinculo_nao_recebe_obra(cliente: Any, equipe: dict[str, Any]) -> None:
    """A lista de obras do celular vem do vínculo, não do tenant inteiro."""
    csrf = _login(cliente, equipe["emails"]["admin_b"])
    obras = cliente.get("/auth/obras").json()["itens"]
    assert [o["id"] for o in obras] == [str(equipe["obra_b"])]
    assert str(equipe["obra_a"]) not in [o["id"] for o in obras]


def test_acoes_devem_vir_da_intersecao_de_papeis(cliente: Any, equipe: dict[str, Any]) -> None:
    """Fiscal vê a obra com as ações do fiscal; o servidor é quem calcula."""
    _login(cliente, equipe["emails"]["fiscal"])
    obras = cliente.get("/auth/obras").json()["itens"]
    fiscal = [o for o in obras if o["id"] == str(equipe["obra_a"])][0]

    assert fiscal["papel_na_obra"] == "fiscal"
    assert "criar_recebimento" in fiscal["acoes"]
    assert "anexar_evidencia" in fiscal["acoes"]
    assert "gerenciar_pedido" not in fiscal["acoes"]
    assert "override" not in fiscal["acoes"]


def test_auditor_recebe_apenas_leitura(cliente: Any, equipe: dict[str, Any]) -> None:
    csrf = _login(cliente, equipe["emails"]["auditor"])
    obras = cliente.get("/auth/obras").json()["itens"]
    assert obras[0]["acoes"] == ["ver_evidencia", "ver_recebimento", "exportar_dossie"]


def test_lista_de_obras_exige_sessao(cliente: Any) -> None:
    assert cliente.get("/auth/obras").status_code == 401


# ---------------------------------------------------------------------------
# Recebimentos e evidências
# ---------------------------------------------------------------------------


def test_historico_de_recebimentos_com_contagem(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["fiscal"])
    rec = _recebimento(cliente, equipe["obra_a"], csrf)
    _foto(cliente, equipe["obra_a"], csrf, rec, cor=7)
    _foto(cliente, equipe["obra_a"], csrf, rec, cor=99)

    itens = cliente.get(f"/obras/{equipe['obra_a']}/recebimentos").json()["itens"]
    assert len(itens) == 1
    assert itens[0]["id"] == rec
    assert itens[0]["total_evidencias"] == 2
    assert itens[0]["criado_por_nome"] == "fiscal"
    assert itens[0]["status"]


def test_evidencias_por_recebimento_nao_expose_chave_de_storage(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["fiscal"])
    rec = _recebimento(cliente, equipe["obra_a"], csrf)
    evid = _foto(cliente, equipe["obra_a"], csrf, rec)

    corpo = cliente.get(
        f"/obras/{equipe['obra_a']}/evidencias", params={"recebimento_id": rec}
    ).json()
    assert [e["id"] for e in corpo["itens"]] == [evid]
    bruto = corpo["itens"][0]
    assert "storage_key" not in bruto
    assert bruto["sha256"]
    assert bruto["conteudo_url"] == f"/evidencias/{evid}/conteudo"


def test_fiscal_ve_historico_mas_nao_de_outra_obra(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    _login(cliente, equipe["emails"]["fiscal"])
    # Fiscal só tem vínculo na obra A; a obra B é de outro tenant.
    assert cliente.get(f"/obras/{equipe['obra_b']}/recebimentos").status_code == 404


def test_admin_de_outra_construtora_nao_ve_recebimentos(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    _recebimento(cliente, equipe["obra_a"], csrf)

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/obras/{equipe['obra_a']}/recebimentos").status_code == 404
    assert cliente.get(f"/obras/{equipe['obra_a']}/evidencias").status_code == 404


def test_auditor_lee_mas_nao_abre_recebimento(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """Leitura de histórico não é poder de registrar entrada — a matriz separa."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    rec = _recebimento(cliente, equipe["obra_a"], csrf)
    _foto(cliente, equipe["obra_a"], csrf, rec)

    cliente.cookies.clear()
    csrf_a = _login(cliente, equipe["emails"]["auditor"])
    assert cliente.get(f"/obras/{equipe['obra_a']}/recebimentos").status_code == 200
    assert cliente.get(f"/obras/{equipe['obra_a']}/evidencias").status_code == 200
    r = cliente.post(
        f"/obras/{equipe['obra_a']}/recebimentos", json={"tipo": "entrada"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert r.status_code == 403


def test_leitura_de_recebimentos_exige_sessao(cliente: Any, equipe: dict[str, Any]) -> None:
    assert cliente.get(f"/obras/{equipe['obra_a']}/recebimentos").status_code == 401
    assert cliente.get(f"/obras/{equipe['obra_a']}/evidencias").status_code == 401
