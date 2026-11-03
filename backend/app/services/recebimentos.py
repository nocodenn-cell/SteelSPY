"""Recebimento físico, entrega parcial e trilha de transições.

O pedido diz o que foi comprado, a NF-e o que foi cobrado, o recebimento o que
entrou no portão. Este módulo cuida da terceira fonte e do estado que dela
decorre — e é aqui que "entrega parcial" deixa de ser texto numa observação.

Regras que este arquivo é responsável por manter:

* O estado do recebimento é calculado a partir de quantidade, não de opinião:
  `pendente` (sem contagem), `parcial` (cobriu parte), `completo` (fechou todas
  as linhas), `divergente` (veio além do que faltava).
* `encerrado` nunca é calculado. Só uma pessoa com a ação `encerrar_recebimento`
  chega lá, e sempre com motivo.
* Fechar um recebimento não fecha o pedido. Uma entrega parcial nunca encerra
  o compromisso inteiro — o pedido segue `parcial` enquanto faltar linha.
* Toda transição vai para `recebimento_eventos` / `pedido_eventos` com autor e
  motivo. Estado atual sem trilha não responde "quem fechou isso em março".

A tolerância de 2% é a mesma que `conferente` usa para chamar divergência de
VERDE; reescrever outro limiar aqui criaria duas verdades sobre o mesmo número.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.pedidos import ErroPedido

TOLERANCIA = 0.02

ESTADOS = ("pendente", "parcial", "completo", "divergente", "encerrado")


def _com_tolerancia(recebido: float, previsto: float) -> bool:
    return recebido >= previsto * (1 - TOLERANCIA)


def calcular_status_recebimento(
    linhas: list[dict[str, Any]],
    coberto: dict[str, float],
    desta_entrega: dict[str, float],
) -> tuple[str, str]:
    """
    Estado desta entrega e o motivo legível que a explica.

    `linhas` são as linhas do pedido (`{id, quantidade}`), `coberto` é o que já
    tinha entrado em entregas anteriores e `desta_entrega` é o que chegou agora.
    """
    if not desta_entrega:
        return "pendente", "Recebimento registrado no portão, sem contagem por linha."

    pedido_por_id = {str(l["id"]): float(l["quantidade"]) for l in linhas}
    excedente: list[str] = []
    for item_id, quantidade in desta_entrega.items():
        previsto = pedido_por_id.get(item_id)
        if previsto is None:
            continue
        faltava = max(previsto - coberto.get(item_id, 0.0), 0.0)
        if quantidade > faltava * (1 + TOLERANCIA):
            excedente.append(f"{quantidade - faltava:.3f} além do que faltava")
    if excedente:
        return "divergente", "Entrega acima do saldo do pedido: " + "; ".join(excedente) + "."

    if all(
        _com_tolerancia(coberto.get(str(l["id"]), 0.0) + desta_entrega.get(str(l["id"]), 0.0),
                        float(l["quantidade"]))
        for l in linhas
    ):
        return "completo", "Todas as linhas do pedido ficaram cobertas com esta entrega."

    return "parcial", "Parte do pedido chegou; ainda há linha com saldo em aberto."


def calcular_status_pedido(
    linhas: list[dict[str, Any]],
    recebido: dict[str, float],
    *,
    divergencia_aberta: bool,
) -> tuple[str, str]:
    """
    Estado do compromisso comercial depois das entregas registradas.

    `atendido` exige mais que quantidade: se ainda há conciliação VERMELHO sem
    decisão, o pedido continua `parcial`. É a regra do produto — o número fecha,
    a auditoria não.
    """
    if not linhas:
        return "aberto", "Pedido sem linhas cadastradas."
    if all(recebido.get(str(l["id"]), 0.0) <= 0 for l in linhas):
        return "aberto", "Nenhum recebimento registrado contra este pedido."
    todas_cobertas = all(
        _com_tolerancia(recebido.get(str(l["id"]), 0.0), float(l["quantidade"])) for l in linhas
    )
    if todas_cobertas and not divergencia_aberta:
        return "atendido", "Todas as linhas cobertas e nenhuma divergência aguardando decisão."
    if todas_cobertas:
        return (
            "parcial",
            "Quantidade total coberta, mas há conciliação crítica sem decisão humana.",
        )
    faltando = [
        f"linha {l.get('linha')}: {float(l['quantidade']) - recebido.get(str(l['id']), 0.0):.3f}"
        for l in linhas
        if not _com_tolerancia(recebido.get(str(l['id']), 0.0), float(l['quantidade']))
    ]
    return "parcial", "Entrega parcial — saldo em aberto em " + ", ".join(faltando) + "."


# ---------------------------------------------------------------------------
# Leitura do estado persistido
# ---------------------------------------------------------------------------


def cobertura_pedido(db: Session, pedido_id: UUID | str) -> dict[str, Any]:
    """
    Quanto de cada linha já entrou no portão.

    Recebimentos `devolucao`/`ajuste` abatem; o saldo do pedido é o que sobra
    depois de tudo que entrou, não a soma das notas do dia.
    """
    linhas = [
        dict(r)
        for r in db.execute(
            text("""
                SELECT i.id, i.linha, i.quantidade, i.unidade, i.material_tipo
                FROM pedido_itens i WHERE i.pedido_id = :p ORDER BY i.linha
            """),
            {"p": str(pedido_id)},
        ).mappings().all()
    ]
    recebidos: dict[str, float] = {}
    for r in db.execute(
        text("""
            SELECT ri.pedido_item_id,
                   SUM(CASE WHEN rec.tipo = 'devolucao' THEN -ri.quantidade ELSE ri.quantidade END)
                     AS quantidade
            FROM recebimento_itens ri
            JOIN recebimentos rec ON rec.id = ri.recebimento_id
            JOIN pedido_itens i ON i.id = ri.pedido_item_id
            WHERE i.pedido_id = :p
            GROUP BY ri.pedido_item_id
        """),
        {"p": str(pedido_id)},
    ).mappings().all():
        recebidos[str(r["pedido_item_id"])] = float(r["quantidade"])

    for linha in linhas:
        linha["quantidade"] = float(linha["quantidade"])
        recebido = recebidos.get(str(linha["id"]), 0.0)
        linha["recebido"] = recebido
        linha["saldo"] = round(max(linha["quantidade"] - recebido, 0.0), 3)
        if recebido <= 0:
            linha["status_recebimento"] = "pendente"
        elif _com_tolerancia(recebido, linha["quantidade"]):
            linha["status_recebimento"] = "completo"
        elif recebido > linha["quantidade"] * (1 + TOLERANCIA):
            linha["status_recebimento"] = "divergente"
        else:
            linha["status_recebimento"] = "parcial"

    return {"linhas": linhas, "recebido_por_item": recebidos}


def _divergencia_aberta(db: Session, pedido_id: UUID | str) -> bool:
    """
    A conciliação mais recente do pedido está crítica e sem dono? É o que impede `atendido`.

    Só a última rodada conta porque cada conciliação reavalia o pedido inteiro: a linha
    anterior é trilha, não achado aberto. Olhando todas as linhas, um pedido rejeitaria
    o estado final para sempre — a tela de divergências mostra a mais recente e o
    histórico das outras sem formulário, então não haveria como decidir o que bloqueia.
    """
    linha = db.execute(
        text("""
            SELECT 1 FROM (
                SELECT status, severidade_tecnica
                FROM conciliacoes
                WHERE pedido_id = :p
                ORDER BY criado_em DESC, id DESC
                LIMIT 1
            ) u
            WHERE u.status = 'em_analise' AND u.severidade_tecnica = 'VERMELHO'
        """),
        {"p": str(pedido_id)},
    ).first()
    return linha is not None


# ---------------------------------------------------------------------------
# Escritas
# ---------------------------------------------------------------------------


def registrar_recebimento(
    db: Session,
    *,
    tenant_id: UUID | str,
    obra_id: UUID | str,
    usuario_id: UUID | str | None,
    tipo: str = "entrada",
    id_cliente: UUID | str | None = None,
    observacoes: str | None = None,
    pedido_id: UUID | str | None = None,
    itens: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Registra a entrega no portão e atualiza o estado que dela decorre.

    `itens` é `[{pedido_item_id, quantidade, unidade?, observacao?}]`. Sem
    `pedido_id` o recebimento continua sendo o carimbo de obra de antes — o
    fluxo antigo não é quebrado, só não ganha estado de entrega parcial.
    """
    itens = [i for i in (itens or []) if i.get("quantidade") is not None]

    if pedido_id is not None:
        pedido = db.execute(
            text("SELECT id, numero, status, obra_id FROM pedidos_compra WHERE id = :p"),
            {"p": str(pedido_id)},
        ).mappings().first()
        if pedido is None:
            raise ErroPedido("Pedido não encontrado.", status_code=404)
        if str(pedido["obra_id"]) != str(obra_id):
            raise ErroPedido("Pedido não pertence a esta obra.", status_code=422)

    cobertura = cobertura_pedido(db, pedido_id) if pedido_id else {"linhas": [], "recebido_por_item": {}}
    if itens and pedido_id is None:
        raise ErroPedido("Contagem por linha exige pedido_id.")
    ids_conhecidos = {str(l["id"]) for l in cobertura["linhas"]}
    for item in itens:
        if str(item["pedido_item_id"]) not in ids_conhecidos:
            raise ErroPedido("Item de pedido não pertence a este pedido.", status_code=422)

    desta = {str(i["pedido_item_id"]): float(i["quantidade"]) for i in itens}
    if pedido_id:
        status, motivo = calcular_status_recebimento(
            cobertura["linhas"], cobertura["recebido_por_item"], desta
        )
    else:
        status, motivo = "pendente", "Recebimento de obra, sem pedido vinculado."

    linha = db.execute(
        text("""
            INSERT INTO recebimentos
                (tenant_id, obra_id, pedido_id, tipo, status, id_cliente, observacoes, criado_por)
            VALUES
                (:t, :o, :p, :tipo, :status, :cliente, :obs, :autor)
            RETURNING *
        """),
        {
            "t": str(tenant_id),
            "o": str(obra_id),
            "p": str(pedido_id) if pedido_id else None,
            "tipo": tipo,
            "status": status,
            "cliente": str(id_cliente) if id_cliente else None,
            "obs": observacoes,
            "autor": str(usuario_id) if usuario_id else None,
        },
    ).mappings().one()
    recebimento_id = str(linha["id"])

    for item in itens:
        try:
            db.execute(
                text("""
                    INSERT INTO recebimento_itens
                        (tenant_id, recebimento_id, pedido_item_id, quantidade, unidade, observacao, criado_por)
                    VALUES (:t, :r, :i, :q, :u, :obs, :autor)
                """),
                {
                    "t": str(tenant_id),
                    "r": recebimento_id,
                    "i": str(item["pedido_item_id"]),
                    "q": float(item["quantidade"]),
                    "u": item.get("unidade") or _unidade_da_linha(cobertura["linhas"], item["pedido_item_id"]),
                    "obs": item.get("observacao"),
                    "autor": str(usuario_id) if usuario_id else None,
                },
            )
        except IntegrityError as exc:
            db.rollback()
            raise ErroPedido(
                "Esta linha já foi contada neste recebimento.", status_code=409
            ) from exc

    _evento_recebimento(db, tenant_id, recebimento_id, None, status, motivo, usuario_id)

    pedido_novo = None
    if pedido_id:
        pedido_novo = recomputar_pedido(
            db, tenant_id=tenant_id, pedido_id=pedido_id, usuario_id=usuario_id
        )

    db.commit()
    resultado = _serializar(linha)
    resultado["motivo_status"] = motivo
    resultado["itens"] = [
        {"pedido_item_id": str(i["pedido_item_id"]), "quantidade": float(i["quantidade"])}
        for i in itens
    ]
    resultado["pedido_status"] = pedido_novo
    return resultado


def encerrar_recebimento(
    db: Session, *, recebimento_id: UUID | str, usuario_id: UUID | str, motivo: str
) -> dict[str, Any]:
    """
    Encerra um recebimento por decisão humana autorizada.

    Não mexe no estado do pedido. Encerrar a entrega de hoje não quita o
    compromisso de ontem: se falta linha, o pedido continua `parcial`.
    """
    if not motivo or not motivo.strip():
        raise ErroPedido("Encerrar um recebimento exige motivo.")

    linha = db.execute(
        text("SELECT * FROM recebimentos WHERE id = :id"), {"id": str(recebimento_id)}
    ).mappings().first()
    if linha is None:
        raise ErroPedido("Recebimento não encontrado.", status_code=404)
    if linha["status"] == "encerrado":
        raise ErroPedido("Este recebimento já está encerrado.", status_code=409)

    db.execute(
        text("UPDATE recebimentos SET status = 'encerrado' WHERE id = :id"),
        {"id": str(recebimento_id)},
    )
    _evento_recebimento(
        db, linha["tenant_id"], str(recebimento_id), linha["status"], "encerrado",
        motivo.strip(), usuario_id,
    )
    db.commit()
    return _serializar(linha) | {"status": "encerrado", "motivo": motivo.strip()}


def detalhe_recebimento(db: Session, recebimento_id: UUID | str) -> dict[str, Any] | None:
    """
    O que o portão precisa saber sobre uma entrega: estado, pedido e trilha.

    O `motivo` do estado mora nos eventos, não na linha do recebimento — foi assim
    que o estado deixou de ser opinião. Sem esta leitura, a tela que mostra
    `encerrado` não tem como dizer quem encerrou e por quê.
    """
    linha = db.execute(
        text("""
            SELECT r.*, p.numero AS pedido_numero, u.nome AS criado_por_nome
            FROM recebimentos r
            LEFT JOIN pedidos_compra p ON p.id = r.pedido_id
            LEFT JOIN usuarios u ON u.id = r.criado_por
            WHERE r.id = :id
        """),
        {"id": str(recebimento_id)},
    ).mappings().first()
    if linha is None:
        return None

    eventos = [
        {
            "status_de": e["status_de"],
            "status_para": e["status_para"],
            "motivo": e["motivo"],
            "criado_em": e["criado_em"].isoformat(),
            "autor_email": e["autor_email"],
        }
        for e in db.execute(
            text("""
                SELECT e.status_de, e.status_para, e.motivo, e.criado_em, u.email AS autor_email
                FROM recebimento_eventos e
                LEFT JOIN usuarios u ON u.id = e.autor_id
                WHERE e.recebimento_id = :r
                ORDER BY e.criado_em
            """),
            {"r": str(recebimento_id)},
        ).mappings().all()
    ]
    contas = [
        {
            "linha": c["linha"],
            "material_tipo": c["material_tipo"],
            "quantidade": float(c["quantidade"]),
            "unidade": c["unidade"],
            "pedido_item_id": str(c["pedido_item_id"]),
        }
        for c in db.execute(
            text("""
                SELECT ri.quantidade, ri.unidade, ri.pedido_item_id, i.linha, i.material_tipo
                FROM recebimento_itens ri
                JOIN pedido_itens i ON i.id = ri.pedido_item_id
                WHERE ri.recebimento_id = :r
                ORDER BY i.linha
            """),
            {"r": str(recebimento_id)},
        ).mappings().all()
    ]

    return {
        "id": str(linha["id"]),
        "obra_id": str(linha["obra_id"]),
        "pedido_id": str(linha["pedido_id"]) if linha["pedido_id"] else None,
        "pedido_numero": linha["pedido_numero"],
        "tipo": linha["tipo"],
        "status": linha["status"],
        "observacoes": linha["observacoes"],
        "recebido_em": linha["recebido_em"].isoformat(),
        "criado_por_nome": linha["criado_por_nome"],
        "motivo_status": eventos[-1]["motivo"] if eventos else None,
        "contagem": contas,
        "eventos": eventos,
    }


def listar_eventos(db: Session, pedido_id: UUID | str) -> list[dict[str, Any]]:
    """Trilha do que aconteceu com o pedido e com cada entrega dele."""
    recebimentos = [
        dict(r)
        for r in db.execute(
            text("""
                SELECT e.status_de, e.status_para, e.motivo, e.criado_em, e.autor_id,
                       u.email AS autor_email, 'recebimento' AS origem, rec.id AS recebimento_id
                FROM recebimento_eventos e
                JOIN recebimentos rec ON rec.id = e.recebimento_id
                LEFT JOIN usuarios u ON u.id = e.autor_id
                WHERE rec.pedido_id = :p
                ORDER BY e.criado_em
            """),
            {"p": str(pedido_id)},
        ).mappings().all()
    ]
    pedidos = [
        dict(r)
        for r in db.execute(
            text("""
                SELECT e.status_de, e.status_para, e.motivo, e.criado_em, e.autor_id,
                       u.email AS autor_email, 'pedido' AS origem, NULL::uuid AS recebimento_id
                FROM pedido_eventos e
                LEFT JOIN usuarios u ON u.id = e.autor_id
                WHERE e.pedido_id = :p
                ORDER BY e.criado_em
            """),
            {"p": str(pedido_id)},
        ).mappings().all()
    ]
    eventos = sorted(recebimentos + pedidos, key=lambda e: e["criado_em"])
    for e in eventos:
        e["criado_em"] = e["criado_em"].isoformat()
        e["recebimento_id"] = str(e["recebimento_id"]) if e["recebimento_id"] else None
        e["autor_id"] = str(e["autor_id"]) if e["autor_id"] else None
    return eventos


def _unidade_da_linha(linhas: list[dict[str, Any]], pedido_item_id: Any) -> str:
    for l in linhas:
        if str(l["id"]) == str(pedido_item_id):
            return l.get("unidade") or ""
    return ""


def _evento_recebimento(
    db: Session,
    tenant_id: Any,
    recebimento_id: str,
    status_de: str | None,
    status_para: str,
    motivo: str | None,
    usuario_id: Any,
) -> None:
    db.execute(
        text("""
            INSERT INTO recebimento_eventos
                (tenant_id, recebimento_id, status_de, status_para, motivo, autor_id)
            VALUES (:t, :r, :de, :para, :motivo, :autor)
        """),
        {
            "t": str(tenant_id),
            "r": recebimento_id,
            "de": status_de,
            "para": status_para,
            "motivo": motivo,
            "autor": str(usuario_id) if usuario_id else None,
        },
    )


def recomputar_pedido(
    db: Session,
    *,
    tenant_id: UUID | str,
    pedido_id: UUID | str,
    usuario_id: UUID | str | None,
) -> dict[str, Any] | None:
    """
    Recalcula o estado do pedido a partir das entregas.

    `cancelado` é intocado: quem cancelou um compromisso decidiu algo que a
    chegada de um caminhão não desfaz.
    """
    atual = db.execute(
        text("SELECT id, status FROM pedidos_compra WHERE id = :p"), {"p": str(pedido_id)}
    ).mappings().first()
    if atual is None or atual["status"] == "cancelado":
        return None

    cobertura = cobertura_pedido(db, pedido_id)
    novo, motivo = calcular_status_pedido(
        cobertura["linhas"],
        cobertura["recebido_por_item"],
        divergencia_aberta=_divergencia_aberta(db, pedido_id),
    )
    if novo == atual["status"]:
        # Nenhuma transição, mas o motivo calculado continua sendo a resposta para a
        # pergunta que a tela faz: "fechei a quantidade, por que o pedido não avançou?"
        return {"status": novo, "motivo": motivo}

    db.execute(
        text("UPDATE pedidos_compra SET status = :s WHERE id = :p"),
        {"s": novo, "p": str(pedido_id)},
    )
    db.execute(
        text("""
            INSERT INTO pedido_eventos (tenant_id, pedido_id, status_de, status_para, motivo, autor_id)
            VALUES (:t, :p, :de, :para, :motivo, :autor)
        """),
        {
            "t": str(tenant_id),
            "p": str(pedido_id),
            "de": atual["status"],
            "para": novo,
            "motivo": motivo,
            "autor": str(usuario_id) if usuario_id else None,
        },
    )
    return {"status": novo, "motivo": motivo}


def _serializar(linha: Any) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "obra_id": str(linha["obra_id"]),
        "pedido_id": str(linha["pedido_id"]) if linha["pedido_id"] else None,
        "tipo": linha["tipo"],
        "status": linha["status"],
        "id_cliente": str(linha["id_cliente"]) if linha["id_cliente"] else None,
        "observacoes": linha["observacoes"],
        "recebido_em": linha["recebido_em"].isoformat(),
    }
