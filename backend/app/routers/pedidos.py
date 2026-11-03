"""Endpoints de fornecedores, pedidos, conciliação e dossiê.

Mesmo contrato de acesso das evidências: sessão → CSRF → tenant → papel → RLS.
Todo `pedido_id` vindo da URL é resolvido dentro do contexto do tenant; se não
aparecer, a resposta é 404 (não 403), para não confirmar existência alheia.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_usuario import SessaoAtual, abrir_contexto
from app.db import get_db
from app.deps import autorizar_na_obra, exigir_csrf, sessao_atual
from app.services import pedidos as svc
from app.tenant import consultar_obra

router = APIRouter(tags=["pedidos"])


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class ItemPedido(BaseModel):
    material_tipo: str = Field(..., min_length=1, max_length=200)
    categoria_material: Literal["aco", "cimento", "bloco", "desconhecido"] = "aco"
    bitola_mm: float | None = Field(None, gt=0)
    marca_exigida: str | None = Field(None, max_length=100)
    quantidade: float = Field(..., gt=0)
    unidade: str = Field(..., min_length=1, max_length=20)
    preco_unitario: float | None = Field(None, ge=0)
    atributos: dict[str, Any] = Field(default_factory=dict)


class PedidoBody(BaseModel):
    fornecedor_id: UUID
    numero: str = Field(..., min_length=1, max_length=60)
    itens: list[ItemPedido] = Field(..., min_length=1)
    emitido_em: date | None = None
    previsao_entrega: date | None = None
    observacoes: str | None = Field(None, max_length=2000)
    erp_ref: str | None = Field(None, max_length=100)


class FornecedorBody(BaseModel):
    cnpj: str = Field(..., min_length=14, max_length=20)
    razao_social: str = Field(..., min_length=1, max_length=200)
    nome_fantasia: str | None = Field(None, max_length=200)


class VincularNfeBody(BaseModel):
    nfe_log_id: UUID


class ConciliarBody(BaseModel):
    nfe_log_id: UUID | None = None
    recebimento_id: UUID | None = None


class DecisaoBody(BaseModel):
    decisao: Literal["aceita", "rejeitada"]
    justificativa: str = Field(..., min_length=5, max_length=4000)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _obra_autorizada(
    db: Session, sessao: SessaoAtual, obra_id: UUID, acao: str
) -> dict[str, Any]:
    obra = consultar_obra(db, obra_id)
    if obra is None or str(obra["tenant_id"]) != str(sessao.tenant_id):
        raise HTTPException(status_code=404, detail="obra não encontrada")
    autorizar_na_obra(db, sessao, obra_id, acao)
    abrir_contexto(db, sessao)
    return obra


def _pedido_autorizado(
    db: Session, sessao: SessaoAtual, pedido_id: UUID, acao: str
) -> dict[str, Any]:
    """Resolve o pedido sob RLS e confere o papel na obra dele."""
    abrir_contexto(db, sessao)
    linha = db.execute(
        text("SELECT obra_id FROM pedidos_compra WHERE id = :id"), {"id": str(pedido_id)}
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="pedido não encontrado")
    autorizar_na_obra(db, sessao, linha["obra_id"], acao)
    return {"obra_id": str(linha["obra_id"])}


def _erro(exc: svc.ErroPedido) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---------------------------------------------------------------------------
# Fornecedores e pedidos
# ---------------------------------------------------------------------------


@router.post("/obras/{obra_id}/fornecedores", status_code=201)
def post_fornecedor(
    obra_id: UUID,
    body: FornecedorBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _obra_autorizada(db, sessao, obra_id, "gerenciar_pedido")
    try:
        return svc.criar_fornecedor(
            db,
            tenant_id=sessao.tenant_id,
            cnpj=body.cnpj,
            razao_social=body.razao_social,
            nome_fantasia=body.nome_fantasia,
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


@router.post("/obras/{obra_id}/pedidos", status_code=201)
def post_pedido(
    obra_id: UUID,
    body: PedidoBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _obra_autorizada(db, sessao, obra_id, "gerenciar_pedido")
    try:
        return svc.criar_pedido(
            db,
            tenant_id=sessao.tenant_id,
            obra_id=obra_id,
            fornecedor_id=body.fornecedor_id,
            numero=body.numero,
            itens=[i.model_dump() for i in body.itens],
            emitido_em=body.emitido_em,
            previsao_entrega=body.previsao_entrega,
            observacoes=body.observacoes,
            erp_ref=body.erp_ref,
            usuario_id=sessao.usuario_id,
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


@router.get("/obras/{obra_id}/pedidos")
def get_pedidos(
    obra_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    _obra_autorizada(db, sessao, obra_id, "gerenciar_pedido")
    return {"itens": svc.listar_pedidos(db, obra_id)}


@router.get("/pedidos/{pedido_id}")
def get_pedido(
    pedido_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    _pedido_autorizado(db, sessao, pedido_id, "gerenciar_pedido")
    try:
        return svc.obter_pedido(db, pedido_id)
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


# ---------------------------------------------------------------------------
# NF-e, conciliação e decisão
# ---------------------------------------------------------------------------


@router.post("/pedidos/{pedido_id}/vincular-nfe")
def post_vincular_nfe(
    pedido_id: UUID,
    body: VincularNfeBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _pedido_autorizado(db, sessao, pedido_id, "gerenciar_pedido")
    try:
        return svc.vincular_nfe(
            db, pedido_id=pedido_id, nfe_log_id=body.nfe_log_id, tenant_id=sessao.tenant_id
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


@router.post("/pedidos/{pedido_id}/conciliar", status_code=201)
def post_conciliar(
    pedido_id: UUID,
    body: ConciliarBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _pedido_autorizado(db, sessao, pedido_id, "gerenciar_pedido")
    try:
        resultado = svc.conciliar(
            db,
            pedido_id=pedido_id,
            nfe_log_id=body.nfe_log_id,
            recebimento_id=body.recebimento_id,
        )
        registro = svc.registrar_conciliacao(
            db,
            tenant_id=sessao.tenant_id,
            pedido_id=pedido_id,
            resultado=resultado,
            usuario_id=sessao.usuario_id,
            nfe_log_id=body.nfe_log_id,
            recebimento_id=body.recebimento_id,
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc
    return {**registro, "resultado": resultado}


@router.post("/conciliacoes/{conciliacao_id}/decisao")
def post_decisao(
    conciliacao_id: UUID,
    body: DecisaoBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Decisão humana sobre a conciliação.

    Exige papel de engenheiro/admin: aceitar divergência é ato de responsável
    técnico, não de quem apenas opera o recebimento.
    """
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    abrir_contexto(db, sessao)

    linha = db.execute(
        text("SELECT pedido_id FROM conciliacoes WHERE id = :id"),
        {"id": str(conciliacao_id)},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="conciliação não encontrada")

    # Aceitar/rejeitar divergência é ato de engenharia — reaproveita a regra de
    # override, que já exige papel de engenheiro ou admin na obra.
    pedido = db.execute(
        text("SELECT obra_id FROM pedidos_compra WHERE id = :id"),
        {"id": str(linha["pedido_id"])},
    ).mappings().first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="pedido não encontrado")
    autorizar_na_obra(db, sessao, pedido["obra_id"], "override")

    try:
        return svc.decidir_conciliacao(
            db,
            conciliacao_id=conciliacao_id,
            decisao=body.decisao,
            justificativa=body.justificativa,
            usuario_id=sessao.usuario_id,
            usuario_email=sessao.email,
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


# ---------------------------------------------------------------------------
# Dossiê
# ---------------------------------------------------------------------------


@router.get("/pedidos/{pedido_id}/dossie")
def get_dossie(
    pedido_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    _pedido_autorizado(db, sessao, pedido_id, "exportar_dossie")
    try:
        return svc.montar_dossie(db, pedido_id=pedido_id)
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc
