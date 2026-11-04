"""Abstração de armazenamento de evidências.

O resto do sistema conhece apenas a porta `BackendArmazenamento`. Disco local e
Supabase Storage são implementações da mesma porta — nada acima muda.

Regras que esta camada garante:

- **chave opaca**: quem chama passa uma chave relativa; o caminho absoluto nunca
  aparece em resposta HTTP nem em log;
- **confinamento**: uma chave que tente escapar da raiz (`../`, caminho absoluto)
  é rejeitada, não normalizada em silêncio;
- **escrita atômica**: grava em arquivo temporário e renomeia, para nunca deixar
  objeto pela metade se o processo morrer no meio;
- **imutabilidade na prática**: gravar sobre chave existente falha, em vez de
  sobrescrever uma prova;
- **bucket privado**: no Supabase a service role fica só no servidor; nenhum
  objeto é público e nenhuma chave é exposta ao cliente.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlparse

import httpx


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


def validar_chave(chave: str) -> str:
    """Rejeita chave vazia, absoluta, com drive ou com segmento de escape."""
    if not chave or chave.startswith(("/", "\\")) or ":" in chave:
        raise ChaveInvalida("chave de armazenamento inválida")
    segmentos = chave.replace("\\", "/").split("/")
    if any(segmento in ("", ".", "..") for segmento in segmentos):
        raise ChaveInvalida("chave de armazenamento inválida")
    return chave


class ArmazenamentoLocal:
    """Disco local, isolado por diretório. Suficiente para desenvolvimento e testes."""

    def __init__(self, raiz: Path | str) -> None:
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _caminho(self, chave: str) -> Path:
        validar_chave(chave)
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


_TIPOS_POR_EXTENSAO = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _tipo_conteudo(chave: str) -> str:
    return _TIPOS_POR_EXTENSAO.get(Path(chave).suffix.lower(), "application/octet-stream")


def _ausente(resposta: httpx.Response) -> bool:
    """Supabase devolve 400 com `not_found` (não só 404) para objeto inexistente."""
    if resposta.status_code == 404:
        return True
    if resposta.status_code != 400:
        return False
    corpo = resposta.content[:300].lower()
    return b"not_found" in corpo or b"not found" in corpo


class ArmazenamentoSupabase:
    """Storage do Supabase, bucket privado, acesso exclusivo do servidor.

    A service role nunca vai ao cliente: todas as leituras passam pela API, que
    já aplicou RLS e autorização por obra. O caminho começa pelo `tenant_id`,
    então o objeto também é auditável por construtora no bucket.
    """

    def __init__(
        self,
        url: str,
        service_key: str,
        bucket: str,
        *,
        cliente: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        base = (url or "").strip().rstrip("/")
        if not base or not service_key or not bucket:
            raise ErroArmazenamento(
                "Storage do Supabase incompleto: defina SUPABASE_URL, "
                "SUPABASE_SERVICE_ROLE_KEY e EVIDENCIAS_BUCKET"
            )
        host = (urlparse(base).hostname or "").lower()
        esquema = urlparse(base).scheme
        if esquema != "https" and not (esquema == "http" and host in {"127.0.0.1", "localhost"}):
            raise ErroArmazenamento("SUPABASE_URL precisa ser https (http só em loopback)")
        if any(caractere.isspace() or caractere in "/\\" for caractere in bucket):
            raise ErroArmazenamento("EVIDENCIAS_BUCKET inválido")

        self.bucket = bucket
        self._base = f"{base}/storage/v1"
        self._chave = service_key
        self._cliente = cliente or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=5.0)
        )
        self._fechar_cliente = cliente is None

    def _url(self, chave: str) -> str:
        return f"{self._base}/object/{self.bucket}/{quote(chave, safe='/')}"

    def _headers(self, *, tipo: str | None = None, upsert: bool = False) -> dict[str, str]:
        cabecalhos = {
            "Authorization": f"Bearer {self._chave}",
            "apikey": self._chave,
        }
        if tipo:
            cabecalhos["Content-Type"] = tipo
        if upsert:
            cabecalhos["x-upsert"] = "true"
        return cabecalhos

    def gravar(self, chave: str, dados: bytes) -> None:
        validar_chave(chave)
        try:
            resposta = self._cliente.post(
                self._url(chave),
                content=dados,
                headers={**self._headers(tipo=_tipo_conteudo(chave)), "x-upsert": "false"},
            )
        except httpx.RequestError as exc:
            raise ErroArmazenamento(f"falha ao gravar objeto: {exc}") from exc

        if resposta.status_code in (200, 201):
            return
        corpo = resposta.content[:200].lower()
        if resposta.status_code in (400, 409) and (
            b"duplicate" in corpo or b"already exists" in corpo
        ):
            raise ChaveJaExiste(f"objeto já existe: {chave}")
        raise ErroArmazenamento(f"falha ao gravar objeto (HTTP {resposta.status_code})")

    def ler(self, chave: str) -> bytes:
        validar_chave(chave)
        try:
            resposta = self._cliente.get(self._url(chave), headers=self._headers())
        except httpx.RequestError as exc:
            raise ErroArmazenamento(f"falha ao ler objeto: {exc}") from exc
        if resposta.status_code == 200:
            return resposta.content
        if _ausente(resposta):
            raise ErroArmazenamento("objeto não encontrado no armazenamento")
        raise ErroArmazenamento(f"falha ao ler objeto (HTTP {resposta.status_code})")

    def existe(self, chave: str) -> bool:
        validar_chave(chave)
        try:
            resposta = self._cliente.head(self._url(chave), headers=self._headers())
        except httpx.RequestError as exc:
            raise ErroArmazenamento(f"falha ao consultar objeto: {exc}") from exc
        if resposta.status_code == 200:
            return True
        # HEAD não tem corpo: o Storage responde 400 (não 404) para objeto
        # inexistente, e 401/403 quando a credencial é o problema.
        if resposta.status_code in (400, 404):
            return False
        raise ErroArmazenamento(f"falha ao consultar objeto (HTTP {resposta.status_code})")

    def remover(self, chave: str) -> None:
        validar_chave(chave)
        try:
            resposta = self._cliente.delete(self._url(chave), headers=self._headers())
        except httpx.RequestError as exc:
            raise ErroArmazenamento(f"falha ao remover objeto: {exc}") from exc
        # Ausente é sucesso: a intenção "não existir mais" já está satisfeita.
        if resposta.status_code in (200, 204) or _ausente(resposta):
            return
        raise ErroArmazenamento(f"falha ao remover objeto (HTTP {resposta.status_code})")

    def fechar(self) -> None:
        if self._fechar_cliente:
            self._cliente.close()


def raiz_padrao() -> Path:
    """Diretório padrão de evidências: `backend/var/evidencias` (fora do Git)."""
    configurado = (os.getenv("EVIDENCIAS_DIR") or "").strip()
    if configurado:
        return Path(configurado)
    return Path(__file__).resolve().parents[2] / "var" / "evidencias"


_BACKEND: BackendArmazenamento | None = None


def backend() -> BackendArmazenamento:
    """Backend em uso. Preguiçoso e substituível em teste via `definir_backend`.

    `EVIDENCIAS_STORAGE` escolhe explicitamente `local` (padrão) ou `supabase`.
    A escolha é explícita de propósito: inferir pelo ambiente faria uma máquina
    de desenvolvimento com Supabase configurado gravar provas no projeto remoto
    sem ninguém pedir.
    """
    global _BACKEND
    if _BACKEND is None:
        modo = (os.getenv("EVIDENCIAS_STORAGE") or "local").strip().lower()
        if modo == "local":
            _BACKEND = ArmazenamentoLocal(raiz_padrao())
        elif modo == "supabase":
            _BACKEND = ArmazenamentoSupabase(
                os.getenv("SUPABASE_URL", ""),
                os.getenv("SUPABASE_SERVICE_ROLE_KEY")
                or os.getenv("SUPABASE_SERVICE_KEY")
                or "",
                os.getenv("EVIDENCIAS_BUCKET", "evidencias"),
            )
        else:
            raise ErroArmazenamento(
                f"EVIDENCIAS_STORAGE inválido: {modo!r} (use 'local' ou 'supabase')"
            )
    return _BACKEND


def definir_backend(novo: BackendArmazenamento | None) -> None:
    """Injeta outro backend (usado nos testes e, no futuro, por object storage)."""
    global _BACKEND
    _BACKEND = novo
