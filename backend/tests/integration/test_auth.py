"""Autenticação, autorização e contexto de tenant — de ponta a ponta.

Estes testes sobem a aplicação de verdade sobre o PostgreSQL de teste, com a
role `stellspy_app` (sem BYPASSRLS). O que eles provam:

- identidade sai da sessão, nunca do corpo da requisição;
- permissão sai do banco, nunca do que o cliente afirma;
- sessão revogada e sessão expirada param de funcionar imediatamente;
- CSRF é exigido quando a credencial é cookie;
- o fluxo legado por chave de obra continua funcionando, com escopo restrito.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.seguranca import criar_token_sessao, hash_senha, ler_token_sessao
from app.utils.chave_nfe import _digito_verificador_chave

SENHA = "SenhaForte#123"


def chave_nfe_valida(base43: str = "1" * 43) -> str:
    """44 dígitos com DV módulo 11 válido — passa na validação antes da autenticação."""
    base = base43[:43]
    return base + str(_digito_verificador_chave(base))


# ---------------------------------------------------------------------------
# Infra de teste
# ---------------------------------------------------------------------------


@pytest.fixture()
def cliente(sessao_app_factory: Any) -> Any:
    """TestClient usando a role de aplicação e o banco de teste."""
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
    """
    Três usuários com papéis diferentes:

    - fiscal_a  : papel global fiscal, vínculo fiscal na obra A
    - eng_a     : papel global engenheiro, vínculo engenheiro na obra A
    - admin_b   : admin da construtora B, vínculo engenheiro na obra B
    """
    senha_hash = hash_senha(SENHA)
    # E-mail é único por (tenant, email), mas `auth_login_lookup` busca por
    # e-mail em todas as construtoras: sem sufixo, o segundo teste encontraria
    # usuários de execuções anteriores e o login viraria ambíguo.
    sufixo = uuid.uuid4().hex[:8]
    emails = {
        "fiscal_a": f"fiscal.a.{sufixo}@alfa.test",
        "eng_a": f"eng.a.{sufixo}@alfa.test",
        "admin_b": f"admin.b.{sufixo}@beta.test",
    }
    ids = {k: uuid.uuid4() for k in emails}

    with sql_owner.begin() as conn:
        for nome, email in emails.items():
            tenant = cenario["tenant_b"] if nome == "admin_b" else cenario["tenant_a"]
            papel = "admin_tenant" if nome == "admin_b" else ("engenheiro" if nome == "eng_a" else "fiscal")
            conn.execute(
                text(
                    "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                    "VALUES (:id, :t, :nome, :email, :hash, :papel)"
                ),
                {
                    "id": ids[nome], "t": tenant, "nome": nome,
                    "email": email, "hash": senha_hash, "papel": papel,
                },
            )
            obra = cenario["obra_b"] if nome == "admin_b" else cenario["obra_a"]
            papel_obra = "engenheiro" if nome == "admin_b" else papel
            conn.execute(
                text(
                    "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) "
                    "VALUES (:t, :o, :u, :p)"
                ),
                {"t": tenant, "o": obra, "u": ids[nome], "p": papel_obra},
            )

    return {"ids": ids, "emails": emails, **cenario}


def _login(cliente: TestClient, email: str, senha: str = SENHA, tenant: str | None = None) -> Any:
    corpo: dict[str, Any] = {"email": email, "senha": senha}
    if tenant:
        corpo["tenant"] = tenant
    return cliente.post("/auth/login", json=corpo)


# ---------------------------------------------------------------------------
# 1–3. Login
# ---------------------------------------------------------------------------


def test_login_valido_abre_sessao(cliente: Any, equipe: dict[str, Any]) -> None:
    r = _login(cliente, equipe["emails"]["fiscal_a"])
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ok"] is True
    assert corpo["usuario"]["papel_global"] == "fiscal"
    assert str(corpo["usuario"]["id"]) == str(equipe["ids"]["fiscal_a"])

    # Cookie de sessão é HttpOnly; o de CSRF não é (precisa ser lido pelo JS).
    cookies = r.headers.get_list("set-cookie")
    sessao_cookie = next(c for c in cookies if c.startswith("stellspy_sessao="))
    csrf_cookie = next(c for c in cookies if c.startswith("stellspy_csrf="))
    assert "HttpOnly" in sessao_cookie
    assert "HttpOnly" not in csrf_cookie

    identidade = cliente.get("/auth/eu")
    assert identidade.status_code == 200
    assert identidade.json()["tenant_id"] == str(equipe["tenant_a"])


def test_login_com_senha_errada_falha(cliente: Any, equipe: dict[str, Any]) -> None:
    r = _login(cliente, equipe["emails"]["fiscal_a"], senha="senha-errada")
    assert r.status_code == 401
    assert "Credenciais inválidas" in r.json()["detail"]
    assert cliente.get("/auth/eu").status_code == 401


def test_login_com_email_inexistente_da_a_mesma_resposta(cliente: Any) -> None:
    """Não se revela se o e-mail existe."""
    r = _login(cliente, "ninguem@lugar-nenhum.test")
    assert r.status_code == 401
    assert "Credenciais inválidas" in r.json()["detail"]


def test_login_de_usuario_de_tenant_inativo_falha(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE construtoras SET ativo = FALSE WHERE id = :t"),
            {"t": equipe["tenant_b"]},
        )
    r = _login(cliente, equipe["emails"]["admin_b"])
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 4–6. Integridade e ciclo de vida da sessão
# ---------------------------------------------------------------------------


def test_cookie_adulterado_e_rejeitado(cliente: Any, equipe: dict[str, Any]) -> None:
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    token = cliente.cookies.get("stellspy_sessao")
    assert token

    # Troca o último caractere da assinatura.
    corpo, assinatura = token.rsplit(".", 1)
    adulterado = f"{corpo}.{('a' if assinatura[-1] != 'a' else 'b')}{assinatura[1:]}"
    cliente.cookies.set("stellspy_sessao", adulterado)

    assert cliente.get("/auth/eu").status_code == 401


def test_sessao_expirada_e_rejeitada(cliente: Any, equipe: dict[str, Any]) -> None:
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    token = cliente.cookies.get("stellspy_sessao")
    dados = ler_token_sessao(token)

    # Mesmo jti, assinatura legítima, expiração no passado.
    antigo = criar_token_sessao(dados["jti"], expira_em=int(time.time()) - 60)
    cliente.cookies.set("stellspy_sessao", antigo)

    assert cliente.get("/auth/eu").status_code == 401


def test_logout_revoga_a_sessao_no_servidor(cliente: Any, equipe: dict[str, Any]) -> None:
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    token = cliente.cookies.get("stellspy_sessao")
    assert cliente.get("/auth/eu").status_code == 200

    assert cliente.post("/auth/logout").status_code == 200

    # Reapresenta o token antigo: assinatura continua válida, mas foi revogado.
    cliente.cookies.set("stellspy_sessao", token)
    assert cliente.get("/auth/eu").status_code == 401


# ---------------------------------------------------------------------------
# 7–8. Isolamento por sessão
# ---------------------------------------------------------------------------


def test_nao_acessa_obra_de_outra_construtora(cliente: Any, equipe: dict[str, Any]) -> None:
    """404, não 403: não se confirma a existência da obra alheia."""
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    csrf = cliente.cookies.get("stellspy_csrf")

    r = cliente.post(
        "/conferir",
        json={"obra_id": str(equipe["obra_b"]), "chave_acesso": chave_nfe_valida("2" * 43)},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404


def test_troca_de_tenant_pelo_corpo_e_ignorada(cliente: Any, equipe: dict[str, Any]) -> None:
    """Enviar tenant_id/papel no corpo não muda nada: a sessão manda."""
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    csrf = cliente.cookies.get("stellspy_csrf")

    r = cliente.post(
        "/conferir",
        json={
            "obra_id": str(equipe["obra_a"]),
            "chave_acesso": chave_nfe_valida("3" * 43),
            "tenant_id": str(equipe["tenant_b"]),
            "papel_global": "admin_tenant",
            "usuario_id": str(equipe["ids"]["admin_b"]),
        },
        headers={"X-CSRF-Token": csrf},
    )
    # Passa porque a obra é da construtora da sessão. Os campos extras são ignorados.
    assert r.status_code == 200
    assert cliente.get("/auth/eu").json()["tenant_id"] == str(equipe["tenant_a"])


# ---------------------------------------------------------------------------
# 9–11. Autorização por papel
# ---------------------------------------------------------------------------


def test_fiscal_nao_pode_fazer_override(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    _marcar_vermelho(sql_owner, equipe["nfe_a"])
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    csrf = cliente.cookies.get("stellspy_csrf")

    r = cliente.post(
        f"/override/{equipe['nfe_a']}",
        json={"justificativa": "aceito pelo fiscal"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403
    assert "não permitida" in r.json()["detail"]


def test_engenheiro_pode_fazer_override(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any
) -> None:
    _marcar_vermelho(sql_owner, equipe["nfe_a"])
    assert _login(cliente, equipe["emails"]["eng_a"]).status_code == 200
    csrf = cliente.cookies.get("stellspy_csrf")

    r = cliente.post(
        f"/override/{equipe['nfe_a']}",
        json={"justificativa": "divergencia analisada e aceita pelo RT"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status_conferencia"] == "VERDE"

    # A identidade gravada vem da sessão, não do corpo.
    ultimo = corpo["override_info"]["ultimo"]
    assert ultimo["usuario_id"] == str(equipe["ids"]["eng_a"])
    assert ultimo["usuario_email"] == equipe["emails"]["eng_a"]


def test_override_sem_sessao_de_usuario_e_recusado(
    cliente: Any, equipe: dict[str, Any], sql_owner: Any, monkeypatch: Any
) -> None:
    """Chave de obra não decide aceite de material não conforme."""
    _marcar_vermelho(sql_owner, equipe["nfe_a"])
    monkeypatch.setattr("app.auth_obra.SKIP_API_KEY", False)

    r = cliente.post(
        f"/override/{equipe['nfe_a']}",
        json={"justificativa": "aceito pela chave da obra"},
        headers={"X-API-KEY": equipe["api_key_a"]},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 12. CSRF
# ---------------------------------------------------------------------------


def test_operacao_por_cookie_sem_csrf_e_bloqueada(cliente: Any, equipe: dict[str, Any]) -> None:
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200

    r = cliente.post(
        "/conferir",
        json={"obra_id": str(equipe["obra_a"]), "chave_acesso": chave_nfe_valida("4" * 43)},
    )
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_csrf_invalido_e_bloqueado(cliente: Any, equipe: dict[str, Any]) -> None:
    assert _login(cliente, equipe["emails"]["fiscal_a"]).status_code == 200
    r = cliente.post(
        "/conferir",
        json={"obra_id": str(equipe["obra_a"]), "chave_acesso": chave_nfe_valida("5" * 43)},
        headers={"X-CSRF-Token": "valor-inventado"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 13. Regressão do fluxo legado por chave de obra
# ---------------------------------------------------------------------------


def test_fluxo_legado_por_api_key_continua_funcionando(
    cliente: Any, equipe: dict[str, Any], monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.auth_obra.SKIP_API_KEY", False)

    r = cliente.post(
        "/conferir",
        json={"obra_id": str(equipe["obra_a"]), "chave_acesso": chave_nfe_valida("6" * 43)},
        headers={"X-API-KEY": equipe["api_key_a"]},
    )
    # Sem NFE_IO_TOKEN o XML não existe -> PENDENTE, mas a autenticação passou.
    assert r.status_code == 200
    assert r.json()["status"] == "PENDENTE"


def test_api_key_de_outra_obra_e_rejeitada(
    cliente: Any, equipe: dict[str, Any], monkeypatch: Any
) -> None:
    monkeypatch.setattr("app.auth_obra.SKIP_API_KEY", False)

    r = cliente.post(
        "/conferir",
        json={"obra_id": str(equipe["obra_a"]), "chave_acesso": chave_nfe_valida("7" * 43)},
        headers={"X-API-KEY": equipe["api_key_b"]},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _marcar_vermelho(sql_owner: Any, nfe_log_id: uuid.UUID) -> None:
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE nfe_logs SET status_conferencia = 'VERMELHO' WHERE id = :id"),
            {"id": nfe_log_id},
        )


# ---------------------------------------------------------------------------
# Rate limit de login
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _limite_zerado() -> Any:
    """O contador é do processo: precisa começar limpo em cada teste."""
    from app.limite_tentativas import limite

    limite().resetar()
    yield
    limite().resetar()


def test_login_bloqueia_apos_o_limite_de_falhas(
    cliente: Any, equipe: dict[str, Any], monkeypatch: Any
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FALHAS", "3")
    email = equipe["emails"]["fiscal_a"]

    for _ in range(3):
        assert _login(cliente, email, senha="errada").status_code == 401

    bloqueado = _login(cliente, email, senha="errada")
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["Retry-After"]) > 0

    # E mesmo a senha correta é recusada enquanto durar o bloqueio.
    assert _login(cliente, email).status_code == 429


def test_login_com_sucesso_zera_o_contador(
    cliente: Any, equipe: dict[str, Any], monkeypatch: Any
) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FALHAS", "3")
    email = equipe["emails"]["fiscal_a"]

    assert _login(cliente, email, senha="errada").status_code == 401
    assert _login(cliente, email, senha="errada").status_code == 401

    # Sucesso limpa o histórico das duas chaves (e-mail e IP).
    assert _login(cliente, email).status_code == 200

    # Duas falhas novas não devem encontrar o contador anterior.
    assert _login(cliente, email, senha="errada").status_code == 401
    assert _login(cliente, email, senha="errada").status_code == 401


def test_bloqueio_por_ip_afeta_outro_email(
    cliente: Any, equipe: dict[str, Any], monkeypatch: Any
) -> None:
    """
    Varredura de contas: atacar vários e-mails do mesmo lugar precisa custar
    caro. A chave por IP é o que impede trocar de alvo e continuar.
    """
    monkeypatch.setenv("AUTH_LOGIN_MAX_FALHAS", "2")
    monkeypatch.setenv("AUTH_LOGIN_JANELA_SEGUNDOS", "60")

    assert _login(cliente, equipe["emails"]["fiscal_a"], senha="errada").status_code == 401
    assert _login(cliente, equipe["emails"]["fiscal_a"], senha="errada").status_code == 401

    # Conta diferente, mesmo IP (TestClient usa o mesmo host).
    assert _login(cliente, equipe["emails"]["eng_a"]).status_code == 429
