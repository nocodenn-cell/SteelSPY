"""Pedidos de compra, conciliação de três vias e dossiê.

A regra que este módulo materializa:

    o pedido é o compromisso, a NF-e é a cobrança, o recebimento é o físico.

As três fontes discordam, e é justamente por isso que o produto existe. Nunca se
assume que a NF-e representa o que chegou — ela é uma das partes, não a verdade.

Reuso deliberado: a severidade de divergência por item vem de
`conferente.analisar_divergencia_detalhada`, que já concentra as regras de
bitola, marca, quantidade e o limiar de 2%/10%. Nada de reimplementar isso aqui.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.conferente import (
    StatusConferencia,
    analisar_divergencia_detalhada,
    converter_para_metros,
)

UNIDADES_POR_EXTENSO = {"M": "m", "METRO": "m", "METROS": "m", "ML": "m"}


class ErroPedido(Exception):
    def __init__(self, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------


def criar_fornecedor(
    db: Session, *, tenant_id: UUID, cnpj: str, razao_social: str, nome_fantasia: str | None
) -> dict[str, Any]:
    cnpj_limpo = "".join(c for c in str(cnpj) if c.isdigit())
    if len(cnpj_limpo) != 14:
        raise ErroPedido("CNPJ deve ter 14 dígitos.")

    existente = db.execute(
        text("SELECT * FROM fornecedores WHERE tenant_id = :t AND cnpj = :c"),
        {"t": str(tenant_id), "c": cnpj_limpo},
    ).mappings().first()
    if existente is not None:
        return _fornecedor_json(existente, criado=False)

    linha = db.execute(
        text("""
            INSERT INTO fornecedores (tenant_id, cnpj, razao_social, nome_fantasia)
            VALUES (:t, :c, :r, :f) RETURNING *
        """),
        {"t": str(tenant_id), "c": cnpj_limpo, "r": razao_social, "f": nome_fantasia},
    ).mappings().one()
    db.commit()
    return _fornecedor_json(linha, criado=True)


def _fornecedor_json(linha: Any, *, criado: bool) -> dict[str, Any]:
    return {
        "id": str(linha["id"]),
        "cnpj": linha["cnpj"],
        "razao_social": linha["razao_social"],
        "nome_fantasia": linha["nome_fantasia"],
        "criado": criado,
    }


def criar_pedido(
    db: Session,
    *,
    tenant_id: UUID,
    obra_id: UUID,
    fornecedor_id: UUID,
    numero: str,
    itens: list[dict[str, Any]],
    emitido_em: date | None = None,
    previsao_entrega: date | None = None,
    observacoes: str | None = None,
    erp_ref: str | None = None,
    usuario_id: UUID | None = None,
) -> dict[str, Any]:
    if not itens:
        raise ErroPedido("Pedido sem itens.")

    numero_limpo = (numero or "").strip()
    if not numero_limpo:
        raise ErroPedido("Número do pedido obrigatório.")

    existente = db.execute(
        text("SELECT id FROM pedidos_compra WHERE tenant_id = :t AND numero = :n"),
        {"t": str(tenant_id), "n": numero_limpo},
    ).scalar()
    if existente is not None:
        raise ErroPedido("Já existe um pedido com este número.", status_code=409)

    try:
        pedido = db.execute(
            text("""
                INSERT INTO pedidos_compra
                    (tenant_id, obra_id, fornecedor_id, numero, emitido_em,
                     previsao_entrega, observacoes, erp_ref, criado_por)
                VALUES (:t, :o, :f, :n, :e, :p, :obs, :erp, :autor)
                RETURNING *
            """),
            {
                "t": str(tenant_id),
                "o": str(obra_id),
                "f": str(fornecedor_id),
                "n": numero_limpo,
                "e": emitido_em,
                "p": previsao_entrega,
                "obs": observacoes,
                "erp": erp_ref,
                "autor": str(usuario_id) if usuario_id else None,
            },
        ).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise ErroPedido(
            "Pedido inválido: obra ou fornecedor não pertencem a esta construtora.",
            status_code=422,
        ) from exc

    total = Decimal("0")
    for indice, item in enumerate(itens, start=1):
        quantidade = item.get("quantidade")
        if quantidade is None or float(quantidade) <= 0:
            db.rollback()
            raise ErroPedido(f"Item {indice}: quantidade deve ser positiva.")
        unidade = (item.get("unidade") or "").strip()
        if not unidade:
            db.rollback()
            raise ErroPedido(f"Item {indice}: unidade obrigatória.")

        preco = item.get("preco_unitario")
        if preco is not None:
            total += Decimal(str(preco)) * Decimal(str(quantidade))

        db.execute(
            text("""
                INSERT INTO pedido_itens (
                    tenant_id, pedido_id, linha, material_tipo, categoria_material,
                    bitola_mm, marca_exigida, quantidade, unidade, preco_unitario, atributos
                ) VALUES (
                    :t, :p, :linha, :mat, :cat, :bitola, :marca, :qtd, :un, :preco, CAST(:attrs AS jsonb)
                )
            """),
            {
                "t": str(tenant_id),
                "p": str(pedido["id"]),
                "linha": indice,
                "mat": (item.get("material_tipo") or "material").strip(),
                "cat": item.get("categoria_material") or "aco",
                "bitola": item.get("bitola_mm"),
                "marca": item.get("marca_exigida"),
                "qtd": quantidade,
                "un": unidade,
                "preco": preco,
                "attrs": json.dumps(item.get("atributos") or {}, default=str),
            },
        )

    if total > 0:
        db.execute(
            text("UPDATE pedidos_compra SET valor_total = :v WHERE id = :id"),
            {"v": total, "id": str(pedido["id"])},
        )
    db.commit()
    return obter_pedido(db, pedido["id"])


def obter_pedido(db: Session, pedido_id: UUID | str) -> dict[str, Any]:
    pedido = db.execute(
        text("SELECT * FROM pedidos_compra WHERE id = :id"), {"id": str(pedido_id)}
    ).mappings().first()
    if pedido is None:
        raise ErroPedido("Pedido não encontrado.", status_code=404)

    itens = db.execute(
        text("SELECT * FROM pedido_itens WHERE pedido_id = :p ORDER BY linha"),
        {"p": str(pedido_id)},
    ).mappings().all()

    return {
        "id": str(pedido["id"]),
        "obra_id": str(pedido["obra_id"]),
        "fornecedor_id": str(pedido["fornecedor_id"]),
        "numero": pedido["numero"],
        "status": pedido["status"],
        "valor_total": str(pedido["valor_total"]) if pedido["valor_total"] is not None else None,
        "emitido_em": pedido["emitido_em"].isoformat() if pedido["emitido_em"] else None,
        "previsao_entrega": (
            pedido["previsao_entrega"].isoformat() if pedido["previsao_entrega"] else None
        ),
        "observacoes": pedido["observacoes"],
        "itens": [
            {
                "id": str(i["id"]),
                "linha": i["linha"],
                "material_tipo": i["material_tipo"],
                "categoria_material": i["categoria_material"],
                "bitola_mm": i["bitola_mm"],
                "marca_exigida": i["marca_exigida"],
                "quantidade": str(i["quantidade"]),
                "unidade": i["unidade"],
                "preco_unitario": str(i["preco_unitario"]) if i["preco_unitario"] is not None else None,
                "atributos": i["atributos"],
            }
            for i in itens
        ],
    }


def listar_pedidos(db: Session, obra_id: UUID | str) -> list[dict[str, Any]]:
    linhas = db.execute(
        text("""
            SELECT id, numero, status, valor_total, emitido_em
            FROM pedidos_compra WHERE obra_id = :o ORDER BY criado_em DESC
        """),
        {"o": str(obra_id)},
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "numero": r["numero"],
            "status": r["status"],
            "valor_total": str(r["valor_total"]) if r["valor_total"] is not None else None,
            "emitido_em": r["emitido_em"].isoformat() if r["emitido_em"] else None,
        }
        for r in linhas
    ]


# ---------------------------------------------------------------------------
# Vínculo NF-e <-> pedido
# ---------------------------------------------------------------------------


def vincular_nfe(
    db: Session, *, pedido_id: UUID | str, nfe_log_id: UUID | str, tenant_id: UUID
) -> dict[str, Any]:
    """
    Associa uma NF-e a um pedido — com as três conferências que importam.

    O navegador informa dois ids. Nenhum deles é confiado: o vínculo só é aceito
    se ambos existirem, forem do mesmo tenant, da mesma obra, e se o emitente da
    nota for o fornecedor do pedido.
    """
    pedido = db.execute(
        text("SELECT * FROM pedidos_compra WHERE id = :id"), {"id": str(pedido_id)}
    ).mappings().first()
    if pedido is None:
        raise ErroPedido("Pedido não encontrado.", status_code=404)

    nota = db.execute(
        text("SELECT * FROM nfe_logs WHERE id = :id"), {"id": str(nfe_log_id)}
    ).mappings().first()
    if nota is None:
        raise ErroPedido("NF-e não encontrada.", status_code=404)

    if str(nota["obra_id"]) != str(pedido["obra_id"]):
        raise ErroPedido(
            "NF-e e pedido pertencem a obras diferentes.", status_code=409
        )

    if nota["pedido_id"] is not None and str(nota["pedido_id"]) != str(pedido["id"]):
        raise ErroPedido("NF-e já vinculada a outro pedido.", status_code=409)

    fornecedor = db.execute(
        text("SELECT cnpj FROM fornecedores WHERE id = :id"),
        {"id": str(pedido["fornecedor_id"])},
    ).mappings().first()

    xml = nota["xml_data"] if isinstance(nota["xml_data"], dict) else {}
    cnpj_emitente = "".join(c for c in str(xml.get("emitente_cnpj") or "") if c.isdigit())
    if fornecedor and cnpj_emitente and fornecedor["cnpj"] != cnpj_emitente:
        raise ErroPedido(
            "Emitente da NF-e não corresponde ao fornecedor do pedido.", status_code=409
        )

    db.execute(
        text("UPDATE nfe_logs SET pedido_id = :p WHERE id = :id"),
        {"p": str(pedido["id"]), "id": str(nota["id"])},
    )
    db.commit()
    return {
        "pedido_id": str(pedido["id"]),
        "nfe_log_id": str(nota["id"]),
        "obra_id": str(pedido["obra_id"]),
        "vinculado": True,
    }


# ---------------------------------------------------------------------------
# Conciliação de três vias
# ---------------------------------------------------------------------------


def _metros(quantidade: Any, unidade: str | None, bitola: float | None) -> float | None:
    """Normaliza para metros quando possível. Sem bitola, só metro direto."""
    try:
        q = float(quantidade)
    except (TypeError, ValueError):
        return None
    u = (unidade or "").strip().upper()

    if u in UNIDADES_POR_EXTENSO:
        return q
    if bitola and u in ("KG", "KILO", "QUILOGRAMA", "QUILOGRAMAS"):
        return converter_para_metros(q, float(bitola))
    if bitola and u in ("BARRA", "BARRAS", "UN", "UNID", "UNIDADE"):
        return q * 12.0
    return None


def _severidade_por_percentual(delta: float, margem: float = 0.02) -> str:
    if delta <= margem:
        return StatusConferencia.VERDE.value
    if delta <= 0.10:
        return StatusConferencia.AMARELO.value
    return StatusConferencia.VERMELHO.value


def conciliar(
    db: Session,
    *,
    pedido_id: UUID | str,
    nfe_log_id: UUID | str | None = None,
    recebimento_id: UUID | str | None = None,
    modo_aprendizado: bool = False,
) -> dict[str, Any]:
    """
    Compara pedido × NF-e × recebimento físico, item a item.

    A severidade técnica vem de `analisar_divergencia_detalhada` quando o item é
    aço (bitola e quantidade em metros). Para os demais, aplica-se a mesma faixa
    de tolerância sobre a quantidade na unidade do pedido.

    `modo_aprendizado` entra apenas como informação de contexto: **não rebaixa**
    a severidade aqui. O rebaixamento é decisão operacional de outra camada.
    """
    pedido = obter_pedido(db, pedido_id)

    nota = None
    if nfe_log_id:
        nota = db.execute(
            text("SELECT * FROM nfe_logs WHERE id = :id"), {"id": str(nfe_log_id)}
        ).mappings().first()
        if nota is None:
            raise ErroPedido("NF-e não encontrada.", status_code=404)
        if nota["pedido_id"] is None:
            raise ErroPedido(
                "NF-e não está vinculada a este pedido.", status_code=409
            )

    itens_nf: list[dict[str, Any]] = []
    if nota is not None and isinstance(nota["xml_data"], dict):
        itens_nf = list(nota["xml_data"].get("itens") or [])

    fisicos: dict[str, Any] = {}
    if recebimento_id:
        linhas = db.execute(
            text("""
                SELECT item_numero, material_recebido, bitola_recebida,
                       quantidade_recebida, unidade_recebida, status_item
                FROM nfe_itens WHERE nfe_log_id = :l ORDER BY item_numero
            """),
            {"l": str(nfe_log_id)} if nfe_log_id else {"l": "00000000-0000-0000-0000-000000000000"},
        ).mappings().all()
        for r in linhas:
            fisicos[str(r["item_numero"])] = dict(r)

    linhas_resultado: list[dict[str, Any]] = []
    pior = StatusConferencia.VERDE
    itens_nf_usados: set[int] = set()

    for indice, item in enumerate(pedido["itens"], start=1):
        bitola = item["bitola_mm"]
        qtd_pedido = float(item["quantidade"])
        unidade = item["unidade"]

        # --- 1. pedido x NF-e
        correspondente, posicao_nf = _achar_item_nf(
            itens_nf, bitola, item["categoria_material"]
        )
        if posicao_nf is not None:
            itens_nf_usados.add(posicao_nf)
        qtd_nf = None
        div_nf = None
        severidade_nf = StatusConferencia.VERDE.value

        if correspondente is not None:
            qtd_nf = float(correspondente.get("quantidade") or 0)
            m_pedido = _metros(qtd_pedido, unidade, bitola)
            m_nf = _metros(qtd_nf, correspondente.get("unidade"), bitola)

            if m_pedido and m_nf is not None and m_pedido > 0:
                detalhe = analisar_divergencia_detalhada(
                    {
                        "descricao": correspondente.get("descricao"),
                        "bitola_mm": correspondente.get("bitola_mm") or bitola,
                        "marca": correspondente.get("marca"),
                        "quantidade": correspondente.get("quantidade"),
                        "unidade": correspondente.get("unidade"),
                    },
                    {
                        "bitola_mm": bitola,
                        "marca_exigida": item["marca_exigida"],
                        "qtd_planejada_metros": m_pedido,
                    },
                    # Sempre sem rebaixamento: aqui é auditoria, não implantação.
                    {"aceita_similar": False, "modo_aprendizado": False},
                    bitola_ja_casada=True,
                )
                severidade_nf = detalhe["status_tecnico"].value
                div_nf = (m_nf - m_pedido) / m_pedido
            else:
                div_nf = (qtd_nf - qtd_pedido) / qtd_pedido if qtd_pedido else None
                if div_nf is not None:
                    severidade_nf = _severidade_por_percentual(abs(div_nf))

        # --- 2. NF-e x físico
        fisico = fisicos.get(str(indice))
        qtd_fisica = float(fisico["quantidade_recebida"]) if fisico and fisico["quantidade_recebida"] else None
        div_fisica = None
        severidade_fisica = StatusConferencia.VERDE.value
        if qtd_nf is not None and qtd_fisica is not None and qtd_nf > 0:
            div_fisica = (qtd_fisica - qtd_nf) / qtd_nf
            severidade_fisica = _severidade_por_percentual(abs(div_fisica))

        severidade_item = _pior_status(severidade_nf, severidade_fisica)
        pior = _pior_status(pior.value, severidade_item)

        linhas_resultado.append(
            {
                "linha": item["linha"],
                "material": item["material_tipo"],
                "bitola_mm": bitola,
                "marca_exigida": item["marca_exigida"],
                "pedido": {"quantidade": qtd_pedido, "unidade": unidade},
                "nfe": {
                    "quantidade": qtd_nf,
                    "unidade": (correspondente or {}).get("unidade"),
                    "divergencia": round(div_nf, 6) if div_nf is not None else None,
                },
                "fisico": {
                    "quantidade": qtd_fisica,
                    "unidade": fisico["unidade_recebida"] if fisico else None,
                    "divergencia_vs_nfe": round(div_fisica, 6) if div_fisica is not None else None,
                },
                "severidade_nfe": severidade_nf,
                "severidade_fisica": severidade_fisica,
                "severidade_tecnica": severidade_item,
            }
        )

    # Item faturado que não casa com nenhuma linha do pedido é divergência
    # estrutural: comprou-se uma coisa e cobrou-se outra. Ignorar em silêncio
    # seria o pior resultado possível — pareceria conferência aprovada.
    for posicao, bruto in enumerate(itens_nf):
        if posicao in itens_nf_usados or not isinstance(bruto, dict):
            continue
        pior = _pior_status(pior, StatusConferencia.VERMELHO)
        linhas_resultado.append(
            {
                "linha": None,
                "tipo": "nao_pedido",
                "material": bruto.get("descricao") or bruto.get("material_tipo"),
                "bitola_mm": bruto.get("bitola_mm"),
                "pedido": None,
                "nfe": {
                    "quantidade": bruto.get("quantidade"),
                    "unidade": bruto.get("unidade"),
                    "divergencia": None,
                },
                "fisico": None,
                "severidade_nfe": StatusConferencia.VERMELHO.value,
                "severidade_fisica": StatusConferencia.VERDE.value,
                "severidade_tecnica": StatusConferencia.VERMELHO.value,
                "mensagem": "Item faturado na NF-e sem linha correspondente no pedido.",
            }
        )

    resultado = {
        "pedido_id": pedido["id"],
        "nfe_log_id": str(nfe_log_id) if nfe_log_id else None,
        "recebimento_id": str(recebimento_id) if recebimento_id else None,
        "modo_aprendizado_contexto": modo_aprendizado,
        "linhas": linhas_resultado,
        "severidade_tecnica": pior,
        "fonte_verdade_fisica": "recebimento" if fisicos else "ausente",
        "aviso": (
            None
            if fisicos
            else "Sem recebimento conferido: a comparação cobre apenas pedido e NF-e. "
            "A NF-e não é prova do que chegou."
        ),
    }
    return resultado


def _achar_item_nf(
    itens_nf: list[dict[str, Any]], bitola: float | None, categoria: str
) -> tuple[dict[str, Any] | None, int | None]:
    """Devolve `(item, posição)` do primeiro item da NF compatível com a linha."""
    for posicao, bruto in enumerate(itens_nf):
        if not isinstance(bruto, dict):
            continue
        b = bruto.get("bitola_mm")
        if bitola is not None and b is not None:
            try:
                if abs(float(b) - float(bitola)) <= 0.5:
                    return bruto, posicao
            except (TypeError, ValueError):
                continue
        elif categoria != "aco":
            return bruto, posicao
    return None, None


def _pior_status(a: str, b: str) -> str:
    ordem = {"VERDE": 0, "AMARELO": 1, "VERMELHO": 2}
    return a if ordem.get(a, 0) >= ordem.get(b, 0) else b


def registrar_conciliacao(
    db: Session,
    *,
    tenant_id: UUID,
    pedido_id: UUID | str,
    resultado: dict[str, Any],
    usuario_id: UUID | None,
    nfe_log_id: UUID | str | None = None,
    recebimento_id: UUID | str | None = None,
) -> dict[str, Any]:
    linha = db.execute(
        text("""
            INSERT INTO conciliacoes
                (tenant_id, pedido_id, nfe_log_id, recebimento_id, resultado,
                 severidade_tecnica, criado_por)
            VALUES (:t, :p, :n, :r, CAST(:res AS jsonb), :sev, :autor)
            RETURNING id, criado_em, status, severidade_tecnica
        """),
        {
            "t": str(tenant_id),
            "p": str(pedido_id),
            "n": str(nfe_log_id) if nfe_log_id else None,
            "r": str(recebimento_id) if recebimento_id else None,
            "res": json.dumps(resultado, default=str),
            "sev": resultado["severidade_tecnica"],
            "autor": str(usuario_id) if usuario_id else None,
        },
    ).mappings().one()
    db.commit()
    return {
        "id": str(linha["id"]),
        "criado_em": linha["criado_em"].isoformat(),
        "status": linha["status"],
        "severidade_tecnica": linha["severidade_tecnica"],
    }


def decidir_conciliacao(
    db: Session,
    *,
    conciliacao_id: UUID | str,
    decisao: str,
    justificativa: str,
    usuario_id: UUID,
    usuario_email: str,
) -> dict[str, Any]:
    """Decisão humana sobre uma conciliação. Nunca automática."""
    if decisao not in ("aceita", "rejeitada"):
        raise ErroPedido("Decisão deve ser 'aceita' ou 'rejeitada'.")

    linha = db.execute(
        text("SELECT * FROM conciliacoes WHERE id = :id"), {"id": str(conciliacao_id)}
    ).mappings().first()
    if linha is None:
        raise ErroPedido("Conciliação não encontrada.", status_code=404)

    corpo = {
        "decisao": decisao,
        "justificativa": justificativa,
        "usuario_id": str(usuario_id),
        "usuario_email": usuario_email,
        "em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "severidade_tecnica_no_momento": linha["severidade_tecnica"],
    }
    db.execute(
        text("""
            UPDATE conciliacoes
            SET status = :s, decisao = CAST(:d AS jsonb)
            WHERE id = :id
        """),
        {"s": decisao, "d": json.dumps(corpo, default=str), "id": str(conciliacao_id)},
    )
    db.commit()
    return {"id": str(conciliacao_id), "status": decisao, "decisao": corpo}


# ---------------------------------------------------------------------------
# Dossiê
# ---------------------------------------------------------------------------


def montar_dossie(db: Session, *, pedido_id: UUID | str) -> dict[str, Any]:
    """
    Reúne tudo o que comprova o recebimento de um pedido.

    O documento é factual: mostra o que existe, com hashes e identificadores.
    Não afirma validade pericial ou jurídica — isso é decisão de terceiro, não
    do software.
    """
    pedido = obter_pedido(db, pedido_id)

    notas = db.execute(
        text("""
            SELECT id, chave_acesso, status_conferencia, resumo_global, itens_resumo,
                   processado_em, tipo
            FROM nfe_logs WHERE pedido_id = :p ORDER BY processado_em
        """),
        {"p": str(pedido_id)},
    ).mappings().all()

    evidencias = db.execute(
        text("""
            SELECT e.id, e.recebimento_id, e.sha256, e.sha256_original, e.tipo,
                   e.origem, e.recebida_em, e.sinalizacao_fraude, e.reutilizada_de,
                   e.largura, e.altura
            FROM evidencias e
            JOIN recebimentos r ON r.id = e.recebimento_id
            WHERE r.obra_id = :o AND e.removido_em IS NULL
            ORDER BY e.recebida_em
        """),
        {"o": pedido["obra_id"]},
    ).mappings().all()

    conciliacoes = db.execute(
        text("""
            SELECT id, severidade_tecnica, status, decisao, criado_em
            FROM conciliacoes WHERE pedido_id = :p ORDER BY criado_em DESC
        """),
        {"p": str(pedido_id)},
    ).mappings().all()

    return {
        "pedido": pedido,
        "nfe": [
            {
                "id": str(n["id"]),
                "chave_acesso": n["chave_acesso"],
                "status_conferencia": n["status_conferencia"],
                "resumo_global": n["resumo_global"],
                "itens_resumo": n["itens_resumo"],
                "processado_em": n["processado_em"].isoformat() if n["processado_em"] else None,
                "tipo": n["tipo"],
            }
            for n in notas
        ],
        "evidencias": [
            {
                "id": str(e["id"]),
                "recebimento_id": str(e["recebimento_id"]) if e["recebimento_id"] else None,
                "sha256": e["sha256"],
                "sha256_original": e["sha256_original"],
                "tipo": e["tipo"],
                "origem": e["origem"],
                "recebida_em": e["recebida_em"].isoformat(),
                "sinalizacao_fraude": bool(e["sinalizacao_fraude"]),
                "reutilizada_de": str(e["reutilizada_de"]) if e["reutilizada_de"] else None,
                "largura": e["largura"],
                "altura": e["altura"],
            }
            for e in evidencias
        ],
        "conciliacoes": [
            {
                "id": str(c["id"]),
                "severidade_tecnica": c["severidade_tecnica"],
                "status": c["status"],
                "decisao": c["decisao"],
                "criado_em": c["criado_em"].isoformat(),
            }
            for c in conciliacoes
        ],
        "total_evidencias": len(evidencias),
        "total_conciliacoes": len(conciliacoes),
        "ressalva": (
            "Documento gerado automaticamente a partir dos registros do sistema. "
            "Não constitui laudo técnico nem parecer jurídico."
        ),
    }
