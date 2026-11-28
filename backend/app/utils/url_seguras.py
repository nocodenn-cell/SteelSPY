"""
Validação de URLs usadas pelo servidor (evita SSRF no download de foto_url).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx


class URLNaoPermitidaError(ValueError):
    """URL rejeitada por política de segurança."""


_CGNAT_IPV4 = ipaddress.ip_network("100.64.0.0/10")


def _host_literais_e_metadata(hostname: str) -> bool:
    h = hostname.lower().rstrip(".")
    if h in ("localhost", "0.0.0.0", "metadata", "metadata.google.internal"):
        return False
    if h.endswith(".localhost") or h.endswith(".local") or h.endswith(".internal"):
        return False
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
        # B9: CGNAT (100.64.0.0/10) não é "private" para ipaddress, mas não é público.
        if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_IPV4:
            return False
        if ip == ipaddress.ip_address("169.254.169.254"):
            return False
    except ValueError:
        pass
    return True


def validar_url_imagem_publica(url: str | None) -> str | None:
    """
    foto_url: apenas HTTPS, host não óbvio de SSRF.
    Opcional: FOTO_URL_ALLOWED_HOSTS=host1,host2 restringe a uma lista explícita.
    """
    if url is None:
        return None
    raw = str(url).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        raise URLNaoPermitidaError("foto_url deve usar HTTPS.")
    host = parsed.hostname
    if not host:
        raise URLNaoPermitidaError("foto_url com hostname inválido.")
    try:
        porta = parsed.port
    except ValueError as exc:  # porta não numérica ou fora de 0-65535
        raise URLNaoPermitidaError("foto_url com porta inválida.") from exc
    if porta not in (None, 443):
        raise URLNaoPermitidaError("foto_url só pode usar a porta 443.")

    allow = (os.getenv("FOTO_URL_ALLOWED_HOSTS") or "").strip()
    if allow:
        permitidos = {x.strip().lower() for x in allow.split(",") if x.strip()}
        if host.lower() not in permitidos:
            raise URLNaoPermitidaError("host da foto_url não está na lista FOTO_URL_ALLOWED_HOSTS.")
    elif not _host_literais_e_metadata(host):
        raise URLNaoPermitidaError("host da foto_url não permitido (rede local / metadata bloqueados).")

    return raw


# ---------------------------------------------------------------------------
# Download seguro de foto_url (P-07)
# ---------------------------------------------------------------------------
#
# Por que existe
# --------------
# `httpx.get(..., follow_redirects=True)` seguia redirects sem revalidar nada:
# uma foto_url pública podia responder 302 para http://10.0.0.5/ ou para
# http://169.254.169.254/ (metadata da nuvem). A validação de host era só
# literal: um nome como `evil.com` que resolve para 127.0.0.1 passava.
#
# Regras aplicadas em CADA salto:
#   1. esquema https e porta 443 (validar_url_imagem_publica + checagem de porta);
#   2. o hostname é resolvido e TODOS os endereços devem ser públicos
#      (uma resposta mista já é recusada);
#   3. a conexão vai para o IP validado, não para o nome. Assim a resposta
#      DNS não pode mudar entre a checagem e o connect (DNS rebinding).
#      SNI e Host continuam sendo o hostname, então o certificado é verificado;
#   4. redirects são seguidos manualmente, com no máximo MAX_REDIRECTS_FOTO;
#   5. proxy do ambiente é ignorado (trust_env=False): um proxy resolveria o
#      nome por conta própria e anularia a fixação do IP.

MAX_REDIRECTS_FOTO = 3
MAX_BYTES_FOTO = 10 * 1024 * 1024
_STATUS_REDIRECT = {301, 302, 303, 307, 308}
_MAGIC_IMAGEM = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8")

Resolver = Callable[[str], list[str]]


def _resolver_dns(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def ip_publico(endereco: str) -> bool:
    """True só para endereço roteável na internet pública."""
    try:
        ip = ipaddress.ip_address(endereco.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_unspecified or ip.is_multicast:
        return False
    # is_global cobre privado, loopback, link-local, reservado, CGNAT (100.64/10),
    # documentação e os demais blocos que não são roteáveis publicamente.
    return ip.is_global


def _escolher_ip_publico(hostname: str, resolver: Resolver) -> str:
    try:
        enderecos = resolver(hostname)
    except OSError as e:
        raise URLNaoPermitidaError(f"hostname da foto_url não resolve: {e}") from e
    if not enderecos:
        raise URLNaoPermitidaError("hostname da foto_url sem endereços.")
    if not all(ip_publico(a) for a in enderecos):
        raise URLNaoPermitidaError("hostname da foto_url resolve para endereço não público.")
    return enderecos[0]


def _validar_salto(url: str, resolver: Resolver) -> tuple[str, str]:
    """Valida um salto. Devolve (hostname, ip_fixado)."""
    validar_url_imagem_publica(url)
    parsed = urlparse(url.strip())
    if parsed.port not in (None, 443):
        raise URLNaoPermitidaError("foto_url só pode usar a porta 443.")
    host = parsed.hostname or ""
    ip = _escolher_ip_publico(host, resolver)
    return host, ip


def baixar_foto_segura(
    url: str,
    *,
    timeout: float = 15.0,
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
) -> bytes | None:
    """
    Baixa a imagem da foto_url aplicando as regras de salto acima.

    Devolve os bytes da imagem (JPEG/PNG/GIF) ou None. Não levanta por destino
    recusado nem por falha de rede: o laudo segue sem foto, como antes.
    """
    resolver = resolver or _resolver_dns
    atual = url
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
            transport=transport,
        ) as cli:
            for _ in range(MAX_REDIRECTS_FOTO + 1):
                try:
                    host, ip = _validar_salto(atual, resolver)
                except URLNaoPermitidaError:
                    return None
                parsed = urlparse(atual.strip())
                ip_url = f"[{ip}]" if ":" in ip else ip
                alvo = parsed._replace(netloc=ip_url).geturl()
                with cli.stream(
                    "GET",
                    alvo,
                    # identity: o teto de 10 MB vale para o corpo que chega, não para
                    # um corpo comprimido que se expande depois de bufferizado.
                    headers={"Host": host, "Accept-Encoding": "identity"},
                    extensions={"sni_hostname": host},
                ) as r:
                    if r.status_code in _STATUS_REDIRECT:
                        destino = r.headers.get("location")
                        if not destino:
                            return None
                        atual = urljoin(atual, destino)
                        continue
                    if r.status_code != 200:
                        return None
                    codificacao = (r.headers.get("content-encoding") or "identity").strip().lower()
                    if codificacao != "identity":
                        return None
                    tamanho = r.headers.get("content-length")
                    if tamanho is not None and (not tamanho.isdigit() or int(tamanho) > MAX_BYTES_FOTO):
                        return None
                    corpo = bytearray()
                    for trecho in r.iter_bytes():
                        corpo.extend(trecho)
                        if len(corpo) > MAX_BYTES_FOTO:
                            return None
                    dados = bytes(corpo)
                    return dados if dados.startswith(_MAGIC_IMAGEM) else None
            return None  # excedeu MAX_REDIRECTS_FOTO
    except httpx.HTTPError:
        return None
