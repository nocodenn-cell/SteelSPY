"""Pipeline de evidências com PostgreSQL real e armazenamento local isolado.

Cada teste corresponde a um cenário da especificação da Sprint 1. O que se
prova aqui não é "o upload funciona": é que ele funciona **sem vazar**, que é
a parte difícil.

O armazenamento é redirecionado para um diretório temporário por teste, então
nenhuma foto real toca o disco do projeto.
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
from app.services import evidencias as svc

SENHA = "SenhaForte#123"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage(tmp_path: Any) -> Any:
    """Armazenamento local num diretório temporário; restaurado ao final."""
    backend = arm.ArmazenamentoLocal(tmp_path / "evidencias")
    arm.definir_backend(backend)
    try:
        yield backend
    finally:
        arm.definir_backend(None)


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
def usuarios(sql_owner: Any, cenario: dict[str, Any]) -> dict[str, Any]:
    """fiscal (obra A), auditor (obra A) e admin da construtora B."""
    sufixo = uuid.uuid4().hex[:8]
    dados = {
        "fiscal": ("fiscal", "fiscal", cenario["tenant_a"], cenario["obra_a"]),
        "auditor": ("auditor", "auditor", cenario["tenant_a"], cenario["obra_a"]),
        "admin_b": ("admin", "admin_tenant", cenario["tenant_b"], cenario["obra_b"]),
    }
    saida: dict[str, Any] = {"emails": {}, "ids": {}}
    senha_hash = hash_senha(SENHA)

    with sql_owner.begin() as conn:
        for chave, (nome, papel_global, tenant, obra) in dados.items():
            uid = uuid.uuid4()
            email = f"{nome}.{sufixo}@teste.local"
            saida["emails"][chave] = email
            saida["ids"][chave] = uid
            conn.execute(
                text(
                    "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                    "VALUES (:id, :t, :n, :e, :h, :p)"
                ),
                {"id": uid, "t": tenant, "n": nome, "e": email, "h": senha_hash, "p": papel_global},
            )
            conn.execute(
                text(
                    "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) "
                    "VALUES (:t, :o, :u, :p)"
                ),
                # papel na obra nunca é admin_tenant (o CHECK não permite);
                # o admin de B entra como engenheiro na obra dele.
                {"t": tenant, "o": obra, "u": uid, "p": "engenheiro" if papel_global == "admin_tenant" else papel_global},
            )

    return {**cenario, **saida}


def imagem_png(cor: tuple[int, int, int] = (200, 30, 30), lado: int = 64) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado), cor).save(buf, format="PNG")
    return buf.getvalue()


def _login(cliente: TestClient, email: str) -> str:
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _upload(
    cliente: TestClient,
    obra_id: str,
    conteudo: bytes,
    *,
    csrf: str | None,
    mime: str = "image/png",
    nome: str = "foto.png",
    dados_extra: dict[str, str] | None = None,
    recebimento_id: str | None = None,
) -> Any:
    form = {"tipo": "material", "origem": "upload"}
    if recebimento_id:
        form["recebimento_id"] = recebimento_id
    if dados_extra:
        form.update(dados_extra)
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return cliente.post(
        f"/obras/{obra_id}/evidencias",
        files={"arquivo": (nome, conteudo, mime)},
        data=form,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# 1. Upload válido
# ---------------------------------------------------------------------------


def test_upload_valido_cria_evidencia(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    conteudo = imagem_png()

    r = _upload(cliente, str(usuarios["obra_a"]), conteudo, csrf=csrf)
    assert r.status_code == 201, r.text
    corpo = r.json()

    assert corpo["criada"] is True
    assert corpo["sha256_original"] == svc.sha256(conteudo)
    assert corpo["bytes_original"] == len(conteudo)
    assert corpo["mime"] == "image/jpeg"  # normalizada
    assert corpo["largura"] > 0 and corpo["altura"] > 0
    assert corpo["conteudo_url"].endswith("/conteudo")

    # A chave interna NUNCA pode aparecer na resposta.
    assert "storage_key" not in corpo
    assert "storage_key_original" not in corpo


# ---------------------------------------------------------------------------
# 2. Arquivo inválido
# ---------------------------------------------------------------------------


def test_arquivo_que_nao_e_imagem_e_rejeitado(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(cliente, str(usuarios["obra_a"]), b"isto nao e uma imagem", csrf=csrf)
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# 3. Acima do limite
# ---------------------------------------------------------------------------


def test_arquivo_acima_do_limite_e_rejeitado(
    cliente: Any, usuarios: dict[str, Any], storage: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("EVIDENCIA_MAX_BYTES", "1024")
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    grande = imagem_png(lado=400)  # PNG de 400x400 passa de 1 KB
    assert len(grande) > 1024

    r = _upload(cliente, str(usuarios["obra_a"]), grande, csrf=csrf)
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# 4. MIME falso
# ---------------------------------------------------------------------------


def test_mime_declarado_divergente_do_conteudo_e_rejeitado(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    """Arquivo PNG anunciado como JPEG: a assinatura real denuncia."""
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(
        cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf, mime="image/jpeg", nome="falsa.jpg"
    )
    assert r.status_code == 400
    assert "não corresponde" in r.json()["detail"]


def test_extensao_mentirosa_com_conteudo_valido_e_aceita_pelo_conteudo(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    """O que vale é o conteúdo: PNG chamado .jpg é PNG, e é gravado como PNG original."""
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(
        cliente, str(usuarios["obra_a"]), imagem_png((10, 200, 10)), csrf=csrf,
        mime="image/png", nome="troca.jpg",
    )
    assert r.status_code == 201
    assert r.json()["mime"] == "image/jpeg"


# ---------------------------------------------------------------------------
# 5–8. Autenticação, permissão e tenant
# ---------------------------------------------------------------------------


def test_upload_sem_sessao_e_rejeitado(cliente: Any, usuarios: dict[str, Any], storage: Any) -> None:
    r = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=None)
    assert r.status_code == 401


def test_upload_sem_csrf_e_rejeitado(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=None)
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_auditor_nao_pode_enviar_evidencia(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["auditor"])
    r = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf)
    assert r.status_code == 403
    assert "anexar_evidencia" in r.json()["detail"]


def test_obra_de_outra_construtora_responde_404(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(cliente, str(usuarios["obra_b"]), imagem_png(), csrf=csrf)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 9. Recebimento de outra obra / outro tenant
# ---------------------------------------------------------------------------


def test_recebimento_de_outra_obra_e_recusado(
    cliente: Any, usuarios: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """Cria um recebimento na obra B e tenta anexar evidência a ele na obra A."""
    rec_b = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO recebimentos (id, tenant_id, obra_id) VALUES (:id, :t, :o)"
            ),
            {"id": rec_b, "t": usuarios["tenant_b"], "o": usuarios["obra_b"]},
        )

    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    r = _upload(
        cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf, recebimento_id=str(rec_b)
    )
    assert r.status_code == 404
    assert "recebimento" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 10–11. Idempotência e integridade
# ---------------------------------------------------------------------------


def test_reenvio_identico_e_idempotente(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    conteudo = imagem_png((5, 5, 200))

    primeira = _upload(cliente, str(usuarios["obra_a"]), conteudo, csrf=csrf)
    segunda = _upload(cliente, str(usuarios["obra_a"]), conteudo, csrf=csrf)

    assert primeira.status_code == 201
    assert segunda.status_code == 200, "duplicata não é erro: é retry"
    assert segunda.json()["id"] == primeira.json()["id"]
    assert segunda.json()["criada"] is False


def test_arquivos_diferentes_geram_evidencias_diferentes(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    a = _upload(cliente, str(usuarios["obra_a"]), imagem_png((1, 2, 3)), csrf=csrf)
    b = _upload(cliente, str(usuarios["obra_a"]), imagem_png((4, 5, 6)), csrf=csrf)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


def test_hash_do_original_confere_com_os_bytes_enviados(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    import hashlib

    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    conteudo = imagem_png((77, 88, 99))
    corpo = _upload(cliente, str(usuarios["obra_a"]), conteudo, csrf=csrf).json()
    assert corpo["sha256_original"] == hashlib.sha256(conteudo).hexdigest()


# ---------------------------------------------------------------------------
# 12–13. Download autorizado e não autorizado
# ---------------------------------------------------------------------------


def test_download_autorizado_devolve_o_original_byte_a_byte(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    conteudo = imagem_png((123, 45, 67))
    criada = _upload(cliente, str(usuarios["obra_a"]), conteudo, csrf=csrf).json()

    r = cliente.get(f"/evidencias/{criada['id']}/conteudo", params={"variante": "original"})
    assert r.status_code == 200
    assert r.content == conteudo, "o original precisa ser devolvido sem qualquer transformação"
    assert r.headers["x-conteudo-sha256"] == criada["sha256_original"]


def test_download_normalizado_e_jpeg(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    r = cliente.get(f"/evidencias/{criada['id']}/conteudo")
    assert r.status_code == 200
    assert r.content.startswith(b"\xff\xd8\xff"), "normalizada é JPEG"
    assert r.headers["x-conteudo-sha256"] == criada["sha256"]


def test_download_por_outra_construtora_responde_404(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    # Troca de usuário: o TestClient guarda o cookie anterior, então limpamos.
    cliente.cookies.clear()
    _login(cliente, usuarios["emails"]["admin_b"])

    r = cliente.get(f"/evidencias/{criada['id']}/conteudo")
    assert r.status_code == 404

    meta = cliente.get(f"/evidencias/{criada['id']}")
    assert meta.status_code == 404


def test_metadados_nao_expoem_caminho_interno(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    meta = cliente.get(f"/evidencias/{criada['id']}")
    assert meta.status_code == 200
    texto = meta.text
    assert "storage_key" not in texto
    assert str(storage.raiz) not in texto


# ---------------------------------------------------------------------------
# 14–15. Falha de armazenamento e recuperação
# ---------------------------------------------------------------------------


class _BackendQueFalha:
    """Falha sempre na gravação."""

    def gravar(self, chave: str, dados: bytes) -> None:
        raise arm.ErroArmazenamento("disco cheio")

    def ler(self, chave: str) -> bytes:  # pragma: no cover
        raise arm.ErroArmazenamento("x")

    def existe(self, chave: str) -> bool:  # pragma: no cover
        return False

    def remover(self, chave: str) -> None:  # pragma: no cover
        pass


class _BackendQueFalhaNaSegundaGravacao:
    """Grava o original e falha na normalizada — simula falha parcial."""

    def __init__(self, real: Any) -> None:
        self.real = real
        self.chamadas = 0
        self.gravadas: list[str] = []

    def gravar(self, chave: str, dados: bytes) -> None:
        self.chamadas += 1
        if self.chamadas == 2:
            raise arm.ErroArmazenamento("falha na segunda gravação")
        self.real.gravar(chave, dados)
        self.gravadas.append(chave)

    def ler(self, chave: str) -> bytes:
        return self.real.ler(chave)

    def existe(self, chave: str) -> bool:
        return self.real.existe(chave)

    def remover(self, chave: str) -> None:
        self.real.remover(chave)


def test_falha_de_armazenamento_responde_503(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    arm.definir_backend(_BackendQueFalha())
    csrf = _login(cliente, usuarios["emails"]["fiscal"])

    r = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf)
    assert r.status_code == 503
    assert "Armazenamento" in r.json()["detail"]


def test_falha_parcial_nao_deixa_objeto_orfao(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    backend = _BackendQueFalhaNaSegundaGravacao(storage)
    arm.definir_backend(backend)
    csrf = _login(cliente, usuarios["emails"]["fiscal"])

    r = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf)
    assert r.status_code == 503

    # O primeiro objeto foi gravado e precisa ter sido removido no rollback.
    assert backend.gravadas, "o cenário precisa ter gravado o primeiro objeto"
    for chave in backend.gravadas:
        assert not storage.existe(chave), f"objeto órfão ficou no armazenamento: {chave}"


# ---------------------------------------------------------------------------
# 16. Isolamento no PostgreSQL
# ---------------------------------------------------------------------------


def test_rls_isola_evidencias_no_banco(
    cliente: Any, usuarios: dict[str, Any], storage: Any, sql_owner: Any, abrir_como: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    with abrir_como(usuarios["tenant_a"]) as conn:
        visiveis = conn.execute(text("SELECT count(*) FROM evidencias")).scalar_one()
    assert visiveis >= 1

    with abrir_como(usuarios["tenant_b"]) as conn:
        alheias = conn.execute(
            text("SELECT count(*) FROM evidencias WHERE id = :id"), {"id": criada["id"]}
        ).scalar_one()
        total_b = conn.execute(text("SELECT count(*) FROM evidencias")).scalar_one()
    assert alheias == 0
    assert total_b == 0, "tenant B não deve enxergar nenhuma evidência de A"

    with abrir_como(None) as conn:
        sem_contexto = conn.execute(text("SELECT count(*) FROM evidencias")).scalar_one()
    assert sem_contexto == 0


def test_trilha_de_auditoria_registra_recebimento_e_download(
    cliente: Any, usuarios: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()
    cliente.get(f"/evidencias/{criada['id']}/conteudo")

    with sql_owner.connect() as conn:
        tipos = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT tipo FROM evidencia_eventos WHERE evidencia_id = :id ORDER BY id"
                ),
                {"id": criada["id"]},
            )
        ]
    assert tipos[:2] == ["recebida", "armazenada"]
    assert "baixada" in tipos
