"""
Persistência da conferência (router e worker da fila compartilham o mesmo fluxo).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.conferente import ConfigObraConferente, conferir_nf_multiplos_itens
from app.services.mensagem_fiscal import gerar_mensagem_fiscal, resumo_global_texto_curto
from app.services.nfe_persistencia import substituir_itens_nfe
from app.services.whatsapp_evolution import notificar_mensagem_fiscal

logger = logging.getLogger(__name__)


def carregar_obra_por_id(db: Session, obra_id: UUID) -> dict[str, Any]:
    row = db.execute(
        text("""
            SELECT id, nome, cnpj_destinatario, aceita_similar, margem_tolerancia_float, modo_aprendizado,
                   api_key, whatsapp_destino
            FROM obras WHERE id = :id
        """),
        {"id": str(obra_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="obra não encontrada")
    return dict(row)


def carregar_especificacoes_obra(db: Session, obra_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, material_tipo, bitola_mm, marca_exigida, qtd_planejada_metros,
                   categoria_material, atributos_especificos,
                   quantidade_prevista, unidade_prevista
            FROM especificacoes
            WHERE obra_id = :obra
            ORDER BY created_at
        """),
        {"obra": str(obra_id)},
    ).mappings().all()
    return [dict(r) for r in rows]


def gravar_conferencia_com_xml(
    db: Session,
    *,
    obra_id: UUID,
    chave: str,
    payload: dict[str, Any],
    foto_url: str | None,
    tipo: str,
    nf_original_id: UUID | None,
) -> tuple[UUID | None, dict[str, Any]]:
    """
    Upsert em nfe_logs + linhas em nfe_itens. Não faz commit (caller decide transação).
    Retorna (nfe_log_id, dict resultado do conferente + mensagem_fiscal para notificação).
    """
    obra = carregar_obra_por_id(db, obra_id)
    especificacoes = carregar_especificacoes_obra(db, obra_id)
    itens = payload.get("itens") or []
    if not itens:
        raise HTTPException(status_code=422, detail="NF sem itens mapeáveis para conferência.")

    config = ConfigObraConferente(
        aceita_similar=bool(obra["aceita_similar"]),
        margem_tolerancia_float=float(obra["margem_tolerancia_float"]),
        modo_aprendizado=bool(obra["modo_aprendizado"]),
    )

    resultado = conferir_nf_multiplos_itens(itens, especificacoes, config)
    st = resultado["status"]
    resumo = resultado["resumo"]
    resumo_g = resumo_global_texto_curto(st, resumo)
    msg_fiscal = gerar_mensagem_fiscal(st, resumo, resultado["itens_processados"])

    payload_gravar = {**payload, **resultado}
    if foto_url:
        payload_gravar["foto_url"] = foto_url

    row = db.execute(
        text("""
            INSERT INTO nfe_logs (
                chave_acesso, obra_id, status_conferencia, xml_data, foto_url,
                resumo_global, itens_resumo, tipo, nf_original_id
            )
            VALUES (
                :chave, :obra, :status, CAST(:xml AS jsonb), :foto,
                :resumo_g, CAST(:itens_res AS jsonb), :tipo, :nf_orig
            )
            ON CONFLICT (obra_id, chave_acesso) DO UPDATE SET
                status_conferencia = EXCLUDED.status_conferencia,
                xml_data = EXCLUDED.xml_data,
                processado_em = NOW(),
                foto_url = COALESCE(EXCLUDED.foto_url, nfe_logs.foto_url),
                resumo_global = EXCLUDED.resumo_global,
                itens_resumo = EXCLUDED.itens_resumo,
                tipo = EXCLUDED.tipo,
                nf_original_id = COALESCE(EXCLUDED.nf_original_id, nfe_logs.nf_original_id),
                laudo_pdf_url = NULL,
                laudo_pdf_gerado_em = NULL
            RETURNING id
        """),
        {
            "chave": chave,
            "obra": str(obra_id),
            "status": st,
            "xml": json.dumps(payload_gravar),
            "foto": foto_url,
            "resumo_g": resumo_g,
            "itens_res": json.dumps(resumo),
            "tipo": tipo,
            "nf_orig": str(nf_original_id) if nf_original_id else None,
        },
    ).mappings().first()

    nfe_log_id_uuid = UUID(str(row["id"])) if row else None
    if nfe_log_id_uuid:
        substituir_itens_nfe(db, nfe_log_id=nfe_log_id_uuid, linhas=resultado["itens_processados"])

    out = {**resultado, "mensagem_fiscal": msg_fiscal, "obra_id": str(obra_id)}
    return nfe_log_id_uuid, out


def aplicar_xml_disponivel_fila(
    db: Session,
    obra_id: UUID,
    chave_acesso: str,
    xml_data: dict[str, Any],
) -> None:
    """Callback do worker: completa conferência para linha PENDENTE existente."""
    row = db.execute(
        text("""
            SELECT foto_url, tipo, nf_original_id
            FROM nfe_logs
            WHERE obra_id = :obra AND chave_acesso = :chave
        """),
        {"obra": str(obra_id), "chave": chave_acesso},
    ).mappings().first()
    if row is None:
        logger.warning("Fila sem nfe_logs correspondente obra=%s chave=%s", obra_id, chave_acesso)
        return

    nf_orig = row.get("nf_original_id")
    nf_uuid = UUID(str(nf_orig)) if nf_orig else None

    _nfe_id, resultado = gravar_conferencia_com_xml(
        db,
        obra_id=obra_id,
        chave=chave_acesso,
        payload=xml_data,
        foto_url=row.get("foto_url"),
        tipo=str(row.get("tipo") or "entrada"),
        nf_original_id=nf_uuid,
    )
    logger.info("Conferência gravada pela fila obra=%s chave=%s", obra_id, chave_acesso)
    obra_row = carregar_obra_por_id(db, obra_id)
    wd = obra_row.get("whatsapp_destino")
    wd_s = str(wd).strip() if wd else ""
    notificar_mensagem_fiscal(
        str(obra_id),
        chave_acesso,
        resultado["mensagem_fiscal"],
        whatsapp_destino_obra=wd_s or None,
        usar_coluna_obra_no_banco=False,
    )
