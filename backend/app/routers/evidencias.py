"""Endpoints de recebimento e evidências.

Contrato de acesso, em todas as rotas:

1. sessão de usuário obrigatória (401 sem ela);
2. CSRF obrigatório nas escritas (credencial é cookie);
3. a obra precisa pertencer ao tenant da sessão — senão 404, não 403, para não
   confirmar a existência de obra alheia;
4. papel verificado pela matriz (`anexar_evidencia`, `ver_evidencia`, ...);
5. só então o contexto de tenant é aberto e o RLS entra em ação.

Nenhuma rota devolve `storage_key`. O cliente recebe metadados e um caminho de
download da própria API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_usuario import SessaoAtual, abrir_contexto
from app.db import get_db
from app.deps import autorizar_na_obra, exigir_csrf, sessao_atual
from app.services import evidencias as svc
from app.services import recebimentos as svc_recebimentos
from app.services.armazenamento import ErroArmazenamento, backend
from app.services.pedidos import ErroPedido
from app.tenant import consultar_obra

router = APIRouter(tags=["evidencias"])

ORIGENS = ("camera", "galeria", "upload", "integracao")
TIPOS = ("material", "etiqueta", "nfe", "lacre", "documento")


class ItemRecebimento(BaseModel):
    """Contagem física de uma linha do pedido, na unidade da linha."""

    pedido_item_id: UUID
    quantidade: float = Field(gt=0)
    unidade: str | None = Field(None, max_length=16)
    observacao: str | None = Field(None, max_length=2000)


class RecebimentoBody(BaseModel):
    tipo: Literal["entrada", "devolucao", "ajuste"] = "entrada"
    id_cliente: UUID | None = Field(None, description="Identificador gerado no dispositivo (offline)")
    observacoes: str | None = Field(None, max_length=2000)
    pedido_id: UUID | None = Field(
        None,
        description="Pedido que esta entrega atende. Com ele a contagem por linha "
        "define o estado da entrega (parcial, completo, divergente).",
    )
    itens: list[ItemRecebimento] = Field(
        default_factory=list, max_length=200,
        description="Quanto chegou de cada linha. Vazio = só o carimbo do portão.",
    )


class EncerrarRecebimentoBody(BaseModel):
    motivo: str = Field(min_length=5, max_length=2000)


def _obra_autorizada(
    db: Session, sessao: SessaoAtual, obra_id: UUID, acao: str
) -> dict[str, Any]:
    obra = consultar_obra(db, obra_id)
    if obra is None or str(obra["tenant_id"]) != str(sessao.tenant_id):
        raise HTTPException(status_code=404, detail="obra não encontrada")
    autorizar_na_obra(db, sessao, obra_id, acao)
    abrir_contexto(db, sessao)
    return obra


def _ler_arquivo(arquivo: UploadFile) -> bytes:
    limite = svc.limite_bytes()
    # Lê um byte além do limite para distinguir "no limite" de "acima do limite".
    conteudo = arquivo.file.read(limite + 1)
    if len(conteudo) > limite:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo acima do limite de {limite // (1024 * 1024)} MB.",
        )
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    return conteudo


@router.post("/obras/{obra_id}/recebimentos")
def post_recebimento(
    obra_id: UUID,
    body: RecebimentoBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Abre um recebimento na obra. Idempotente por `id_cliente`."""
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _obra_autorizada(db, sessao, obra_id, "criar_recebimento")

    if body.id_cliente is not None:
        existente = db.execute(
            text("SELECT * FROM recebimentos WHERE obra_id = :o AND id_cliente = :c"),
            {"o": str(obra_id), "c": str(body.id_cliente)},
        ).mappings().first()
        if existente is not None:
            return _serializar_recebimento(existente, criado=False)

    try:
        resultado = svc_recebimentos.registrar_recebimento(
            db,
            tenant_id=sessao.tenant_id,
            obra_id=obra_id,
            usuario_id=sessao.usuario_id,
            tipo=body.tipo,
            id_cliente=body.id_cliente,
            observacoes=body.observacoes,
            pedido_id=body.pedido_id,
            itens=[i.model_dump() for i in body.itens],
        )
    except ErroPedido as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    resultado["criado"] = True
    return resultado


@router.post("/recebimentos/{recebimento_id}/encerrar")
def post_encerrar_recebimento(
    recebimento_id: UUID,
    body: EncerrarRecebimentoBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Encerra uma entrega por decisão humana autorizada.

    O estado `encerrado` não é calculado em lugar nenhum do sistema: chegar nele
    exige a ação `encerrar_recebimento` e um motivo, e fica na trilha com quem
    decidiu. Encerrar a entrega não encerra o pedido.
    """
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)

    # Contexto antes da leitura: sem `app.tenant_id` o RLS não mostra nada, e o
    # dono receberia 404 do próprio recebimento.
    abrir_contexto(db, sessao)
    dono = db.execute(
        text("SELECT obra_id FROM recebimentos WHERE id = :id"), {"id": str(recebimento_id)}
    ).mappings().first()
    if dono is None:
        # 404: confirmar que o id existe em outra construtora já seria informação.
        raise HTTPException(status_code=404, detail="recebimento não encontrado")
    autorizar_na_obra(db, sessao, dono["obra_id"], "encerrar_recebimento")

    try:
        return svc_recebimentos.encerrar_recebimento(
            db,
            recebimento_id=recebimento_id,
            usuario_id=sessao.usuario_id,
            motivo=body.motivo,
        )
    except ErroPedido as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/recebimentos/{recebimento_id}")
def get_recebimento(
    recebimento_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Uma entrega, com o estado, a contagem por linha e a trilha de quem mudou quê.

    A tela de fotos precisa dele para mostrar `parcial`/`completo`/`encerrado` sem
    recarregar o histórico inteiro da obra, e para saber se ainda faz sentido
    oferecer o botão de encerrar.
    """
    sessao = sessao_atual(request, db)
    # Contexto antes da leitura, pelo mesmo motivo do encerrar: sem tenant, o RLS
    # não mostra a linha e o dono recebe 404 do próprio recebimento.
    abrir_contexto(db, sessao)
    dono = db.execute(
        text("SELECT obra_id FROM recebimentos WHERE id = :id"), {"id": str(recebimento_id)}
    ).mappings().first()
    if dono is None:
        raise HTTPException(status_code=404, detail="recebimento não encontrado")
    _obra_autorizada(db, sessao, dono["obra_id"], "ver_recebimento")

    detalhe = svc_recebimentos.detalhe_recebimento(db, recebimento_id)
    if detalhe is None:
        raise HTTPException(status_code=404, detail="recebimento não encontrado")
    return detalhe


def _serializar_recebimento(linha: Any, *, criado: bool) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "obra_id": str(linha["obra_id"]),
        "pedido_id": str(linha["pedido_id"]) if linha["pedido_id"] else None,
        "tipo": linha["tipo"],
        "status": linha["status"],
        "id_cliente": str(linha["id_cliente"]) if linha["id_cliente"] else None,
        "observacoes": linha["observacoes"],
        "recebido_em": linha["recebido_em"].isoformat(),
        "criado": criado,
    }


@router.post("/obras/{obra_id}/evidencias", status_code=201)
def post_evidencia(
    obra_id: UUID,
    request: Request,
    response: Response,
    arquivo: UploadFile = File(..., description="JPEG, PNG ou WEBP"),
    tipo: str = Form("material"),
    origem: str = Form("upload"),
    recebimento_id: str | None = Form(None),
    capturada_em: str | None = Form(None),
    idempotency_key: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    exigir_csrf(request, sessao)
    _obra_autorizada(db, sessao, obra_id, "anexar_evidencia")

    if tipo not in TIPOS:
        raise HTTPException(status_code=422, detail=f"tipo inválido: use {TIPOS}")
    if origem not in ORIGENS:
        raise HTTPException(status_code=422, detail=f"origem inválida: use {ORIGENS}")

    rec_uuid: UUID | None = None
    if recebimento_id:
        try:
            rec_uuid = UUID(recebimento_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="recebimento_id inválido") from exc
        # O recebimento precisa ser da mesma obra; o RLS já garante o tenant,
        # mas a obra precisa ser conferida explicitamente.
        pertence = db.execute(
            text("SELECT 1 FROM recebimentos WHERE id = :r AND obra_id = :o"),
            {"r": str(rec_uuid), "o": str(obra_id)},
        ).scalar()
        if not pertence:
            raise HTTPException(
                status_code=404, detail="recebimento não encontrado nesta obra"
            )

    capturada: datetime | None = None
    if capturada_em:
        try:
            capturada = datetime.fromisoformat(capturada_em.replace("Z", "+00:00"))
        except ValueError:
            # Metadado do dispositivo: se vier torto, é descartado, não bloqueia.
            capturada = None

    conteudo = _ler_arquivo(arquivo)

    try:
        evidencia, criada = svc.criar_evidencia(
            db,
            tenant_id=sessao.tenant_id,
            obra_id=obra_id,
            recebimento_id=rec_uuid,
            conteudo=conteudo,
            mime_declarado=arquivo.content_type,
            origem=origem,
            tipo=tipo,
            capturada_em=capturada,
            usuario_id=sessao.usuario_id,
            idempotency_key=idempotency_key,
        )
    except svc.ErroEvidencia as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not criada:
        # Reenvio idêntico: não é erro, é retry. 200 e não 201.
        response.status_code = 200

    return {
        **evidencia,
        "criada": criada,
        "conteudo_url": f"/evidencias/{evidencia['id']}/conteudo",
    }


@router.get("/obras/{obra_id}/recebimentos")
def get_recebimentos(
    obra_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    limite: int = 30,
) -> dict[str, Any]:
    """
    Histórico de recebimentos da obra, com quantas fotos cada um tem.

    É a tela que responde "o que já entrou hoje" sem perguntar para alguém. A
    contagem vem de um único agregado de propósito: listar um `SELECT` por
    recebimento faria esta página depender do tamanho do dia.
    """
    sessao = sessao_atual(request, db)
    _obra_autorizada(db, sessao, obra_id, "ver_recebimento")

    linhas = db.execute(
        text("""
            SELECT r.id, r.tipo, r.status, r.observacoes, r.recebido_em, r.criado_por,
                   r.pedido_id, p.numero AS pedido_numero,
                   u.nome AS criado_por_nome,
                   count(e.id) AS total_evidencias
            FROM recebimentos r
            LEFT JOIN pedidos_compra p ON p.id = r.pedido_id
            LEFT JOIN evidencias e ON e.recebimento_id = r.id AND e.removido_em IS NULL
            LEFT JOIN usuarios u ON u.id = r.criado_por
            WHERE r.obra_id = :o
            GROUP BY r.id, p.numero, u.nome
            ORDER BY r.recebido_em DESC
            LIMIT :lim
        """),
        {"o": str(obra_id), "lim": min(max(limite, 1), 200)},
    ).mappings().all()

    return {
        "itens": [
            {
                "id": str(r["id"]),
                "tipo": r["tipo"],
                "status": r["status"],
                "pedido_id": str(r["pedido_id"]) if r["pedido_id"] else None,
                "pedido_numero": r["pedido_numero"],
                "observacoes": r["observacoes"],
                "recebido_em": r["recebido_em"].isoformat(),
                "criado_por_nome": r["criado_por_nome"],
                "total_evidencias": int(r["total_evidencias"]),
            }
            for r in linhas
        ]
    }


@router.get("/obras/{obra_id}/evidencias")
def get_evidencias_da_obra(
    obra_id: UUID,
    request: Request,
    recebimento_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Evidências da obra (ou de um recebimento), sem nunca expor `storage_key`."""
    sessao = sessao_atual(request, db)
    _obra_autorizada(db, sessao, obra_id, "ver_evidencia")

    where = "obra_id = :o AND removido_em IS NULL"
    params: dict[str, Any] = {"o": str(obra_id)}
    if recebimento_id is not None:
        where += " AND recebimento_id = :r"
        params["r"] = str(recebimento_id)

    linhas = db.execute(
        text(f"""
            SELECT * FROM evidencias WHERE {where}
            ORDER BY recebida_em DESC
        """),
        params,
    ).mappings().all()

    return {
        "itens": [
            {**svc._serializar(r), "conteudo_url": f"/evidencias/{r['id']}/conteudo"}
            for r in linhas
        ]
    }


@router.get("/evidencias/{evidencia_id}")
def get_evidencia(
    evidencia_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    sessao = sessao_atual(request, db)
    abrir_contexto(db, sessao)

    linha = db.execute(
        text("SELECT * FROM evidencias WHERE id = :id AND removido_em IS NULL"),
        {"id": str(evidencia_id)},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="evidência não encontrada")

    autorizar_na_obra(db, sessao, linha["obra_id"], "ver_evidencia")
    return {
        **svc._serializar(linha),
        "conteudo_url": f"/evidencias/{evidencia_id}/conteudo",
    }


@router.get("/evidencias/{evidencia_id}/conteudo")
def get_conteudo(
    evidencia_id: UUID,
    request: Request,
    variante: str = "normalizada",
    db: Session = Depends(get_db),
) -> Response:
    """
    Download autorizado. `variante=original` devolve o arquivo exatamente como
    chegou — é a prova pericial; `normalizada` (padrão) é a versão sem EXIF.
    """
    if variante not in ("original", "normalizada"):
        raise HTTPException(status_code=422, detail="variante deve ser original ou normalizada")

    sessao = sessao_atual(request, db)
    abrir_contexto(db, sessao)

    linha = db.execute(
        text("SELECT * FROM evidencias WHERE id = :id AND removido_em IS NULL"),
        {"id": str(evidencia_id)},
    ).mappings().first()
    if linha is None:
        raise HTTPException(status_code=404, detail="evidência não encontrada")

    autorizar_na_obra(db, sessao, linha["obra_id"], "ver_evidencia")

    chave = linha["storage_key_original"] if variante == "original" else linha["storage_key"]
    mime = linha["mime_original"] if variante == "original" else linha["mime"]
    esperado = linha["sha256_original"] if variante == "original" else linha["sha256"]

    try:
        dados = backend().ler(chave)
    except ErroArmazenamento as exc:
        raise HTTPException(
            status_code=503, detail="Arquivo indisponível no armazenamento."
        ) from exc

    # Integridade conferida a cada download: se o objeto mudou, não servimos.
    if svc.sha256(dados) != esperado:
        raise HTTPException(
            status_code=500, detail="Integridade do arquivo não confere."
        )

    svc.registrar_download(
        db,
        tenant_id=sessao.tenant_id,
        evidencia_id=evidencia_id,
        variante=variante,
        usuario_id=sessao.usuario_id,
    )

    extensao = "jpg" if mime == "image/jpeg" else mime.split("/")[-1]
    return Response(
        content=dados,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{evidencia_id}.{extensao}"',
            "X-Conteudo-Sha256": esperado,
            "Cache-Control": "private, max-age=0, no-store",
        },
    )
