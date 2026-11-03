"""
Orquestração: conferir NF-e, fila de retentativa, override auditável.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Header, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_obra import verificar_acesso_obra
from app.pwa_session import SESSION_COOKIE_NAME
from app.db import get_db
from app.domain.conferente import (
    ChaveNFeInvalidaError,
    ConfigObraConferente,
    StatusConferencia,
    TipoAlerta,
    validar_chave,
)
from app.services.fila_retentativa import enfileirar_apos_falha_xml
from app.services.conferencia_persist import carregar_obra_por_id, gravar_conferencia_com_xml
from app.services.divergencias_pdf import gerar_divergencias_pdf_bytes, nome_arquivo_divergencias
from app.services.laudo_pdf import gerar_laudo_pdf_bytes, montar_contexto_laudo, nome_arquivo_laudo
from app.services.laudo_storage import SUPABASE_URL as LAUDO_SUPABASE_URL, enviar_laudo_pdf
from app.services.mensagem_fiscal import gerar_mensagem_fiscal
from app.services.nfe_io import buscar_xml_ou_json_por_chave
from app.services.whatsapp_evolution import notificar_mensagem_fiscal, notificar_xml_pendente
from app.tenant import resolver_tenant_de_nfe_log
from app.utils.url_seguras import URLNaoPermitidaError, url_redirect_laudo_confiavel, validar_url_imagem_publica

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conferencia"])


class ConferirBody(BaseModel):
    obra_id: UUID
    chave_acesso: str = Field(..., min_length=44, max_length=54)
    foto_url: str | None = Field(None, max_length=2048, description="URL da foto da NF (evidência no laudo)")
    tipo: Literal["entrada", "devolucao", "ajuste"] = Field(
        "entrada",
        description="entrada | devolucao | ajuste (devolução referencia nf_original_id)",
    )
    nf_original_id: UUID | None = Field(None, description="nfe_logs.id da NF original quando tipo=devolucao")

    @field_validator("foto_url", mode="before")
    @classmethod
    def _normalizar_foto(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("foto_url")
    @classmethod
    def _validar_foto_ssrf(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return validar_url_imagem_publica(v)
        except URLNaoPermitidaError as e:
            raise ValueError(str(e)) from e

    @model_validator(mode="after")
    def _devolucao_exige_original(self) -> ConferirBody:
        if self.tipo == "devolucao" and self.nf_original_id is None:
            raise ValueError("nf_original_id é obrigatório quando tipo=devolucao")
        return self


class OverrideBody(BaseModel):
    justificativa: str = Field(..., min_length=5, max_length=4000)
    usuario_id: str | None = None


def _notificar_aguardando(obra_id: str, chave: str, whatsapp_destino_obra: str | None) -> None:
    notificar_xml_pendente(
        obra_id,
        chave,
        whatsapp_destino_obra=whatsapp_destino_obra,
        usar_coluna_obra_no_banco=False,
    )


def _notificar_pos_conferencia(
    obra_id: str, chave: str, mensagem: str, whatsapp_destino_obra: str | None
) -> None:
    notificar_mensagem_fiscal(
        obra_id,
        chave,
        mensagem,
        whatsapp_destino_obra=whatsapp_destino_obra,
        usar_coluna_obra_no_banco=False,
    )


def _resposta_conferencia_idempotente(
    *,
    nfe_log_id: str,
    chave: str,
    status_db: str,
    xml_data: Any,
) -> dict[str, Any]:
    """Reconstrói o JSON da API a partir do snapshot em xml_data + status atual no banco (pós-override)."""
    xd = xml_data if isinstance(xml_data, dict) else {}
    resumo = xd.get("resumo") or {"total": 0, "verdes": 0, "amarelos": 0, "vermelhos": 0}
    itens_proc = xd.get("itens_processados") or []
    msg_fiscal = gerar_mensagem_fiscal(status_db, resumo, itens_proc)
    can_override = status_db == StatusConferencia.VERMELHO.value
    return {
        "nfe_log_id": nfe_log_id,
        "chave_acesso": chave,
        "status": status_db,
        "alerta": xd.get("alerta", ""),
        "detalhes": xd.get("detalhes") or [],
        "motivos": xd.get("motivos") or [],
        "modo_aprendizado": bool(xd.get("modo_aprendizado", False)),
        "mensagem_modo_aprendizado": xd.get("mensagem_modo_aprendizado"),
        "can_override": can_override,
        "resumo": resumo,
        "mensagem_fiscal": msg_fiscal,
        "laudo_pdf": f"/conferir/{nfe_log_id}/laudo.pdf",
        "divergencias_pdf": f"/conferir/{nfe_log_id}/divergencias.pdf",
    }


def _resposta_pendente_rica(
    *,
    nfe_log_id: str | None,
    chave: str,
    modo_aprendizado: bool,
) -> dict[str, Any]:
    return {
        "nfe_log_id": nfe_log_id,
        "chave_acesso": chave,
        "status": StatusConferencia.PENDENTE.value,
        "alerta": TipoAlerta.PENDENTE_XML.value,
        "detalhes": [],
        "motivos": ["Aguardando disponibilidade do XML na SEFAZ/API."],
        "modo_aprendizado": modo_aprendizado,
        "mensagem_modo_aprendizado": None,
        "can_override": False,
        "mensagem": "Retentativas automáticas em 5, 15 e 30 min.",
    }


@router.post("/conferir")
def post_conferir(
    body: ConferirBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(None, alias="X-API-KEY"),
    pwa_session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    try:
        chave = validar_chave(body.chave_acesso)
    except ChaveNFeInvalidaError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    obra = carregar_obra_por_id(db, body.obra_id)
    verificar_acesso_obra(obra, x_api_key=x_api_key, pwa_session_cookie=pwa_session_cookie)

    _wd_raw = obra.get("whatsapp_destino")
    whatsapp_destino_obra = str(_wd_raw).strip() if _wd_raw is not None else None
    if whatsapp_destino_obra == "":
        whatsapp_destino_obra = None

    if body.tipo == "devolucao" and body.nf_original_id is not None:
        pertence = db.execute(
            text("SELECT 1 FROM nfe_logs WHERE id = :id AND obra_id = :obra"),
            {"id": str(body.nf_original_id), "obra": str(body.obra_id)},
        ).scalar()
        if not pertence:
            raise HTTPException(
                status_code=422,
                detail="nf_original_id deve referenciar uma NF já registrada na mesma obra.",
            )

    ex = db.execute(
        text("""
            SELECT id, status_conferencia, xml_data
            FROM nfe_logs
            WHERE obra_id = :obra AND chave_acesso = :chave
        """),
        {"obra": str(body.obra_id), "chave": chave},
    ).mappings().first()

    config = ConfigObraConferente(
        aceita_similar=bool(obra["aceita_similar"]),
        margem_tolerancia_float=float(obra["margem_tolerancia_float"]),
        modo_aprendizado=bool(obra["modo_aprendizado"]),
    )

    if (
        ex
        and ex["status_conferencia"] != StatusConferencia.PENDENTE.value
        and ex["xml_data"] is not None
    ):
        return _resposta_conferencia_idempotente(
            nfe_log_id=str(ex["id"]),
            chave=chave,
            status_db=ex["status_conferencia"],
            xml_data=ex["xml_data"],
        )

    payload = buscar_xml_ou_json_por_chave(chave)
    if payload is None:
        if ex and ex["status_conferencia"] == StatusConferencia.PENDENTE.value:
            return _resposta_pendente_rica(
                nfe_log_id=str(ex["id"]),
                chave=chave,
                modo_aprendizado=config.modo_aprendizado,
            )
        row_pend = db.execute(
            text("""
                INSERT INTO nfe_logs (
                    tenant_id, chave_acesso, obra_id, status_conferencia, xml_data, foto_url, tipo, nf_original_id
                )
                VALUES (:tenant, :chave, :obra, 'PENDENTE', NULL, :foto, :tipo, :nf_orig)
                ON CONFLICT (obra_id, chave_acesso) DO UPDATE SET
                    status_conferencia = 'PENDENTE',
                    processado_em = NOW(),
                    foto_url = COALESCE(EXCLUDED.foto_url, nfe_logs.foto_url),
                    tipo = EXCLUDED.tipo,
                    nf_original_id = COALESCE(EXCLUDED.nf_original_id, nfe_logs.nf_original_id)
                RETURNING id
            """),
            {
                "tenant": str(obra["tenant_id"]),
                "chave": chave,
                "obra": str(body.obra_id),
                "foto": body.foto_url,
                "tipo": body.tipo,
                "nf_orig": str(body.nf_original_id) if body.nf_original_id else None,
            },
        ).mappings().first()
        db.commit()
        enfileirar_apos_falha_xml(
            db,
            obra_id=body.obra_id,
            chave_acesso=chave,
            ultimo_erro="XML não encontrado na API (404 ou timeout)",
            tenant_id=obra["tenant_id"],
        )
        background_tasks.add_task(_notificar_aguardando, str(body.obra_id), chave, whatsapp_destino_obra)
        return _resposta_pendente_rica(
            nfe_log_id=str(row_pend["id"]) if row_pend else None,
            chave=chave,
            modo_aprendizado=config.modo_aprendizado,
        )

    nfe_log_id_uuid, resultado = gravar_conferencia_com_xml(
        db,
        obra_id=body.obra_id,
        chave=chave,
        payload=payload,
        foto_url=body.foto_url,
        tipo=body.tipo,
        nf_original_id=body.nf_original_id,
    )
    db.commit()

    msg_fiscal = resultado["mensagem_fiscal"]
    resumo = resultado["resumo"]
    background_tasks.add_task(
        _notificar_pos_conferencia, str(body.obra_id), chave, msg_fiscal, whatsapp_destino_obra
    )

    nfe_log_id = str(nfe_log_id_uuid) if nfe_log_id_uuid else None
    return {
        "nfe_log_id": nfe_log_id,
        "chave_acesso": chave,
        "status": resultado["status"],
        "alerta": resultado["alerta"],
        "detalhes": resultado["detalhes"],
        "motivos": resultado["motivos"],
        "modo_aprendizado": resultado["modo_aprendizado"],
        "mensagem_modo_aprendizado": resultado["mensagem_modo_aprendizado"],
        "can_override": resultado["can_override"],
        "resumo": resumo,
        "mensagem_fiscal": msg_fiscal,
        "laudo_pdf": f"/conferir/{nfe_log_id}/laudo.pdf" if nfe_log_id else None,
        "divergencias_pdf": f"/conferir/{nfe_log_id}/divergencias.pdf" if nfe_log_id else None,
    }


# Devolve Response (bytes do PDF) ou RedirectResponse (302), nunca um modelo
# Pydantic. A anotacao de retorno e uma uniao de subclasses de Response e, a
# partir do FastAPI 0.162, isso exige response_model=None no decorador — sem
# ele o import do router falha com FastAPIError e a API nao sobe.
@router.get("/conferir/{nfe_log_id}/laudo.pdf", response_model=None)
def get_laudo_pdf(
    nfe_log_id: UUID,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(None, alias="X-API-KEY"),
    pwa_session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Response | RedirectResponse:
    """
    Laudo de Conformidade Técnica (PDF).
    Se `laudo_pdf_url` estiver preenchido (cache no Supabase Storage), redireciona (302).
    Caso contrário gera o PDF, tenta enviar ao Storage e grava a URL; se o upload falhar,
    devolve o arquivo inline.
    """
    # Abre o contexto de tenant antes de qualquer consulta: sem ele o RLS
    # esconde `obras` e o JOIN abaixo voltaria vazio.
    if resolver_tenant_de_nfe_log(db, nfe_log_id) is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    row = db.execute(
        text("""
            SELECT n.id, n.obra_id, n.chave_acesso, n.status_conferencia, n.xml_data, n.override_info,
                   n.processado_em, n.foto_url, n.laudo_pdf_url,
                   o.nome AS obra_nome, o.cnpj_destinatario, o.modo_aprendizado, o.api_key
            FROM nfe_logs n
            JOIN obras o ON o.id = n.obra_id
            WHERE n.id = :id
        """),
        {"id": str(nfe_log_id)},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    verificar_acesso_obra(
        {"id": row["obra_id"], "api_key": row.get("api_key")},
        x_api_key=x_api_key,
        pwa_session_cookie=pwa_session_cookie,
    )

    if row["status_conferencia"] == StatusConferencia.PENDENTE.value or row["xml_data"] is None:
        raise HTTPException(
            status_code=409,
            detail="Laudo disponível após conclusão da conferência (status diferente de PENDENTE com xml_data).",
        )

    cached = row.get("laudo_pdf_url")
    cand = str(cached).strip() if cached else ""
    if cand.startswith("https://") and url_redirect_laudo_confiavel(cand, LAUDO_SUPABASE_URL or ""):
        return RedirectResponse(url=cand, status_code=302)

    nfe_log = {
        "id": row["id"],
        "chave_acesso": row["chave_acesso"],
        "status_conferencia": row["status_conferencia"],
        "xml_data": row["xml_data"],
        "override_info": row["override_info"],
        "processado_em": row["processado_em"],
        "foto_url": row["foto_url"],
    }
    obra = {
        "nome": row["obra_nome"],
        "cnpj_destinatario": row["cnpj_destinatario"],
        "modo_aprendizado": bool(row.get("modo_aprendizado")),
    }
    ctx = montar_contexto_laudo(nfe_log=nfe_log, obra=obra)
    pdf_bytes = gerar_laudo_pdf_bytes(ctx)
    fname = nome_arquivo_laudo(ctx)

    public_url = enviar_laudo_pdf(nfe_log_id, pdf_bytes)
    if public_url:
        db.execute(
            text("""
                UPDATE nfe_logs
                SET laudo_pdf_url = :url, laudo_pdf_gerado_em = NOW()
                WHERE id = :id
            """),
            {"url": public_url, "id": str(nfe_log_id)},
        )
        db.commit()
        return RedirectResponse(url=public_url, status_code=302)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
        },
    )


@router.get("/conferir/{nfe_log_id}/divergencias.pdf")
def get_divergencias_pdf(
    nfe_log_id: UUID,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(None, alias="X-API-KEY"),
    pwa_session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Response:
    """
    PDF detalhado por linha (nfe_itens): divergências e mensagens do conferente.
    """
    # Contexto de tenant antes da consulta (o RLS filtra `obras` no JOIN).
    if resolver_tenant_de_nfe_log(db, nfe_log_id) is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    row = db.execute(
        text("""
            SELECT n.id, n.obra_id, n.chave_acesso, n.status_conferencia,
                   o.nome AS obra_nome, o.api_key
            FROM nfe_logs n
            JOIN obras o ON o.id = n.obra_id
            WHERE n.id = :id
        """),
        {"id": str(nfe_log_id)},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    verificar_acesso_obra(
        {"id": row["obra_id"], "api_key": row.get("api_key")},
        x_api_key=x_api_key,
        pwa_session_cookie=pwa_session_cookie,
    )

    if row["status_conferencia"] == StatusConferencia.PENDENTE.value:
        raise HTTPException(
            status_code=409,
            detail="PDF de divergências disponível após conclusão da conferência (status diferente de PENDENTE).",
        )

    it_rows = db.execute(
        text("""
            SELECT item_numero, material_recebido, bitola_recebida, marca_recebida,
                   quantidade_recebida, unidade_recebida, status_item, divergencias, mensagem_item
            FROM nfe_itens
            WHERE nfe_log_id = CAST(:id AS uuid)
            ORDER BY item_numero
        """),
        {"id": str(nfe_log_id)},
    ).mappings().all()

    linhas: list[dict[str, Any]] = []
    for r in it_rows:
        d = dict(r)
        div = d.get("divergencias")
        if isinstance(div, str):
            try:
                d["divergencias"] = json.loads(div)
            except json.JSONDecodeError:
                pass
        linhas.append(d)

    pdf_bytes = gerar_divergencias_pdf_bytes(
        obra_nome=str(row.get("obra_nome") or "—"),
        chave_acesso=str(row.get("chave_acesso") or ""),
        nfe_log_id=str(nfe_log_id),
        status_nf=str(row.get("status_conferencia") or ""),
        linhas=linhas,
    )
    fname = nome_arquivo_divergencias(str(nfe_log_id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/override/{nfe_log_id}")
def post_override(
    nfe_log_id: UUID,
    body: OverrideBody,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(None, alias="X-API-KEY"),
    pwa_session_cookie: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    # Contexto de tenant antes do SELECT ... FOR UPDATE (o JOIN em `obras` é
    # filtrado por RLS e precisaria devolver a linha).
    if resolver_tenant_de_nfe_log(db, nfe_log_id) is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    row = db.execute(
        text("""
            SELECT n.id, n.obra_id, n.status_conferencia, n.override_info, o.api_key
            FROM nfe_logs n
            JOIN obras o ON o.id = n.obra_id
            WHERE n.id = :id
            FOR UPDATE OF nfe_logs
        """),
        {"id": str(nfe_log_id)},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="nfe_log não encontrado")

    verificar_acesso_obra(
        {"id": row["obra_id"], "api_key": row.get("api_key")},
        x_api_key=x_api_key,
        pwa_session_cookie=pwa_session_cookie,
    )

    if row["status_conferencia"] != StatusConferencia.VERMELHO.value:
        raise HTTPException(
            status_code=409,
            detail=f"Override permitido apenas a partir de VERMELHO (atual: {row['status_conferencia']}).",
        )

    anterior = row["override_info"] if isinstance(row["override_info"], dict) else {}
    historico = list(anterior.get("historico", []))
    entrada = {
        "justificativa": body.justificativa,
        "usuario_id": body.usuario_id,
        "em": datetime.now(timezone.utc).isoformat(),
        "status_anterior": row["status_conferencia"],
        "status_novo": StatusConferencia.VERDE.value,
    }
    historico.append(entrada)
    novo_override = {**anterior, "historico": historico, "ultimo": entrada}

    db.execute(
        text("""
            UPDATE nfe_logs
            SET status_conferencia = 'VERDE',
                override_info = CAST(:info AS jsonb),
                laudo_pdf_url = NULL,
                laudo_pdf_gerado_em = NULL
            WHERE id = :id
        """),
        {"id": str(nfe_log_id), "info": json.dumps(novo_override)},
    )
    db.commit()

    return {"id": str(nfe_log_id), "status_conferencia": "VERDE", "override_info": novo_override}
