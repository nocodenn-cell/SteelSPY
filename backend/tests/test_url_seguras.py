import pytest

from app.utils import url_seguras


def test_foto_https_permitida(monkeypatch):
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)
    u = "https://cdn.exemplo.com.br/nf/foto.jpg"
    assert url_seguras.validar_url_imagem_publica(u) == u


def test_foto_rejeita_localhost(monkeypatch):
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)
    with pytest.raises(url_seguras.URLNaoPermitidaError):
        url_seguras.validar_url_imagem_publica("https://localhost/x.png")


def test_foto_allowlist(monkeypatch):
    monkeypatch.setenv("FOTO_URL_ALLOWED_HOSTS", "storage.supabase.co")
    url_seguras.validar_url_imagem_publica("https://storage.supabase.co/bucket/x.png")
    with pytest.raises(url_seguras.URLNaoPermitidaError):
        url_seguras.validar_url_imagem_publica("https://evil.com/x.png")


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.exemplo.com.br:99999/foto.jpg",  # fora de 0-65535
        "https://cdn.exemplo.com.br:abc/foto.jpg",  # não numérica
        "https://cdn.exemplo.com.br:8443/foto.jpg",  # numérica, mas só 443 é aceita
    ],
)
def test_foto_rejeita_porta_invalida_ou_diferente_de_443(monkeypatch, url):
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)
    with pytest.raises(url_seguras.URLNaoPermitidaError):
        url_seguras.validar_url_imagem_publica(url)


def test_foto_aceita_porta_443_explicita(monkeypatch):
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)
    u = "https://cdn.exemplo.com.br:443/foto.jpg"
    assert url_seguras.validar_url_imagem_publica(u) == u


@pytest.mark.parametrize("url", ["https://100.64.0.1/x", "https://100.127.255.254/x"])
def test_foto_rejeita_cgnat_100_64_literal(monkeypatch, url):
    """B9: 100.64.0.0/10 (CGNAT) não é 'privado' para ipaddress, mas não é público."""
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)
    with pytest.raises(url_seguras.URLNaoPermitidaError):
        url_seguras.validar_url_imagem_publica(url)


def test_foto_cgnat_nao_passa_pelo_download_seguro(monkeypatch):
    """B9: mesmo que o nome resolva para CGNAT, o download é recusado sem conectar."""
    import httpx

    from app.utils.url_seguras import baixar_foto_segura

    chamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(str(request.url))
        return httpx.Response(200, content=b"\xff\xd8\xff\xe0" + b"0" * 200)

    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/foto.jpg",
        resolver=lambda host: ["100.64.0.1"],
        transport=httpx.MockTransport(handler),
    )
    assert dados is None
    assert chamadas == []
