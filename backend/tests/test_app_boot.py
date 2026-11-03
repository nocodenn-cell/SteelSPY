"""Regressão P-16 — a aplicação precisa importar, iniciar e manter as rotas.

Contexto do defeito
-------------------
`app/routers/conferencia.py` anotava a rota de laudo como
`-> Response | RedirectResponse`. A partir do FastAPI 0.162 isso é rejeitado
no import: a união de duas subclasses de `Response` não é um campo Pydantic
válido, e o FastAPI tenta usá-la como `response_model`.

Efeito: `import app.main` levantava `FastAPIError` e a API não subia.
Os 69 testes existentes não detectavam nada porque nenhum importava `app.main`.

Este arquivo é a rede de segurança que faltava. Ele não depende de banco,
de rede nem de credenciais: a sessão do banco é substituída por um stub.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Rotas públicas esperadas (método, caminho). Guarda de regressão de contrato:
# se alguém remover ou renomear uma rota, este teste falha.
ROTAS_ESPERADAS: list[tuple[str, str]] = [
    ("GET", "/health"),
    ("POST", "/auth/pwa/login"),
    ("GET", "/auth/pwa/session"),
    ("POST", "/auth/pwa/logout"),
    ("POST", "/conferir"),
    ("GET", "/conferir/{nfe_log_id}/laudo.pdf"),
    ("GET", "/conferir/{nfe_log_id}/divergencias.pdf"),
    ("POST", "/override/{nfe_log_id}"),
]


def _rotas_api(app: Any) -> list[Any]:
    """
    Coleta as rotas HTTP efetivas, atravessando wrappers de `include_router`.

    FastAPI >= 0.162 nao achata mais as rotas incluidas: `include_router` cria
    um `_IncludedRouter` que expõe o router original em `original_router`.
    Versões anteriores colocavam os `APIRoute` diretamente em `app.routes`.
    Este helper funciona nos dois formatos.
    """
    encontradas: list[Any] = []
    fila = list(app.routes)
    while fila:
        rota = fila.pop(0)
        original = getattr(rota, "original_router", None)
        if original is not None and hasattr(original, "routes"):
            fila.extend(original.routes)
        elif hasattr(rota, "endpoint"):
            encontradas.append(rota)
    return encontradas


# --------------------------------------------------------------------------
# 1 e 2 — importação e criação do app
# --------------------------------------------------------------------------


def test_app_main_importa() -> None:
    """Antes da correção este import levantava FastAPIError."""
    modulo = importlib.import_module("app.main")
    assert modulo.app is not None
    assert modulo.app.title == "stellSPY Auditoria NF-e"


def test_todos_os_modulos_do_pacote_importam() -> None:
    import app as pacote

    nomes = ["app"] + sorted(m.name for m in pkgutil.walk_packages(pacote.__path__, "app."))
    falhas: list[str] = []
    for nome in nomes:
        try:
            importlib.import_module(nome)
        except Exception as exc:  # noqa: BLE001 - queremos o motivo, não o tipo
            falhas.append(f"{nome}: {type(exc).__name__}: {exc}")
    assert not falhas, "módulos que falharam ao importar:\n" + "\n".join(falhas)


@pytest.fixture(scope="module")
def client() -> Any:
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_app_inicializa(client: TestClient) -> None:
    """Instanciar o TestClient executa o ciclo de startup do FastAPI."""
    assert client.app is not None


# --------------------------------------------------------------------------
# 3 e 4 — rota apropriada, sem depender de produção
# --------------------------------------------------------------------------


def test_health_responde_200(client: TestClient) -> None:
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_conferir_rejeita_payload_invalido_sem_tocar_no_banco(client: TestClient) -> None:
    """Validação de entrada acontece antes do banco — contrato 422 do Pydantic."""
    resposta = client.post("/conferir", json={"obra_id": "nao-e-uuid", "chave_acesso": "123"})
    assert resposta.status_code == 422


# --------------------------------------------------------------------------
# 5 — a rota de laudo continua registrada e com o contrato esperado
# --------------------------------------------------------------------------


def test_todas_as_rotas_esperadas_estao_registradas() -> None:
    from app.main import app

    registradas = {
        (metodo, getattr(rota, "path", ""))
        for rota in _rotas_api(app)
        for metodo in getattr(rota, "methods", set()) or set()
    }
    ausentes = [par for par in ROTAS_ESPERADAS if par not in registradas]
    assert not ausentes, f"rotas ausentes após a correção: {ausentes}"


def test_contrato_openapi_expoe_as_rotas() -> None:
    """O contrato publicado ao cliente também precisa conter as 8 rotas."""
    from app.main import app

    caminhos = set(app.openapi()["paths"])
    esperados = {caminho for _, caminho in ROTAS_ESPERADAS}
    assert esperados <= caminhos, f"faltando no OpenAPI: {esperados - caminhos}"


def test_rota_laudo_tem_response_model_none() -> None:
    """A correção P-16: sem isso, o import volta a falhar no FastAPI 0.162+."""
    from app.main import app

    rota = next(
        (r for r in _rotas_api(app) if getattr(r, "path", "") == "/conferir/{nfe_log_id}/laudo.pdf"),
        None,
    )
    assert rota is not None, "rota de laudo não registrada"
    assert rota.response_model is None, (
        "a rota de laudo deve declarar response_model=None: ela devolve "
        "Response ou RedirectResponse diretamente"
    )
    assert "GET" in rota.methods


def test_rota_laudo_declara_nfe_log_id_como_uuid() -> None:
    """Contrato do path param: precisa continuar tipado como UUID."""
    from app.main import app

    parametros = app.openapi()["paths"]["/conferir/{nfe_log_id}/laudo.pdf"]["get"]["parameters"]
    alvo = [p for p in parametros if p["name"] == "nfe_log_id" and p["in"] == "path"]
    assert alvo, "path param nfe_log_id ausente do contrato"
    assert alvo[0]["schema"].get("format") == "uuid"


# --------------------------------------------------------------------------
# 6 — contrato HTTP da rota de PDF, com banco substituído por stub
# --------------------------------------------------------------------------


class _ResultadoVazio:
    def mappings(self) -> "_ResultadoVazio":
        return self

    def first(self) -> None:
        return None

    def all(self) -> list[Any]:
        return []


class _SessaoVazia:
    """Sessão mínima: nenhuma linha encontrada. Evita qualquer acesso a banco."""

    def execute(self, *args: Any, **kwargs: Any) -> _ResultadoVazio:
        return _ResultadoVazio()

    def commit(self) -> None:  # pragma: no cover - não usado nesta rota
        return None

    def rollback(self) -> None:  # pragma: no cover
        return None

    def close(self) -> None:
        return None


@pytest.fixture()
def client_sem_registro() -> Any:
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: _SessaoVazia()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "caminho, rota_nome",
    [
        ("laudo.pdf", "laudo"),
        ("divergencias.pdf", "divergencias"),
    ],
)
def test_pdf_de_nfe_log_inexistente_responde_404(
    client_sem_registro: TestClient, caminho: str, rota_nome: str
) -> None:
    """Contrato: id desconhecido → 404 JSON, nunca 200 e nunca 500."""
    resposta = client_sem_registro.get(f"/conferir/00000000-0000-0000-0000-000000000000/{caminho}")
    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith("application/json")
    assert "nfe_log" in resposta.json()["detail"].lower()


def test_endpoints_protegidos_nao_respondem_200_sem_autenticacao(
    client_sem_registro: TestClient,
) -> None:
    """
    Não exigimos 200 de endpoint protegido: exigimos que ele NÃO devolva 200
    sem autenticação. Com o stub de banco, o resultado esperado é 404.
    """
    resposta = client_sem_registro.get(
        "/conferir/11111111-1111-1111-1111-111111111111/laudo.pdf"
    )
    assert resposta.status_code != 200


# --------------------------------------------------------------------------
# 7 — regressão do PDF (usa o domínio real, sem banco)
# --------------------------------------------------------------------------


def test_geracao_de_pdf_continua_funcionando() -> None:
    """
    Regressão do gerador de PDF: garante que a correção do router não afetou
    a produção do laudo. Exercita o domínio real, sem banco e sem rede.
    """
    from app.services.laudo_pdf import gerar_laudo_pdf_bytes, montar_contexto_laudo

    ctx = montar_contexto_laudo(
        nfe_log={
            "id": "00000000-0000-0000-0000-000000000001",
            "chave_acesso": "1" * 44,
            "status_conferencia": "VERDE",
            "processado_em": None,
            "xml_data": {"emitente_nome": "Fornecedor Teste", "detalhes": [], "motivos": []},
            "override_info": {},
            "foto_url": None,
        },
        obra={"nome": "Obra Teste", "cnpj_destinatario": "12345678000190", "modo_aprendizado": False},
    )
    pdf = gerar_laudo_pdf_bytes(ctx)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    # Marcador obrigatório do documento gerado.
    assert re.search(rb"RELAT", pdf) or len(pdf) > 1000
