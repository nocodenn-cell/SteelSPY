"""Serviço de evidências: validar, normalizar, armazenar, recuperar.

A ordem importa e é o que torna a operação recuperável:

1. calcula hash do que chegou (prova do original);
2. valida a assinatura real do arquivo (não confia no Content-Type);
3. decodifica e normaliza (gera segundo artefato, com hash próprio);
4. grava os dois objetos no armazenamento;
5. só então grava a linha no banco e a trilha de eventos.

Se o passo 4 falhar no meio, os objetos já gravados são removidos e a exceção
sobe como 503. Se o passo 5 falhar, os objetos ficam órfãos — situação
detectável e inofensiva, preferível a uma linha apontando para arquivo
inexistente.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.armazenamento import (
    ErroArmazenamento,
    backend as backend_padrao,
)

logger = logging.getLogger(__name__)

LIMITE_BYTES_PADRAO = 12 * 1024 * 1024
MAX_LADO_PADRAO = 4096
MAX_PIXELS = 50_000_000
QUALIDADE_JPEG = 85

# Assinatura real do arquivo. Extensão e Content-Type são fáceis de mentir;
# os primeiros bytes, não.
_ASSINATURAS: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)

_MIMES_ACEITOS = {"image/jpeg", "image/png", "image/webp"}


class ErroEvidencia(Exception):
    """Erro de negócio da evidência. Carrega o status HTTP adequado."""

    def __init__(self, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def limite_bytes() -> int:
    bruto = (os.getenv("EVIDENCIA_MAX_BYTES") or "").strip()
    if bruto.isdigit():
        return max(1024, int(bruto))
    return LIMITE_BYTES_PADRAO


def max_lado() -> int:
    bruto = (os.getenv("EVIDENCIA_MAX_LADO") or "").strip()
    if bruto.isdigit():
        return max(256, min(int(bruto), 8192))
    return MAX_LADO_PADRAO


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def detectar_tipo(conteudo: bytes) -> tuple[str, str] | None:
    """Retorna (mime, extensão) pela assinatura, ou None se não for suportado."""
    for assinatura, mime, ext in _ASSINATURAS:
        if conteudo.startswith(assinatura):
            return mime, ext
    # WEBP: "RIFF" + 4 bytes de tamanho + "WEBP"
    if len(conteudo) >= 12 and conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def normalizar_imagem(conteudo: bytes, mime_declarado: str | None) -> dict[str, Any]:
    """
    Valida assinatura, decodifica e normaliza para JPEG sem EXIF.

    Levanta `ErroEvidencia` com status adequado:
    - 400 assinatura ausente/divergente do que foi declarado;
    - 422 imagem corrompida ou grande demais em pixels.
    """
    detectado = detectar_tipo(conteudo)
    if detectado is None:
        raise ErroEvidencia(
            "Formato não suportado. Envie JPEG, PNG ou WEBP.", status_code=415
        )
    mime_real, ext_real = detectado

    declarado = (mime_declarado or "").split(";")[0].strip().lower()
    if declarado and declarado in _MIMES_ACEITOS and declarado != mime_real:
        raise ErroEvidencia(
            f"Conteúdo não corresponde ao tipo declarado ({declarado} != {mime_real}).",
            status_code=400,
        )

    try:
        with Image.open(io.BytesIO(conteudo)) as img:
            img.load()
            largura, altura = img.size
            if largura * altura > MAX_PIXELS:
                raise ErroEvidencia(
                    f"Imagem grande demais ({largura}x{altura}). Máximo de {MAX_PIXELS} pixels.",
                    status_code=422,
                )
            convertida = img.convert("RGB") if img.mode not in ("RGB", "L") else img.copy()
    except ErroEvidencia:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ErroEvidencia(f"Imagem inválida ou corrompida: {exc}", status_code=422) from exc

    lado = max_lado()
    convertida.thumbnail((lado, lado), Image.LANCZOS)
    saida = io.BytesIO()
    # Sem parâmetro exif: o Pillow não escreve metadados a partir de um objeto novo.
    convertida.save(saida, format="JPEG", quality=QUALIDADE_JPEG, optimize=True)

    return {
        "conteudo": saida.getvalue(),
        "mime": "image/jpeg",
        "ext": "jpg",
        "largura": convertida.width,
        "altura": convertida.height,
        "mime_original": mime_real,
        "ext_original": ext_real,
    }


def _chaves(tenant_id: UUID, obra_id: UUID, evidencia_id: UUID, ext_original: str) -> tuple[str, str]:
    base = f"{tenant_id}/{obra_id}/{evidencia_id}"
    return f"{base}/original.{ext_original}", f"{base}/normalizada.jpg"


def _serializar(linha: Any) -> dict[str, Any]:
    """Converte a linha em dicionário de API — sem chaves de armazenamento."""
    return {
        "id": str(linha["id"]),
        "obra_id": str(linha["obra_id"]),
        "recebimento_id": str(linha["recebimento_id"]) if linha["recebimento_id"] else None,
        "sha256": linha["sha256"],
        "sha256_original": linha["sha256_original"],
        "mime": linha["mime"],
        "bytes": linha["bytes"],
        "bytes_original": linha["bytes_original"],
        "largura": linha["largura"],
        "altura": linha["altura"],
        "origem": linha["origem"],
        "tipo": linha["tipo"],
        "capturada_em": linha["capturada_em"].isoformat() if linha["capturada_em"] else None,
        "recebida_em": linha["recebida_em"].isoformat(),
        # Sinal antifraude: a imagem já existia na obra em outro contexto.
        "reutilizada_de": str(linha["reutilizada_de"]) if linha["reutilizada_de"] else None,
        "sinalizacao_fraude": bool(linha["sinalizacao_fraude"]),
    }


def _registrar_evento(
    db: Session,
    *,
    tenant_id: UUID,
    evidencia_id: UUID,
    tipo: str,
    detalhe: dict[str, Any] | None = None,
    autor_id: UUID | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO evidencia_eventos (tenant_id, evidencia_id, tipo, detalhe, autor_id)
            VALUES (:t, :e, :tipo, CAST(:det AS jsonb), :autor)
        """),
        {
            "t": str(tenant_id),
            "e": str(evidencia_id),
            "tipo": tipo,
            "det": _json(detalhe or {}),
            "autor": str(autor_id) if autor_id else None,
        },
    )


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)


def criar_evidencia(
    db: Session,
    *,
    tenant_id: UUID,
    obra_id: UUID,
    recebimento_id: UUID | None,
    conteudo: bytes,
    mime_declarado: str | None,
    origem: str,
    tipo: str,
    capturada_em: datetime | None,
    usuario_id: UUID | None,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    Grava a evidência. Devolve `(evidencia, criada)`.

    Três identidades, três mecanismos — e é isso que evita confundir "retry"
    com "reuso indevido":

    - `idempotency_key` identifica a **operação** de upload. Mesma chave, mesma
      resposta, sem gravar de novo;
    - `sha256` identifica o **arquivo**. É o que prova que a foto é a mesma;
    - `(recebimento_id, sha256)` identifica a **prova de um recebimento**.

    A mesma imagem em recebimentos diferentes é permitida — o fiscal pode
    fotografar o mesmo material duas vezes — mas fica marcada: `reutilizada_de`
    aponta para a primeira ocorrência e `sinalizacao_fraude` vira verdadeiro.
    O sistema não bloqueia; ele mostra para quem decide.
    """
    if not conteudo:
        raise ErroEvidencia("Arquivo vazio.", status_code=400)

    limite = limite_bytes()
    if len(conteudo) > limite:
        raise ErroEvidencia(
            f"Arquivo acima do limite de {limite // (1024 * 1024)} MB.", status_code=413
        )

    chave_idem = (idempotency_key or "").strip() or None
    if chave_idem:
        existente = db.execute(
            text("""
                SELECT * FROM evidencias
                WHERE obra_id = :obra AND idempotency_key = :chave AND removido_em IS NULL
            """),
            {"obra": str(obra_id), "chave": chave_idem},
        ).mappings().first()
        if existente is not None:
            logger.info("upload idempotente por chave: evidência %s", existente["id"])
            return _serializar(existente), False

    sha_original = sha256(conteudo)
    normalizada = normalizar_imagem(conteudo, mime_declarado)
    sha_norm = sha256(normalizada["conteudo"])

    # Mesma prova para o mesmo recebimento: é retry, não erro.
    if recebimento_id is not None:
        repetida = db.execute(
            text("""
                SELECT * FROM evidencias
                WHERE recebimento_id = :rec AND sha256 = :sha AND removido_em IS NULL
            """),
            {"rec": str(recebimento_id), "sha": sha_norm},
        ).mappings().first()
        if repetida is not None:
            logger.info("upload idempotente no recebimento: evidência %s", repetida["id"])
            return _serializar(repetida), False

    # Sem recebimento e sem chave de operação: o mesmo arquivo na mesma obra é
    # retry de rede, não reutilização. Devolve o que já existe.
    if recebimento_id is None and chave_idem is None:
        repetida_solta = db.execute(
            text("""
                SELECT * FROM evidencias
                WHERE obra_id = :obra AND sha256 = :sha
                  AND recebimento_id IS NULL AND removido_em IS NULL
            """),
            {"obra": str(obra_id), "sha": sha_norm},
        ).mappings().first()
        if repetida_solta is not None:
            logger.info("upload idempotente (sem recebimento): %s", repetida_solta["id"])
            return _serializar(repetida_solta), False

    # Reutilização: este conteúdo já existe em outro ponto da obra?
    primeira = db.execute(
        text("""
            SELECT id FROM evidencias
            WHERE obra_id = :obra AND sha256 = :sha AND removido_em IS NULL
            ORDER BY recebida_em, id
            LIMIT 1
        """),
        {"obra": str(obra_id), "sha": sha_norm},
    ).scalar()

    reutilizada_de = str(primeira) if primeira else None
    sinalizada = primeira is not None

    evidencia_id = uuid4()
    chave_original, chave_norm = _chaves(
        tenant_id, obra_id, evidencia_id, normalizada["ext_original"]
    )

    armazenamento = backend_padrao()
    gravadas: list[str] = []
    try:
        armazenamento.gravar(chave_original, conteudo)
        gravadas.append(chave_original)
        armazenamento.gravar(chave_norm, normalizada["conteudo"])
        gravadas.append(chave_norm)
    except ErroArmazenamento as exc:
        for chave in gravadas:
            try:
                armazenamento.remover(chave)
            except ErroArmazenamento:  # pragma: no cover - melhor esforço
                logger.warning("não foi possível limpar objeto órfão %s", chave)
        raise ErroEvidencia(
            "Armazenamento indisponível. Tente novamente em instantes.", status_code=503
        ) from exc

    try:
        db.execute(
            text("""
                INSERT INTO evidencias (
                    id, tenant_id, obra_id, recebimento_id,
                    sha256_original, sha256,
                    storage_key_original, storage_key,
                    mime_original, mime, bytes_original, bytes,
                    largura, altura, origem, tipo, capturada_em, criado_por,
                    idempotency_key, reutilizada_de, sinalizacao_fraude
                ) VALUES (
                    :id, :tenant, :obra, :rec,
                    :sha_orig, :sha,
                    :key_orig, :key,
                    :mime_orig, :mime, :bytes_orig, :bytes,
                    :largura, :altura, :origem, :tipo, :capturada, :autor,
                    :chave_idem, :reutilizada_de, :sinalizada
                )
            """),
            {
                "id": str(evidencia_id),
                "tenant": str(tenant_id),
                "obra": str(obra_id),
                "rec": str(recebimento_id) if recebimento_id else None,
                "sha_orig": sha_original,
                "sha": sha_norm,
                "key_orig": chave_original,
                "key": chave_norm,
                "mime_orig": normalizada["mime_original"],
                "mime": normalizada["mime"],
                "bytes_orig": len(conteudo),
                "bytes": len(normalizada["conteudo"]),
                "largura": normalizada["largura"],
                "altura": normalizada["altura"],
                "origem": origem,
                "tipo": tipo,
                "capturada": capturada_em,
                "autor": str(usuario_id) if usuario_id else None,
                "chave_idem": chave_idem,
                "reutilizada_de": reutilizada_de,
                "sinalizada": sinalizada,
            },
        )
    except IntegrityError:
        # Corrida entre dois uploads idênticos: o índice único resolveu por nós.
        db.rollback()
        for chave in gravadas:
            try:
                armazenamento.remover(chave)
            except ErroArmazenamento:  # pragma: no cover
                pass
        existente = None
        if chave_idem:
            existente = db.execute(
                text("""
                    SELECT * FROM evidencias
                    WHERE obra_id = :obra AND idempotency_key = :chave AND removido_em IS NULL
                """),
                {"obra": str(obra_id), "chave": chave_idem},
            ).mappings().first()
        if existente is None and recebimento_id is not None:
            existente = db.execute(
                text("""
                    SELECT * FROM evidencias
                    WHERE recebimento_id = :rec AND sha256 = :sha AND removido_em IS NULL
                """),
                {"rec": str(recebimento_id), "sha": sha_norm},
            ).mappings().first()
        if existente is None:
            raise
        return _serializar(existente), False

    _registrar_evento(
        db,
        tenant_id=tenant_id,
        evidencia_id=evidencia_id,
        tipo="recebida",
        detalhe={"sha256_original": sha_original, "bytes_original": len(conteudo)},
        autor_id=usuario_id,
    )
    _registrar_evento(
        db,
        tenant_id=tenant_id,
        evidencia_id=evidencia_id,
        tipo="armazenada",
        detalhe={"sha256": sha_norm, "bytes": len(normalizada["conteudo"])},
        autor_id=usuario_id,
    )
    db.commit()

    linha = db.execute(
        text("SELECT * FROM evidencias WHERE id = :id"), {"id": str(evidencia_id)}
    ).mappings().one()
    return _serializar(linha), True


def registrar_download(
    db: Session, *, tenant_id: UUID, evidencia_id: UUID, variante: str, usuario_id: UUID | None
) -> None:
    _registrar_evento(
        db,
        tenant_id=tenant_id,
        evidencia_id=evidencia_id,
        tipo="baixada",
        detalhe={"variante": variante},
        autor_id=usuario_id,
    )
    db.commit()
