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


def test_redirect_laudo_somente_supabase():
    base = "https://abcdefgh.supabase.co"
    ok = f"{base}/storage/v1/object/public/laudos/x.pdf"
    assert url_seguras.url_redirect_laudo_confiavel(ok, base) is True
    assert url_seguras.url_redirect_laudo_confiavel("https://evil.com/phish", base) is False
    assert url_seguras.url_redirect_laudo_confiavel(ok, "") is False
