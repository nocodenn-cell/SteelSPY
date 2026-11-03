"""
Fila de retentativa quando o XML não está disponível (NFe.io / SEFAZ).
Reivindicação com FOR UPDATE SKIP LOCKED + status processando (evita dois workers na mesma NF).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DELAYS_MINUTOS = (5, 15, 30)


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def enfileirar_apos_falha_xml(
    db: Session,
    *,
    obra_id: UUID,
    chave_acesso: str,
    ultimo_erro: str | None = None,
) -> dict[str, Any]:
    chave = chave_acesso[:44]
    proxima = agora_utc() + timedelta(minutes=DELAYS_MINUTOS[0])
    sql = text("""
        INSERT INTO fila_nfe (obra_id, chave_acesso, tentativas, proxima_tentativa, status, ultimo_erro)
        VALUES (:obra_id, :chave, 0, :proxima, 'pendente', :erro)
        ON CONFLICT (obra_id, chave_acesso) DO UPDATE SET
            ultimo_erro = EXCLUDED.ultimo_erro,
            proxima_tentativa = EXCLUDED.proxima_tentativa,
            tentativas = 0,
            status = 'pendente',
            notificado_aguardando = FALSE,
            updated_at = NOW()
        RETURNING id, tentativas, proxima_tentativa, notificado_aguardando
    """)
    row = db.execute(
        sql,
        {"obra_id": str(obra_id), "chave": chave, "proxima": proxima, "erro": ultimo_erro},
    ).mappings().first()
    db.commit()
    return dict(row) if row else {}


def marcar_notificado_aguardando(db: Session, fila_id: UUID) -> None:
    db.execute(
        text("UPDATE fila_nfe SET notificado_aguardando = TRUE, updated_at = NOW() WHERE id = :id"),
        {"id": str(fila_id)},
    )
    db.commit()


def _reivindicar_lote_fila(db: Session, limite: int = 50) -> list[Any]:
    """
    Atomically: seleciona linhas elegíveis com SKIP LOCKED e marca como processando.
    Retorna linhas para trabalho fora do lock prolongado (commit libera bloqueio).
    """
    rows = db.execute(
        text("""
            WITH candidatos AS (
                SELECT id
                FROM fila_nfe
                WHERE status = 'pendente' AND proxima_tentativa <= NOW()
                ORDER BY proxima_tentativa
                FOR UPDATE SKIP LOCKED
                LIMIT :limite
            )
            UPDATE fila_nfe AS f
            SET status = 'processando', updated_at = NOW()
            FROM candidatos AS c
            WHERE f.id = c.id
            RETURNING f.id, f.obra_id, f.chave_acesso, f.tentativas, f.notificado_aguardando
        """),
        {"limite": limite},
    ).mappings().all()
    db.commit()
    return list(rows)


def processar_tick_fila(
    db: Session,
    *,
    buscar_xml: Callable[[str], dict[str, Any] | None],
    ao_sucesso: Callable[[Session, UUID, str, dict[str, Any]], None] | None = None,
    notificar_aguardando: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    resultados: list[dict[str, Any]] = []
    claimed = _reivindicar_lote_fila(db)

    for row in claimed:
        fid = UUID(str(row["id"]))
        obra_id = UUID(str(row["obra_id"]))
        chave = str(row["chave_acesso"])
        tentativas = int(row["tentativas"])
        notificado = bool(row["notificado_aguardando"])

        if not notificado and notificar_aguardando:
            try:
                notificar_aguardando(str(obra_id), chave)
            except Exception as e:  # noqa: BLE001
                logger.warning("Falha ao notificar aguardando: %s", e)
            marcar_notificado_aguardando(db, fid)

        xml_data = buscar_xml(chave)
        if xml_data is not None:
            try:
                if ao_sucesso:
                    ao_sucesso(db, obra_id, chave, xml_data)
                db.execute(
                    text("UPDATE fila_nfe SET status = 'processado', updated_at = NOW() WHERE id = :id"),
                    {"id": str(fid)},
                )
                db.commit()
            except Exception as e:  # noqa: BLE001
                logger.exception("Falha ao persistir conferência após XML (fila id=%s): %s", fid, e)
                db.rollback()
                db.execute(
                    text("""
                        UPDATE fila_nfe
                        SET status = 'pendente',
                            ultimo_erro = :erro,
                            proxima_tentativa = NOW() + INTERVAL '2 minutes',
                            updated_at = NOW()
                        WHERE id = :id
                    """),
                    {"id": str(fid), "erro": f"erro ao gravar conferência: {e!s}"[:2000]},
                )
                db.commit()
                resultados.append(
                    {"id": str(fid), "chave_acesso": chave, "resultado": "erro_gravacao", "detalhe": str(e)}
                )
                continue
            resultados.append({"id": str(fid), "chave_acesso": chave, "resultado": "processado"})
            continue

        nova_tentativa = tentativas + 1
        if nova_tentativa >= 3:
            db.execute(
                text("""
                    UPDATE fila_nfe
                    SET status = 'falha',
                        tentativas = :t,
                        ultimo_erro = 'XML não disponível após 3 retentativas',
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": str(fid), "t": nova_tentativa},
            )
            db.commit()
            resultados.append({"id": str(fid), "chave_acesso": chave, "resultado": "falha"})
            continue

        proxima = agora_utc() + timedelta(minutes=DELAYS_MINUTOS[nova_tentativa])
        db.execute(
            text("""
                UPDATE fila_nfe
                SET status = 'pendente',
                    tentativas = :t,
                    proxima_tentativa = :proxima,
                    ultimo_erro = 'XML indisponível na API',
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": str(fid), "t": nova_tentativa, "proxima": proxima},
        )
        db.commit()
        resultados.append(
            {
                "id": str(fid),
                "chave_acesso": chave,
                "resultado": "reagendado",
                "proxima_tentativa": proxima.isoformat(),
                "tentativas": nova_tentativa,
            }
        )

    return resultados
