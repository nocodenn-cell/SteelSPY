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
    codigo_produto_fornecedor: str | None = Field(
        None,
        max_length=120,
        description="Código do produto no fornecedor (o cProd da NF-e). Base da correlação.",
    )
    referencia_erp: str | None = Field(None, max_length=120)
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


class CorrelacaoBody(BaseModel):
    pedido_item_id: UUID
    nfe_log_id: UUID
    nfe_item_numero: int = Field(..., ge=1)
    quantidade: float | None = Field(
        None,
        gt=0,
        description="Parte do item atribuída a esta linha. Omisso = item inteiro.",
    )
    observacao: str | None = Field(None, max_length=2000)


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


@router.get("/obras/{obra_id}/nfe")
def get_nfe_da_obra(
    obra_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    limite: int = 50,
) -> dict[str, Any]:
    """Notas processadas na obra — é daqui que a tela de vínculo lista o que procurar."""
    sessao = sessao_atual(request, db)
    _obra_autorizada(db, sessao, obra_id, "ver_recebimento")
    return {"itens": svc.listar_nfe_da_obra(db, obra_id=obra_id, limite=min(max(limite, 1), 200))}


@router.get("/pedidos/{pedido_id}/nfe")
def get_nfe_do_pedido(
    pedido_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """NF-e vinculadas ao pedido, com item a item — sem isto ninguém correlaciona."""
    sessao = sessao_atual(request, db)
    _pedido_autorizado(db, sessao, pedido_id, "ver_recebimento")
    try:
        return {"itens": svc.listar_nfe_do_pedido(db, pedido_id)}
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
    # Conciliar é ato de quem opera o recebimento, não de quem só compra.
    # O que exige engenharia é a *decisão* sobre a divergência (override), não o cálculo.
    _pedido_autorizado(db, sessao, pedido_id, "criar_recebimento")
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


@router.get("/pedidos/{pedido_id}/conciliacoes")
def get_conciliacoes(
    pedido_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    _pedido_autorizado(db, sessao, pedido_id, "ver_recebimento")
    return {"itens": svc.listar_conciliacoes(db, pedido_id)}


# ---------------------------------------------------------------------------
# Correlação confirmada por responsável
# ---------------------------------------------------------------------------


@router.post("/pedidos/{pedido_id}/correlacoes", status_code=201)
def post_correlacao(
    pedido_id: UUID,
    body: CorrelacaoBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Diz, com a assinatura de quem decidiu, qual item de NF-e é de qual linha.

    É a saída para a ambiguidade: o motor não escolhe, o responsável escolhe.
    Por isso o papel exigido é o de quem gerencia o pedido, e a decisão fica
    registrada com autor e horário.
    """
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _pedido_autorizado(db, sessao, pedido_id, "gerenciar_pedido")
    try:
        return svc.correlacionar_manualmente(
            db,
            tenant_id=sessao.tenant_id,
            pedido_id=pedido_id,
            pedido_item_id=body.pedido_item_id,
            nfe_log_id=body.nfe_log_id,
            nfe_item_numero=body.nfe_item_numero,
            quantidade=body.quantidade,
            observacao=body.observacao,
            usuario_id=sessao.usuario_id,
        )
    except svc.ErroPedido as exc:
        raise _erro(exc) from exc


@router.get("/pedidos/{pedido_id}/correlacoes")
def get_correlacoes(
    pedido_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    _pedido_autorizado(db, sessao, pedido_id, "ver_recebimento")
    return {"itens": svc.listar_correlacoes(db, pedido_id)}


@router.delete("/correlacoes/{correlacao_id}")
def delete_correlacao(
    correlacao_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Encerra uma correlação — não apaga o registro, marca como removida.

    A correlação é resolvida pelo próprio tenant via RLS; a obra é descoberta a
    partir dela para não haver como autorizar em obra errada.
    """
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    abrir_contexto(db, sessao)
    linha = db.execute(
        text("""
            SELECT i.pedido_id AS pid, p.obra_id AS oid
            FROM correlacoes_humanas c
            JOIN pedido_itens i ON i.id = c.pedido_item_id
            JOIN pedidos_compra p ON p.id = i.pedido_id
            WHERE c.id = :id
        """),
        {"id": str(correlacao_id)},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="correlação não encontrada")
    autorizar_na_obra(db, sessao, linha["oid"], "gerenciar_pedido")
    try:
        return svc.desfazer_correlacao(
            db, correlacao_id=correlacao_id, usuario_id=sessao.usuario_id
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
