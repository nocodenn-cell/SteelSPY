"""Backend de Storage do Supabase — contrato da porta, sem rede real.

O que se prova aqui não é "o upload chama a URL": é que o bucket é tratado como
privado (service role só no header), que a chave não escapa da raiz e que uma
falha do Storage vira erro de domínio, nunca exceção solta.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import armazenamento as arm

URL = "https://akvbtceshpsvsuacueaq.supabase.co"
CHAVE = "service-role-de-teste"


def _cliente(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _backend(handler) -> arm.ArmazenamentoSupabase:
    return arm.ArmazenamentoSupabase(URL, CHAVE, "evidencias", cliente=_cliente(handler))


def test_gravar_envia_para_o_bucket_privado_com_service_role_no_header():
    vistos: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        vistos.append(request)
        return httpx.Response(200, json={"Key": "ok"})

    backend = _backend(handler)
    backend.gravar("tenant/obra/evidencia/original.jpg", b"\xff\xd8\xffdados")

    assert len(vistos) == 1
    requisicao = vistos[0]
    assert requisicao.method == "POST"
    assert str(requisicao.url) == (
        f"{URL}/storage/v1/object/evidencias/tenant/obra/evidencia/original.jpg"
    )
    assert requisicao.headers["authorization"] == f"Bearer {CHAVE}"
    assert requisicao.headers["apikey"] == CHAVE
    assert requisicao.headers["x-upsert"] == "false"
    assert requisicao.headers["content-type"] == "image/jpeg"
    # A credencial não pode aparecer na URL (log, histórico, referer).
    assert "service-role" not in str(requisicao.url)
    assert requisicao.url.query == b""


def test_objeto_duplicado_vira_chave_ja_existe():
    backend = _backend(
        lambda request: httpx.Response(
            400, json={"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"}
        )
    )
    with pytest.raises(arm.ChaveJaExiste):
        backend.gravar("a/b.jpg", b"x")


def test_falha_do_storage_vira_erro_de_dominio():
    backend = _backend(lambda request: httpx.Response(503, text="indisponível"))
    with pytest.raises(arm.ErroArmazenamento) as exc:
        backend.gravar("a/b.jpg", b"x")
    assert "503" in str(exc.value)


def test_ler_devolve_bytes_e_404_vira_erro():
    backend = _backend(lambda request: httpx.Response(200, content=b"conteudo"))
    assert backend.ler("a/b.jpg") == b"conteudo"

    ausente = _backend(lambda request: httpx.Response(404))
    with pytest.raises(arm.ErroArmazenamento):
        ausente.ler("a/b.jpg")


def test_existe_usa_head_e_distingue_200_de_404():
    metodos: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        metodos.append(request.method)
        return httpx.Response(200 if "presente" in str(request.url) else 404)

    backend = _backend(handler)
    assert backend.existe("a/presente.jpg") is True
    assert backend.existe("a/ausente.jpg") is False
    assert metodos == ["HEAD", "HEAD"]


def test_remover_e_idempotente_mas_falha_real_sobe():
    backend = _backend(lambda request: httpx.Response(404))
    backend.remover("a/b.jpg")  # já não existia: intenção satisfeita

    quebrado = _backend(lambda request: httpx.Response(500))
    with pytest.raises(arm.ErroArmazenamento):
        quebrado.remover("a/b.jpg")


@pytest.mark.parametrize(
    "chave",
    ["", "/absoluta.jpg", "../fora.jpg", "a/../../b.jpg", "a//b.jpg", "C:/x.jpg", "a\\..\\b.jpg"],
)
def test_chave_invalida_e_rejeitada_antes_de_qualquer_requisicao(chave: str):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - não deve rodar
        chamadas.append(request)
        return httpx.Response(200)

    backend = _backend(handler)
    with pytest.raises(arm.ChaveInvalida):
        backend.gravar(chave, b"x")
    assert chamadas == []


def test_http_so_e_aceito_em_loopback():
    with pytest.raises(arm.ErroArmazenamento):
        arm.ArmazenamentoSupabase("http://exemplo.com", CHAVE, "evidencias")
    arm.ArmazenamentoSupabase("http://127.0.0.1:55321", CHAVE, "evidencias").fechar()


def test_configuracao_incompleta_falha_alto():
    with pytest.raises(arm.ErroArmazenamento):
        arm.ArmazenamentoSupabase(URL, "", "evidencias")


def test_selecao_de_backend_e_explicita(monkeypatch: pytest.MonkeyPatch):
    arm.definir_backend(None)
    monkeypatch.delenv("EVIDENCIAS_STORAGE", raising=False)
    assert isinstance(arm.backend(), arm.ArmazenamentoLocal)

    monkeypatch.setenv("EVIDENCIAS_STORAGE", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    arm.definir_backend(None)
    with pytest.raises(arm.ErroArmazenamento):
        arm.backend()

    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", CHAVE)
    arm.definir_backend(None)
    backend = arm.backend()
    assert isinstance(backend, arm.ArmazenamentoSupabase)
    assert backend.bucket == "evidencias"

    monkeypatch.setenv("EVIDENCIAS_STORAGE", "qualquer-coisa")
    arm.definir_backend(None)
    with pytest.raises(arm.ErroArmazenamento):
        arm.backend()

    arm.definir_backend(None)
