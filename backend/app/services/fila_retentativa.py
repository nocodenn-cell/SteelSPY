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

from app.tenant import vincular_sessao

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
    tenant_id: UUID | None = None,
) -> dict[str, Any]:
    chave = chave_acesso[:44]
    proxima = agora_utc() + timedelta(minutes=DELAYS_MINUTOS[0])
    # O tenant é NOT NULL na fila. Preferimos o valor explícito; se não vier,
    # resolvemos pela obra — que só é visível se a sessão já estiver no contexto
    # do tenant correto.
    sql = text("""
        INSERT INTO fila_nfe (
            tenant_id, obra_id, chave_acesso, tentativas, proxima_tentativa, status, ultimo_erro
        )
        VALUES (
            COALESCE(CAST(:tenant AS uuid), (SELECT o.tenant_id FROM obras o WHERE o.id = CAST(:obra_id AS uuid))),
            :obra_id, :chave, 0, :proxima, 'pendente', :erro
        )
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
        {
            "tenant": str(tenant_id) if tenant_id else None,
            "obra_id": str(obra_id),
            "chave": chave,
            "proxima": proxima,
            "erro": ultimo_erro,
        },
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
    Claim atômico de trabalho entre tenants.

    Com RLS ligado em `fila_nfe`, um SELECT comum só enxergaria a fila do
    tenant da sessão — e o worker começa sem sessão de tenant. Por isso o claim
    inteiro (SKIP LOCKED + UPDATE + RETURNING) vive na função SECURITY DEFINER
    `fila_reivindicar_lote`, que devolve o `tenant_id` de cada linha. O worker
    abre o contexto por item e executa o resto sob RLS normalmente.
    """
    rows = db.execute(
        text("""
            SELECT id, tenant_id, obra_id, chave_acesso, tentativas, notificado_aguardando
            FROM fila_reivindicar_lote(:limite)
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

        # Abre o contexto do tenant dono desta linha. A partir daqui, toda
        # leitura/escrita em nfe_logs, nfe_itens e fila_nfe passa pelo RLS.
        vincular_sessao(db, row["tenant_id"])

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
