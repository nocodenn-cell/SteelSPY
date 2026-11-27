"""P-07: download de foto_url sem SSRF via redirect nem via DNS (fixação de IP)."""

import gzip

import httpx
import pytest

from app.utils import url_seguras
from app.utils.url_seguras import baixar_foto_segura, ip_publico

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PUBLICO = "8.8.8.8"  # endereço público usado nos testes


@pytest.fixture(autouse=True)
def _sem_allowlist(monkeypatch):
    monkeypatch.delenv("FOTO_URL_ALLOWED_HOSTS", raising=False)


def _resolver(mapa):
    """DNS falso: nome -> lista de IPs. Nome desconhecido falha como o SO falharia."""
    def resolver(hostname):
        if hostname not in mapa:
            raise OSError(f"nao resolve: {hostname}")
        return list(mapa[hostname])
    return resolver


def _transporte(rotas):
    """
    rotas: {(ip, path): resposta}. Registra cada requisição feita.
    A requisição deve chegar ao IP fixado, com o hostname no Host.
    """
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append((request.url.host, request.url.path, request.headers.get("host")))
        return rotas.get((request.url.host, request.url.path), httpx.Response(404))

    return httpx.MockTransport(handler), chamadas


def _redirect(destino):
    return httpx.Response(302, headers={"location": destino})


# --- redirects legítimos -----------------------------------------------------


def test_foto_direta_publica_e_baixada_pelo_ip_validado():
    transport, chamadas = _transporte({(PUBLICO, "/foto.jpg"): httpx.Response(200, content=JPEG)})
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/foto.jpg",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    )
    assert dados == JPEG
    # conexão no IP, Host e SNI no hostname (certificado continua sendo verificado)
    assert chamadas == [(PUBLICO, "/foto.jpg", "cdn.exemplo.com.br")]


def test_redirect_legitimo_para_outro_caminho_do_mesmo_host_funciona():
    transport, chamadas = _transporte(
        {
            (PUBLICO, "/a"): _redirect("/b.jpg"),
            (PUBLICO, "/b.jpg"): httpx.Response(200, content=JPEG),
        }
    )
    dados = baixar_foto_segura(
        "https://storage.supabase.co/a",
        resolver=_resolver({"storage.supabase.co": [PUBLICO]}),
        transport=transport,
    )
    assert dados == JPEG
    assert len(chamadas) == 2


def test_redirect_legitimo_para_outro_host_publico_funciona():
    outro = "1.1.1.1"
    transport, chamadas = _transporte(
        {
            (PUBLICO, "/a"): _redirect("https://cdn2.exemplo.com.br/b.png"),
            (outro, "/b.png"): httpx.Response(200, content=b"\x89PNG" + b"0" * 50),
        }
    )
    dados = baixar_foto_segura(
        "https://cdn1.exemplo.com.br/a",
        resolver=_resolver({"cdn1.exemplo.com.br": [PUBLICO], "cdn2.exemplo.com.br": [outro]}),
        transport=transport,
    )
    assert dados is not None and dados.startswith(b"\x89PNG")
    assert [c[0] for c in chamadas] == [PUBLICO, outro]


# --- redirects maliciosos ----------------------------------------------------


def test_redirect_para_host_que_resolve_para_rede_privada_e_bloqueado():
    transport, chamadas = _transporte(
        {
            (PUBLICO, "/a"): _redirect("https://intranet.exemplo.com/admin"),
            ("10.0.0.5", "/admin"): httpx.Response(200, content=JPEG),
        }
    )
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/a",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO], "intranet.exemplo.com": ["10.0.0.5"]}),
        transport=transport,
    )
    assert dados is None
    # o salto para 10.0.0.5 nunca foi enviado
    assert all(c[0] != "10.0.0.5" for c in chamadas)


@pytest.mark.parametrize(
    "destino",
    [
        "http://169.254.169.254/latest/meta-data/",  # esquema http
        "https://169.254.169.254/latest/meta-data/",  # metadata literal
        "https://127.0.0.1/admin",  # loopback literal
        "https://[::1]/admin",  # loopback IPv6
        "https://[::ffff:127.0.0.1]/admin",  # IPv4 mapeado em IPv6
        "https://localhost/admin",
        "https://service.internal/admin",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_",
    ],
)
def test_redirect_para_destino_interno_ou_esquema_proibido_e_bloqueado(destino):
    transport, chamadas = _transporte({(PUBLICO, "/a"): _redirect(destino)})
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/a",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    )
    assert dados is None
    assert len(chamadas) == 1  # só a requisição inicial


def test_loop_de_redirect_e_interrompido():
    transport, chamadas = _transporte({(PUBLICO, "/a"): _redirect("/a")})
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/a",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    )
    assert dados is None
    assert len(chamadas) == url_seguras.MAX_REDIRECTS_FOTO + 1


def test_redirect_sem_location_devolve_none():
    transport, _ = _transporte({(PUBLICO, "/a"): httpx.Response(302)})
    assert baixar_foto_segura(
        "https://cdn.exemplo.com.br/a",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    ) is None


# --- DNS: validação e evasão ------------------------------------------------


def test_host_publico_que_resolve_para_loopback_e_bloqueado():
    """Antes: `evil.com` passava na validação literal e era buscado mesmo resolvendo para 127.0.0.1."""
    transport, chamadas = _transporte({("127.0.0.1", "/x.jpg"): httpx.Response(200, content=JPEG)})
    dados = baixar_foto_segura(
        "https://evil.com/x.jpg",
        resolver=_resolver({"evil.com": ["127.0.0.1"]}),
        transport=transport,
    )
    assert dados is None and chamadas == []


def test_resposta_dns_mista_com_um_endereco_privado_e_recusada():
    transport, chamadas = _transporte({(PUBLICO, "/x.jpg"): httpx.Response(200, content=JPEG)})
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/x.jpg",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO, "192.168.1.10"]}),
        transport=transport,
    )
    assert dados is None and chamadas == []


def test_dns_rebinding_nao_altera_o_destino_entre_validacao_e_conexao():
    """
    O resolvedor responde público na primeira consulta e privado na segunda.
    Como o IP é fixado após uma única resolução, a conexão vai ao público.
    """
    respostas = iter([[PUBLICO], ["10.0.0.5"]])

    def resolver(hostname):
        return next(respostas)

    transport, chamadas = _transporte({(PUBLICO, "/x.jpg"): httpx.Response(200, content=JPEG)})
    dados = baixar_foto_segura(
        "https://rebind.exemplo.com/x.jpg", resolver=resolver, transport=transport
    )
    assert dados == JPEG
    assert [c[0] for c in chamadas] == [PUBLICO]


def test_falha_de_dns_devolve_none_sem_requisicao():
    transport, chamadas = _transporte({})
    assert baixar_foto_segura(
        "https://inexistente.exemplo.com/x.jpg",
        resolver=_resolver({}),
        transport=transport,
    ) is None
    assert chamadas == []


# --- URLs inválidas ----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://cdn.exemplo.com.br/x.jpg",  # sem TLS
        "https:///x.jpg",  # sem hostname
        "https://cdn.exemplo.com.br:8443/x.jpg",  # porta fora do 443
        "ftp://cdn.exemplo.com.br/x.jpg",
        "",
    ],
)
def test_url_invalida_nao_gera_requisicao(url):
    transport, chamadas = _transporte({})
    assert baixar_foto_segura(url, resolver=_resolver({}), transport=transport) is None
    assert chamadas == []


# --- conteúdo e tamanho ------------------------------------------------------


def test_conteudo_que_nao_e_imagem_e_descartado():
    transport, _ = _transporte({(PUBLICO, "/x"): httpx.Response(200, content=b"<html>")})
    assert baixar_foto_segura(
        "https://cdn.exemplo.com.br/x",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    ) is None


def test_imagem_maior_que_o_limite_e_descartada(monkeypatch):
    monkeypatch.setattr(url_seguras, "MAX_BYTES_FOTO", 1000)
    transport, _ = _transporte({(PUBLICO, "/x"): httpx.Response(200, content=JPEG + b"0" * 2000)})
    assert baixar_foto_segura(
        "https://cdn.exemplo.com.br/x",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    ) is None


# --- classificação de IP -----------------------------------------------------


@pytest.mark.parametrize(
    "ip,publico",
    [
        ("8.8.8.8", True),
        ("1.1.1.1", True),
        ("2606:4700:4700::1111", True),
        ("10.0.0.1", False),
        ("172.16.5.5", False),
        ("192.168.0.1", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),  # metadata na nuvem
        ("100.64.0.1", False),  # CGNAT
        ("0.0.0.0", False),
        ("224.0.0.1", False),  # multicast
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),  # ULA
        ("::ffff:10.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("não é ip", False),
    ],
)
def test_classificacao_de_ip(ip, publico):
    assert ip_publico(ip) is publico


# --- teto de bytes vale para o corpo que chega (não depois de descomprimir) ---


def test_foto_com_content_encoding_e_recusada_antes_de_bufferizar():
    transport, chamadas = _transporte(
        {
            (PUBLICO, "/foto.jpg"): httpx.Response(
                200, headers={"content-encoding": "gzip"}, content=gzip.compress(JPEG)
            )
        }
    )
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/foto.jpg",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    )
    assert dados is None
    assert chamadas, "a requisição foi feita"


def test_pedido_de_foto_pede_identidade_de_codificacao():
    cabecalhos = []

    def handler(request: httpx.Request) -> httpx.Response:
        cabecalhos.append(request.headers.get("accept-encoding"))
        return httpx.Response(200, content=JPEG)

    baixar_foto_segura(
        "https://cdn.exemplo.com.br/foto.jpg",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=httpx.MockTransport(handler),
    )
    assert cabecalhos == ["identity"]


def test_foto_com_content_length_acima_do_teto_e_recusada():
    grande = str(url_seguras.MAX_BYTES_FOTO + 1)
    transport, _ = _transporte(
        {
            (PUBLICO, "/foto.jpg"): httpx.Response(
                200, headers={"content-length": grande}, content=JPEG
            )
        }
    )
    dados = baixar_foto_segura(
        "https://cdn.exemplo.com.br/foto.jpg",
        resolver=_resolver({"cdn.exemplo.com.br": [PUBLICO]}),
        transport=transport,
    )
    assert dados is None
