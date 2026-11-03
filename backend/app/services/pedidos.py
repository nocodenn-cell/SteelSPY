"""Pedidos de compra, conciliação de três vias e dossiê.

A regra que este módulo materializa:

    o pedido é o compromisso, a NF-e é a cobrança, o recebimento é o físico.

As três fontes discordam, e é justamente por isso que o produto existe. Nunca se
assume que a NF-e representa o que chegou — ela é uma das partes, não a verdade.

Reuso deliberado: a severidade de divergência por item vem de
`conferente.analisar_divergencia_detalhada`, que já concentra as regras de
bitola, marca, quantidade e o limiar de 2%/10%. Nada de reimplementar isso aqui.

A associação entre linha de pedido e item de NF-e vem de `services.correlacao`.
Ela era feita aqui mesmo, por "primeira linha com a mesma bitola", o que deixava
duas linhas do pedido consumirem o mesmo ferro. Na correlação uma quantidade
faturada é consumida uma única vez, e o que a evidência não decide é devolvido
para revisão humana em vez de ser escolhido por chute.
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
)
from app.services.correlacao import (
    CorrelacaoHumana,
    ItemFaturado,
    LinhaPedido,
    chave_base,
    correlacionar,
)


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
                    bitola_mm, marca_exigida, quantidade, unidade, preco_unitario,
                    codigo_produto_fornecedor, referencia_erp, atributos
                ) VALUES (
                    :t, :p, :linha, :mat, :cat, :bitola, :marca, :qtd, :un, :preco,
                    :codigo, :ref_erp, CAST(:attrs AS jsonb)
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
                "codigo": (item.get("codigo_produto_fornecedor") or "").strip() or None,
                "ref_erp": (item.get("referencia_erp") or "").strip() or None,
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
                "codigo_produto_fornecedor": i["codigo_produto_fornecedor"],
                "referencia_erp": i["referencia_erp"],
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


def _notas_do_pedido(
    db: Session, pedido_id: UUID | str, nfe_log_id: UUID | str | None
) -> list[Any]:
    """
    NF-e que entram na conciliação.

    Com `nfe_log_id`, concilia-se uma nota só — é o caso "chegou esta NF-e".
    Sem ele, concilia-se contra tudo que está vinculado ao pedido, que é o que
    responde a pergunta certa em entrega parcial: quanto do pedido já foi
    faturado, somando as notas.
    """
    if nfe_log_id:
        nota = db.execute(
            text("SELECT * FROM nfe_logs WHERE id = :id"), {"id": str(nfe_log_id)}
        ).mappings().first()
        if nota is None:
            raise ErroPedido("NF-e não encontrada.", status_code=404)
        if nota["pedido_id"] is None or str(nota["pedido_id"]) != str(pedido_id):
            raise ErroPedido("NF-e não está vinculada a este pedido.", status_code=409)
        return [nota]

    return list(
        db.execute(
            text("""
                SELECT * FROM nfe_logs
                WHERE pedido_id = :p
                ORDER BY processado_em
            """),
            {"p": str(pedido_id)},
        ).mappings().all()
    )


def _itens_faturados(nota: Any) -> list[ItemFaturado]:
    xml = nota["xml_data"] if isinstance(nota["xml_data"], dict) else {}
    brutos = list(xml.get("itens") or [])
    return [
        ItemFaturado.de_dict(bruto, nfe_log_id=str(nota["id"]), posicao=posicao)
        for posicao, bruto in enumerate(brutos, start=1)
        if isinstance(bruto, dict)
    ]


def _correlacoes_humanas(db: Session, pedido_id: UUID | str) -> list[CorrelacaoHumana]:
    """Correlações confirmadas por responsável, ainda em vigor."""
    linhas = db.execute(
        text("""
            SELECT c.pedido_item_id, c.nfe_log_id, c.nfe_item_numero, c.quantidade
            FROM correlacoes_humanas c
            JOIN pedido_itens i ON i.id = c.pedido_item_id
            WHERE i.pedido_id = :p AND c.removido_em IS NULL
            ORDER BY c.criado_em
        """),
        {"p": str(pedido_id)},
    ).mappings().all()
    return [
        CorrelacaoHumana(
            pedido_item_id=str(r["pedido_item_id"]),
            nfe_log_id=str(r["nfe_log_id"]),
            n_item=int(r["nfe_item_numero"]),
            quantidade=float(r["quantidade"]) if r["quantidade"] is not None else None,
        )
        for r in linhas
    ]


def _fisico_por_referencia(db: Session, notas: list[Any]) -> dict[str, Any]:
    """
    Linha conferida no recebimento, indexada por `nfe_log_id:n_item`.

    É o lado físico da comparação. Antes ele era casado pela *posição* da linha
    no pedido, o que não significa nada; agora entra pela mesma referência que a
    correlação produziu.
    """
    fisicos: dict[str, Any] = {}
    for nota in notas:
        for r in db.execute(
            text("""
                SELECT item_numero, material_recebido, bitola_recebida, marca_recebida,
                       quantidade_recebida, unidade_recebida, status_item
                FROM nfe_itens WHERE nfe_log_id = :l ORDER BY item_numero
            """),
            {"l": str(nota["id"])},
        ).mappings().all():
            fisicos[f"{nota['id']}:{r['item_numero']}"] = r
    return fisicos


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
    Compara pedido × NF-e × recebimento físico, linha a linha.

    A associação entre linha e item faturado é feita por `correlacao`, não por
    semelhança de bitola: cada quantidade faturada é consumida uma única vez.
    É isso que impede duas linhas de 10 mm contarem o mesmo ferro.

    A severidade técnica vem de `analisar_divergencia_detalhada` quando o item é
    aço (bitola e quantidade em metros). Para os demais, aplica-se a mesma faixa
    de tolerância sobre a quantidade na unidade do pedido.

    Ambiguidade material nunca vira VERDE. Vira AMARELO com
    `requer_revisao_humana`, e o resultado diz *por que* não decidiu.

    `modo_aprendizado` entra apenas como informação de contexto: **não rebaixa**
    a severidade aqui. O rebaixamento é decisão operacional de outra camada.
    """
    pedido = obter_pedido(db, pedido_id)
    notas = _notas_do_pedido(db, pedido_id, nfe_log_id)

    itens_faturados: list[ItemFaturado] = []
    for nota in notas:
        itens_faturados.extend(_itens_faturados(nota))

    correlacao = correlacionar(
        linhas=[LinhaPedido.de_dict(i) for i in pedido["itens"]],
        itens=itens_faturados,
        manuais=_correlacoes_humanas(db, pedido_id),
    )
    fisicos = _fisico_por_referencia(db, notas)
    atribuidas = correlacao.por_linha()

    linhas_resultado: list[dict[str, Any]] = []
    pior = StatusConferencia.VERDE.value

    for item in pedido["itens"]:
        linha = LinhaPedido.de_dict(item)
        resultado = _avaliar_linha(linha, atribuidas.get(linha.pedido_item_id, []), fisicos)
        pior = _pior_status(pior, resultado["severidade_tecnica"])
        linhas_resultado.append(resultado)

    ambiguidade_por_linha = {a.pedido_item_id: a for a in correlacao.ambiguidades}
    for resultado in linhas_resultado:
        am = ambiguidade_por_linha.get(resultado["pedido_item_id"])
        if am is None:
            continue
        resultado["status_linha"] = "revisao"
        resultado["requer_revisao_humana"] = True
        resultado["motivo_revisao"] = am.motivo
        resultado["candidatos"] = am.candidatos
        resultado["disputado_por_linha"] = am.disputado_por
        resultado["severidade_tecnica"] = _pior_status(
            resultado["severidade_tecnica"], StatusConferencia.AMARELO.value
        )
        pior = _pior_status(pior, StatusConferencia.AMARELO.value)

    # Item faturado que não casa com nenhuma linha do pedido é divergência
    # estrutural: comprou-se uma coisa e cobrou-se outra. Ignorar em silêncio
    # seria o pior resultado possível — pareceria conferência aprovada.
    nao_pedidos: list[dict[str, Any]] = []
    for bruto in correlacao.faturados_sem_pedido:
        pior = _pior_status(pior, StatusConferencia.VERMELHO.value)
        nao_pedidos.append({**bruto, "severidade_tecnica": StatusConferencia.VERMELHO.value})

    tem_fisico = bool(fisicos)
    progresso = _progresso(pedido["itens"], atribuidas, ambiguidade_por_linha)

    resultado = {
        "pedido_id": pedido["id"],
        "nfe_log_id": str(nfe_log_id) if nfe_log_id else None,
        "nfe_log_ids": [str(n["id"]) for n in notas],
        "recebimento_id": str(recebimento_id) if recebimento_id else None,
        "modo_aprendizado_contexto": modo_aprendizado,
        "linhas": linhas_resultado,
        "faturados_sem_pedido": nao_pedidos,
        "ambiguidades": [
            {
                "pedido_item_id": a.pedido_item_id,
                "linha": a.linha,
                "motivo": a.motivo,
                "candidatos": a.candidatos,
                "disputado_por_linha": a.disputado_por,
            }
            for a in correlacao.ambiguidades
        ],
        "severidade_tecnica": pior,
        "requer_revisao_humana": bool(correlacao.ambiguidades) or bool(nao_pedidos),
        "progresso": progresso,
        "fonte_verdade_fisica": "recebimento" if tem_fisico else "ausente",
        "aviso": (
            None
            if tem_fisico
            else "Sem recebimento conferido: a comparação cobre apenas pedido e NF-e. "
            "A NF-e não é prova do que chegou."
        ),
    }
    return resultado


def _avaliar_linha(
    linha: LinhaPedido,
    atribuicoes: list[Any],
    fisicos: dict[str, Any],
) -> dict[str, Any]:
    """
    Conta uma linha do pedido contra o que foi faturado para ela e contra o físico.

    A comparação é sempre feita na base comum (metros para aço, unidade declarada
    para o resto). Somar 400 kg com 12 barras exige converter antes — e quando a
    conversão não existe, a linha vai para revisão em vez de receber um número.
    """
    base_pedido = linha.base
    qtd_pedido = base_pedido[1] if base_pedido else linha.quantidade

    faturada = 0.0
    itens_vinculados: list[dict[str, Any]] = []
    marca_nf: str | None = None
    confiabilidades: set[str] = set()
    incompativel_unidade = False
    qtd_fisica: float | None = None

    for a in atribuicoes:
        confiabilidades.add(a.confianca)
        itens_vinculados.append(
            {
                "referencia": a.referencia,
                "nfe_log_id": a.nfe_log_id,
                "n_item": a.n_item,
                "quantidade_item": a.quantidade_faturada,
                "quantidade_correlacionada_base": round(a.quantidade_consumida_base, 6),
                "confianca": a.confianca,
                "origem": a.origem,
            }
        )
        if base_pedido and a.base and a.base != base_pedido[0]:
            incompativel_unidade = True
        elif a.base:
            faturada += a.quantidade_consumida_base

        fisico = fisicos.get(a.referencia)
        if fisico is not None:
            if marca_nf is None:
                marca_nf = fisico["marca_recebida"]
            convertida = chave_base(
                fisico["quantidade_recebida"],
                fisico["unidade_recebida"] or linha.unidade,
                fisico["bitola_recebida"] if fisico["bitola_recebida"] is not None else linha.bitola_mm,
            )
            if convertida and convertida[0] == (base_pedido[0] if base_pedido else convertida[0]):
                qtd_fisica = (qtd_fisica or 0.0) + convertida[1]

    severidade_nf = StatusConferencia.VERDE.value
    div_nf: float | None = None
    motivos: list[str] = []
    status_linha = "pendente"

    if base_pedido is None:
        severidade_nf = StatusConferencia.AMARELO.value
        motivos.append(
            f"Unidade do pedido '{linha.unidade}' sem base de conversão conhecida."
        )
        status_linha = "revisao"
    elif not atribuicoes:
        status_linha = "pendente"
    elif incompativel_unidade:
        severidade_nf = StatusConferencia.AMARELO.value
        motivos.append(
            "Unidade do item faturado não conversível com a unidade do pedido."
        )
        status_linha = "revisao"
    elif qtd_pedido and qtd_pedido > 0:
        div_nf = (faturada - qtd_pedido) / qtd_pedido
        if linha.categoria_material == "aco" and base_pedido and base_pedido[0] == "m":
            detalhe = analisar_divergencia_detalhada(
                {
                    "descricao": linha.material_tipo,
                    "bitola_mm": linha.bitola_mm,
                    "marca": marca_nf,
                    "quantidade": faturada,
                    "unidade": "M",
                },
                {
                    "bitola_mm": linha.bitola_mm,
                    "marca_exigida": linha.marca_exigida,
                    "qtd_planejada_metros": qtd_pedido,
                },
                # Sempre sem rebaixamento: aqui é auditoria, não implantação.
                {"aceita_similar": False, "modo_aprendizado": False},
                bitola_ja_casada=True,
            )
            severidade_nf = detalhe["status_tecnico"].value
            motivos.extend(detalhe["motivos"])
        else:
            severidade_nf = _severidade_por_percentual(abs(div_nf))
            if severidade_nf != StatusConferencia.VERDE.value:
                motivos.append(
                    f"Quantidade: pedido {qtd_pedido:.3f} {base_pedido[0] if base_pedido else linha.unidade}, "
                    f"faturado {faturada:.3f} ({div_nf * 100:.2f}%)."
                )

        if abs(div_nf) <= 0.02:
            status_linha = "completo"
        elif div_nf < 0:
            status_linha = "parcial"
        else:
            status_linha = "divergente"

    div_fisica = None
    severidade_fisica = StatusConferencia.VERDE.value
    if qtd_fisica is not None and faturada > 0:
        div_fisica = (qtd_fisica - faturada) / faturada
        severidade_fisica = _severidade_por_percentual(abs(div_fisica))

    severidade_item = _pior_status(severidade_nf, severidade_fisica)

    return {
        "linha": linha.linha,
        "pedido_item_id": linha.pedido_item_id,
        "material": linha.material_tipo,
        "categoria_material": linha.categoria_material,
        "bitola_mm": linha.bitola_mm,
        "marca_exigida": linha.marca_exigida,
        "codigo_produto_fornecedor": linha.codigo_produto,
        "base_comparacao": base_pedido[0] if base_pedido else None,
        "pedido": {
            "quantidade": linha.quantidade,
            "unidade": linha.unidade,
            "quantidade_base": round(qtd_pedido, 6) if base_pedido else None,
        },
        "nfe": {
            "quantidade": round(faturada, 6) if atribuicoes else None,
            "unidade": (base_pedido[0] if base_pedido else None),
            "divergencia": round(div_nf, 6) if div_nf is not None else None,
            "itens": itens_vinculados,
            "confianca": sorted(confiabilidades) or None,
        },
        "fisico": {
            "quantidade": round(qtd_fisica, 6) if qtd_fisica is not None else None,
            "divergencia_vs_nfe": round(div_fisica, 6) if div_fisica is not None else None,
        },
        "status_linha": status_linha,
        "incompatibilidade_unidade": incompativel_unidade,
        "requer_revisao_humana": status_linha == "revisao",
        "motivos": motivos,
        "severidade_nfe": severidade_nf,
        "severidade_fisica": severidade_fisica,
        "severidade_tecnica": severidade_item,
    }


def _progresso(
    itens: list[dict[str, Any]],
    atribuidas: dict[str, list[Any]],
    ambiguidade_por_linha: dict[str, Any],
) -> dict[str, Any]:
    """
    Quanto do pedido já foi faturado.

    Serve para uma coisa só: não deixar o sistema tratar entrega parcial como
    pedido encerrado. O percentual é por quantidade, na base de cada linha.
    """
    por_status = {"pendente": 0, "parcial": 0, "completo": 0, "divergente": 0, "revisao": 0}
    total_base = 0.0
    coberto_base = 0.0
    detalhe: list[dict[str, Any]] = []

    for item in itens:
        linha = LinhaPedido.de_dict(item)
        base = linha.base
        if base:
            total_base += base[1]
        afts = atribuidas.get(linha.pedido_item_id, [])
        unidade_base = base[0] if base else None

        if linha.pedido_item_id in ambiguidade_por_linha:
            status = "revisao"
            coberto = 0.0
        elif not afts:
            status = "pendente"
            coberto = 0.0
        else:
            coberto = sum(
                a.quantidade_consumida_base
                for a in afts
                if a.base and a.base == (base[0] if base else a.base)
            )
            if base and coberto >= base[1] * 0.999:
                status = "completo"
            elif coberto > 0:
                status = "parcial"
            else:
                status = "pendente"

        if status != "revisao":
            coberto_base += coberto
        por_status[status] += 1
        detalhe.append(
            {
                "pedido_item_id": linha.pedido_item_id,
                "linha": linha.linha,
                "material": linha.material_tipo,
                "status": status,
                "unidade_base": unidade_base,
                "pedido_base": round(base[1], 6) if base else None,
                "faturado_base": round(coberto, 6),
                "percentual": round(coberto / base[1], 6) if base and base[1] > 0 else None,
            }
        )

    return {
        "total_linhas": len(itens),
        "por_status": por_status,
        "linhas": detalhe,
        "percentual_faturado": round(coberto_base / total_base, 6) if total_base > 0 else None,
    }


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
# NF-e do pedido e da obra
# ---------------------------------------------------------------------------


def listar_conciliacoes(db: Session, pedido_id: UUID | str) -> list[dict[str, Any]]:
    """
    Conciliações do pedido, da mais recente para a mais antiga.

    A tela de divergências do celular lê daqui. `status` diz se alguém já
    decidiu: divergência sem decisão continua pendente, e a tela precisa deixar
    isso visível.
    """
    linhas = db.execute(
        text("""
            SELECT id, nfe_log_id, recebimento_id, severidade_tecnica, status,
                   criado_em, resultado, decisao
            FROM conciliacoes WHERE pedido_id = :p
            ORDER BY criado_em DESC
        """),
        {"p": str(pedido_id)},
    ).mappings().all()
    saida: list[dict[str, Any]] = []
    for r in linhas:
        resultado = r["resultado"] if isinstance(r["resultado"], dict) else {}
        saida.append(
            {
                "id": str(r["id"]),
                "nfe_log_id": str(r["nfe_log_id"]) if r["nfe_log_id"] else None,
                "recebimento_id": str(r["recebimento_id"]) if r["recebimento_id"] else None,
                "severidade_tecnica": r["severidade_tecnica"],
                "status": r["status"],
                "criado_em": r["criado_em"].isoformat() if r["criado_em"] else None,
                "requer_revisao_humana": bool(resultado.get("requer_revisao_humana")),
                "progresso": resultado.get("progresso"),
                "ambiguidades": resultado.get("ambiguidades") or [],
                "decidida_por": (r["decisao"] or {}).get("usuario_email") if r["decisao"] else None,
            }
        )
    return saida


def listar_nfe_do_pedido(db: Session, pedido_id: UUID | str) -> list[dict[str, Any]]:
    """
    NF-e vinculadas ao pedido, com os itens faturados de cada uma.

    Existe para a tela de correlação: sem ver o item da nota, o responsável não
    tem como dizer a qual linha do pedido ele pertence.
    """
    saida: list[dict[str, Any]] = []
    for nota in _notas_do_pedido(db, pedido_id, None):
        saida.append(
            {
                "id": str(nota["id"]),
                "chave_acesso": nota["chave_acesso"],
                "tipo": nota["tipo"],
                "status_conferencia": nota["status_conferencia"],
                "processado_em": (
                    nota["processado_em"].isoformat() if nota["processado_em"] else None
                ),
                "itens": [
                    {
                        "n_item": i.n_item,
                        "descricao": i.descricao,
                        "codigo_produto": i.codigo_produto,
                        "bitola_mm": i.bitola_mm,
                        "marca": i.marca,
                        "quantidade": i.quantidade,
                        "unidade": i.unidade,
                    }
                    for i in _itens_faturados(nota)
                ],
            }
        )
    return saida


def listar_nfe_da_obra(db: Session, *, obra_id: UUID | str, limite: int = 50) -> list[dict[str, Any]]:
    """Notas da obra, com o pedido a que estão vinculadas — ou nenhum."""
    linhas = db.execute(
        text("""
            SELECT id, chave_acesso, pedido_id, status_conferencia, tipo,
                   processado_em, resumo_global, itens_resumo
            FROM nfe_logs
            WHERE obra_id = :o
            ORDER BY processado_em DESC
            LIMIT :lim
        """),
        {"o": str(obra_id), "lim": int(limite)},
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "chave_acesso": r["chave_acesso"],
            "pedido_id": str(r["pedido_id"]) if r["pedido_id"] else None,
            "status_conferencia": r["status_conferencia"],
            "tipo": r["tipo"],
            "processado_em": r["processado_em"].isoformat() if r["processado_em"] else None,
            "resumo_global": r["resumo_global"],
            "itens_resumo": r["itens_resumo"],
        }
        for r in linhas
    ]


# ---------------------------------------------------------------------------
# Correlação confirmada por responsável
# ---------------------------------------------------------------------------


def correlacionar_manualmente(
    db: Session,
    *,
    tenant_id: UUID,
    pedido_id: UUID | str,
    pedido_item_id: UUID | str,
    nfe_log_id: UUID | str,
    nfe_item_numero: int,
    quantidade: float | None = None,
    observacao: str | None = None,
    usuario_id: UUID | None = None,
) -> dict[str, Any]:
    """
    Registra a decisão de um responsável sobre qual item pertence a qual linha.

    É a única saída para a ambiguidade material. Por isso é explícita, nomeada e
    reversível — e por isso não aceita nada que não se possa provar: a linha
    precisa ser do pedido, e a NF-e precisa estar vinculada a ele.

    `quantidade` divide um item entre duas linhas — é o caso em que uma única
    nota cobre meias entregas de duas linhas iguais. Sem ela, o item inteiro é
    atribuído à linha.
    """
    itens_do_pedido = set(
        str(i["id"])
        for i in db.execute(
            text("SELECT id FROM pedido_itens WHERE pedido_id = :p"), {"p": str(pedido_id)}
        ).mappings().all()
    )
    if str(pedido_item_id) not in itens_do_pedido:
        raise ErroPedido("Item de pedido não pertence a este pedido.", status_code=422)

    nota = db.execute(
        text("SELECT pedido_id FROM nfe_logs WHERE id = :id"), {"id": str(nfe_log_id)}
    ).mappings().first()
    if nota is None:
        raise ErroPedido("NF-e não encontrada.", status_code=404)
    if nota["pedido_id"] is None or str(nota["pedido_id"]) != str(pedido_id):
        raise ErroPedido(
            "NF-e precisa estar vinculada ao pedido antes de ser correlacionada.",
            status_code=409,
        )

    if quantidade is not None and float(quantidade) <= 0:
        raise ErroPedido("Quantidade correlacionada deve ser positiva.")

    try:
        linha = db.execute(
            text("""
                INSERT INTO correlacoes_humanas
                    (tenant_id, pedido_item_id, nfe_log_id, nfe_item_numero,
                     quantidade, observacao, criado_por)
                VALUES (:t, :i, :n, :num, :q, :o, :autor)
                RETURNING id, criado_em
            """),
            {
                "t": str(tenant_id),
                "i": str(pedido_item_id),
                "n": str(nfe_log_id),
                "num": int(nfe_item_numero),
                "q": quantidade,
                "o": observacao,
                "autor": str(usuario_id) if usuario_id else None,
            },
        ).mappings().one()
    except IntegrityError as exc:
        db.rollback()
        raise ErroPedido(
            "Esta linha já foi correlacionada a este item da NF-e.", status_code=409
        ) from exc

    db.commit()
    return {
        "id": str(linha["id"]),
        "criado_em": linha["criado_em"].isoformat(),
        "pedido_item_id": str(pedido_item_id),
        "nfe_log_id": str(nfe_log_id),
        "nfe_item_numero": int(nfe_item_numero),
        "quantidade": quantidade,
        "observacao": observacao,
    }


def listar_correlacoes(db: Session, pedido_id: UUID | str) -> list[dict[str, Any]]:
    linhas = db.execute(
        text("""
            SELECT c.id, c.pedido_item_id, c.nfe_log_id, c.nfe_item_numero,
                   c.quantidade, c.observacao, c.criado_em, c.criado_por, c.removido_em
            FROM correlacoes_humanas c
            JOIN pedido_itens i ON i.id = c.pedido_item_id
            WHERE i.pedido_id = :p
            ORDER BY c.criado_em
        """),
        {"p": str(pedido_id)},
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "pedido_item_id": str(r["pedido_item_id"]),
            "nfe_log_id": str(r["nfe_log_id"]),
            "nfe_item_numero": r["nfe_item_numero"],
            "quantidade": float(r["quantidade"]) if r["quantidade"] is not None else None,
            "observacao": r["observacao"],
            "criado_em": r["criado_em"].isoformat(),
            "criado_por": str(r["criado_por"]) if r["criado_por"] else None,
            "removido_em": r["removido_em"].isoformat() if r["removido_em"] else None,
        }
        for r in linhas
    ]


def desfazer_correlacao(db: Session, *, correlacao_id: UUID | str, usuario_id: UUID) -> dict[str, Any]:
    """Encerra a correlação. Não apaga: a trilha de quem correlacionou fica no banco."""
    linha = db.execute(
        text("""
            UPDATE correlacoes_humanas
            SET removido_em = NOW(), removido_por = :u
            WHERE id = :id AND removido_em IS NULL
            RETURNING id
        """),
        {"id": str(correlacao_id), "u": str(usuario_id)},
    ).mappings().first()
    if linha is None:
        raise ErroPedido("Correlação não encontrada ou já encerrada.", status_code=404)
    db.commit()
    return {"id": str(correlacao_id), "removido": True}


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
