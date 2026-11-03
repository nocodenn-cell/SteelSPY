"""
Persistência de linhas em nfe_itens após conferência (substitui anteriores do mesmo log).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def substituir_itens_nfe(
    db: Session,
    *,
    nfe_log_id: UUID,
    tenant_id: UUID,
    linhas: list[dict[str, Any]],
) -> None:
    db.execute(text("DELETE FROM nfe_itens WHERE nfe_log_id = :id"), {"id": str(nfe_log_id)})
    for linha in linhas:
        esp = linha.get("especificacao_id")
        db.execute(
            text("""
                INSERT INTO nfe_itens (
                    tenant_id, nfe_log_id, item_numero, material_recebido, bitola_recebida, marca_recebida,
                    quantidade_recebida, unidade_recebida, status_item, divergencias, mensagem_item,
                    especificacao_id
                )
                VALUES (
                    :tenant, :log, :num, :mat, :bit, :marc, :qtd, :un, :st, CAST(:div AS jsonb), :msg, :esp
                )
            """),
            {
                "tenant": str(tenant_id),
                "log": str(nfe_log_id),
                "num": int(linha["item_numero"]),
                "mat": linha.get("material_recebido"),
                "bit": linha.get("bitola_recebida"),
                "marc": linha.get("marca_recebida"),
                "qtd": linha.get("quantidade_recebida"),
                "un": linha.get("unidade_recebida"),
                "st": linha["status_item"],
                "div": json.dumps(linha.get("divergencias") or []),
                "msg": (linha.get("mensagem_item") or "")[:4000],
                "esp": str(esp) if esp else None,
            },
        )
