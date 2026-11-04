"""Validação das origens exatas aceitas pelo CORS.

`CORS_ALLOW_ORIGINS` alimenta `allow_credentials=True`. Nesse modo, o curinga
`*` não significa "sem cookies": o Starlette passa a refletir a origem de quem
chamou, ou seja, qualquer site com a sessão da pessoa. Por isso a lista é
validada na inicialização — uma configuração ambígua derruba o processo em vez
de abrir a API.

Origem é `scheme://host[:port]`, sem caminho. Um valor com caminho nunca casa
com o cabeçalho `Origin` do navegador e produz um CORS quebrado de aparência
misteriosa; melhor recusar na largada.
"""

from __future__ import annotations

from urllib.parse import urlsplit

ESQUEMAS = frozenset({"http", "https"})


def origens_permitidas(valor: str | None) -> list[str]:
    """Devolve as origens normalizadas ou levanta `ValueError` na primeira inválida."""
    if not valor or not valor.strip():
        return []

    saida: list[str] = []
    for bruta in valor.split(","):
        item = bruta.strip()
        if not item:
            continue
        if item == "*":
            raise ValueError(
                "o curinga '*' é incompatível com allow_credentials=True; "
                "liste as origens exatas do PWA"
            )
        if item.lower() == "null":
            raise ValueError("a origem 'null' aceitaria qualquer documento local")

        partes = urlsplit(item)
        if partes.scheme.lower() not in ESQUEMAS:
            raise ValueError(f"origem sem http/https: {item!r}")
        if not partes.hostname:
            raise ValueError(f"origem sem host: {item!r}")
        if partes.username or partes.password:
            raise ValueError(f"origem não pode carregar credencial: {item!r}")
        if partes.query or partes.fragment:
            raise ValueError(f"origem não pode ter query nem fragmento: {item!r}")
        if partes.path not in ("", "/"):
            raise ValueError(f"origem não pode ter caminho: {item!r}")
        try:
            partes.port  # noqa: B018 — força a validação da porta
        except ValueError as exc:
            raise ValueError(f"porta inválida em {item!r}") from exc

        normalizada = f"{partes.scheme.lower()}://{partes.netloc.lower()}"
        if normalizada not in saida:
            saida.append(normalizada)

    return saida
