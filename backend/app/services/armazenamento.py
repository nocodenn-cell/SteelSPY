"""Abstração de armazenamento de evidências.

O resto do sistema conhece apenas a porta `BackendArmazenamento`. Trocar disco
local por object storage (Supabase, S3, R2) é implementar outra classe — nada
acima muda.

Regras que esta camada garante:

- **chave opaca**: quem chama passa uma chave relativa; o caminho absoluto nunca
  aparece em resposta HTTP nem em log;
- **confinamento**: uma chave que tente escapar da raiz (`../`, caminho absoluto)
  é rejeitada, não normalizada em silêncio;
- **escrita atômica**: grava em arquivo temporário e renomeia, para nunca deixar
  objeto pela metade se o processo morrer no meio;
- **imutabilidade na prática**: gravar sobre chave existente falha, em vez de
  sobrescrever uma prova.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol


class ErroArmazenamento(Exception):
    """Falha ao ler/gravar. Vira 503 na borda HTTP — nunca 500 com stack trace."""


class ChaveInvalida(ErroArmazenamento):
    """Chave que tentaria sair da raiz do armazenamento."""


class ChaveJaExiste(ErroArmazenamento):
    """Tentativa de sobrescrever um objeto existente (prova é imutável)."""


class BackendArmazenamento(Protocol):
    def gravar(self, chave: str, dados: bytes) -> None: ...
    def ler(self, chave: str) -> bytes: ...
    def existe(self, chave: str) -> bool: ...
    def remover(self, chave: str) -> None: ...


class ArmazenamentoLocal:
    """Disco local, isolado por diretório. Suficiente para desenvolvimento e testes."""

    def __init__(self, raiz: Path | str) -> None:
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _caminho(self, chave: str) -> Path:
        if not chave or chave.startswith(("/", "\\")) or ":" in chave:
            raise ChaveInvalida("chave de armazenamento inválida")
        destino = (self.raiz / chave).resolve()
        if not destino.is_relative_to(self.raiz):
            raise ChaveInvalida("chave de armazenamento fora da raiz")
        return destino

    def gravar(self, chave: str, dados: bytes) -> None:
        destino = self._caminho(chave)
        if destino.exists():
            raise ChaveJaExiste(f"objeto já existe: {chave}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".tmp")
        try:
            temporario.write_bytes(dados)
            os.replace(temporario, destino)
        except OSError as exc:
            temporario.unlink(missing_ok=True)
            raise ErroArmazenamento(f"falha ao gravar objeto: {exc}") from exc

    def ler(self, chave: str) -> bytes:
        destino = self._caminho(chave)
        try:
            return destino.read_bytes()
        except FileNotFoundError as exc:
            raise ErroArmazenamento("objeto não encontrado no armazenamento") from exc
        except OSError as exc:
            raise ErroArmazenamento(f"falha ao ler objeto: {exc}") from exc

    def existe(self, chave: str) -> bool:
        return self._caminho(chave).is_file()

    def remover(self, chave: str) -> None:
        destino = self._caminho(chave)
        try:
            destino.unlink(missing_ok=True)
        except OSError as exc:
            raise ErroArmazenamento(f"falha ao remover objeto: {exc}") from exc

    # Utilitário de teste/operação — nunca exposto por HTTP.
    def limpar(self) -> None:
        shutil.rmtree(self.raiz, ignore_errors=True)
        self.raiz.mkdir(parents=True, exist_ok=True)


def raiz_padrao() -> Path:
    """Diretório padrão de evidências: `backend/var/evidencias` (fora do Git)."""
    configurado = (os.getenv("EVIDENCIAS_DIR") or "").strip()
    if configurado:
        return Path(configurado)
    return Path(__file__).resolve().parents[2] / "var" / "evidencias"


_BACKEND: BackendArmazenamento | None = None


def backend() -> BackendArmazenamento:
    """Backend em uso. Preguiçoso e substituível em teste via `definir_backend`."""
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = ArmazenamentoLocal(raiz_padrao())
    return _BACKEND


def definir_backend(novo: BackendArmazenamento | None) -> None:
    """Injeta outro backend (usado nos testes e, no futuro, por object storage)."""
    global _BACKEND
    _BACKEND = novo
