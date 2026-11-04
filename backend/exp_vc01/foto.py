"""Entrada de fotografia do protótipo — reusa a validação que já existe no produto.

O SteelSPY já sabe validar assinatura de arquivo, decodificar, rejeitar imagem
corrompida, limitar pixels, normalizar e calcular os dois hashes. Reimplementar
isso aqui seria duplicar justamente a camada que o brief manda não tocar, e o
experimento passaria a rodar sobre uma foto que a produção aceitaria de outro
jeito. Daí `app.services.evidencias` ser a única porta de entrada.

Nada aqui escreve no banco nem no armazenamento de evidências: o protótipo é
isolado por construção.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.evidencias import (
    ErroEvidencia,
    normalizar_imagem,
    sha256,
)


@dataclass(frozen=True)
class Fotografia:
    """A foto como chegou e como o detector a vê, cada uma com seu hash.

    Os dois hashes vão no laudo porque a contagem precisa ser amarrável ao
    arquivo que o humano tem na mão — mesma razão que fez o dossiê citar os dois.
    """

    original: bytes
    normalizada: bytes
    sha256_original: str
    sha256_normalizada: str
    largura: int
    altura: int
    mime: str
    origem: str

    def cabecalho(self) -> dict[str, Any]:
        return {
            "origem": self.origem,
            "mime_original": self.mime,
            "sha256_original": self.sha256_original,
            "sha256_normalizada": self.sha256_normalizada,
            "bytes_original": len(self.original),
            "bytes_normalizada": len(self.normalizada),
            "largura": self.largura,
            "altura": self.altura,
        }


def de_bytes(conteudo: bytes, mime_declarado: str | None = None, origem: str = "upload") -> Fotografia:
    normalizada = normalizar_imagem(conteudo, mime_declarado)
    return Fotografia(
        original=conteudo,
        normalizada=normalizada["conteudo"],
        sha256_original=sha256(conteudo),
        sha256_normalizada=sha256(normalizada["conteudo"]),
        largura=normalizada["largura"],
        altura=normalizada["altura"],
        mime=normalizada["mime_original"],
        origem=origem,
    )


def de_arquivo(caminho: str | Path) -> Fotografia:
    p = Path(caminho)
    dados = p.read_bytes()
    try:
        return de_bytes(dados, origem=str(p))
    except ErroEvidencia as exc:
        raise ErroEvidencia(f"{p.name}: {exc.detail}", status_code=exc.status_code) from exc
