"""Motor de correlação pedido × NF-e (P0).

O bug que estes testes fecham é um só, e ele era silencioso: duas linhas de
pedido com a mesma bitola consumiam o mesmo item faturado. A conta saía errada e
o relatório dizia VERDE.

O que se exige aqui, em ordem de importância:

1. nenhuma quantidade faturada é usada duas vezes;
2. sem evidência para decidir, não se decide — vira ambiguidade;
3. ambiguidade aparece uma única vez no resultado, não três;
4. entrega parcial da mesma linha é agregada, não confundida com ambiguidade.
"""

from __future__ import annotations

import pytest

from app.services.correlacao import (
    CONFIANCA_BITOLA_UNICA,
    CONFIANCA_CODIGO,
    CONFIANCA_MANUAL,
    CorrelacaoHumana,
    ItemFaturado,
    LinhaPedido,
    chave_base,
    correlacionar,
    normalizar_codigo,
)

NF1 = "11111111-1111-1111-1111-111111111111"
NF2 = "22222222-2222-2222-2222-222222222222"


def linha(pid: str, *, linha_no: int, qtd: float, un: str = "M", bitola: float | None = 10.0,
          codigo: str | None = None, marca: str | None = "GERDAU",
          categoria: str = "aco") -> LinhaPedido:
    return LinhaPedido(
        pedido_item_id=pid, linha=linha_no, quantidade=qtd, unidade=un,
        codigo_produto=codigo, categoria_material=categoria, bitola_mm=bitola,
        marca_exigida=marca,
    )


def item(*, nfe: str = NF1, n: int, qtd: float, un: str = "M", bitola: float | None = 10.0,
         codigo: str | None = None, marca: str | None = "GERDAU",
         descricao: str = "VERGALHAO CA-50") -> ItemFaturado:
    return ItemFaturado(
        referencia=f"{nfe}:{n}", nfe_log_id=nfe, n_item=n, quantidade=qtd, unidade=un,
        codigo_produto=codigo, descricao=descricao, bitola_mm=bitola, marca=marca,
    )


# ---------------------------------------------------------------------------
# Base de comparação
# ---------------------------------------------------------------------------


def test_chave_base_converte_quilo_em_metros_com_bitola() -> None:
    nome, valor = chave_base(100.0, "KG", 10.0)
    assert nome == "m"
    # 10 mm ≈ 0,617 kg/m → 100 kg ≈ 162 m. A precisão vem do domínio, não daqui.
    assert 150 < valor < 175


def test_chave_base_sem_bitola_nao_inventa_conversao() -> None:
    assert chave_base(100.0, "KG", None)[0] == "kg"
    assert chave_base(50.0, "SACO", None)[0] == "saco"


def test_chave_base_unidade_vazia_devolve_none() -> None:
    assert chave_base(50.0, "", 10.0) is None
    assert chave_base(None, "M", 10.0) is None


def test_chave_base_barra_de_aco_vira_metros() -> None:
    nome, valor = chave_base(10.0, "BARRA", 10.0)
    assert nome == "m" and valor == pytest.approx(120.0)


def test_normalizar_codigo_ignora_pontuacao_e_caixa() -> None:
    assert normalizar_codigo(" vca-50/10 ") == "VCA5010"
    assert normalizar_codigo(None) == ""


# ---------------------------------------------------------------------------
# O caso que motivou a correção
# ---------------------------------------------------------------------------


def test_duas_linhas_de_mesma_bitola_com_um_item_faturado_sao_ambiguas() -> None:
    """Nada é atribuído: escolher uma das duas seria inventar a correlação."""
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500), linha("B", linha_no=2, qtd=500)],
        itens=[item(n=1, qtd=500)],
    )

    assert resultado.atribuicoes == []
    assert len(resultado.ambiguidades) == 2
    assert {a.linha for a in resultado.ambiguidades} == {1, 2}
    # O item ambíguo não aparece como "faturado sem pedido": isso contaria o
    # mesmo problema duas vezes no mesmo relatório.
    assert resultado.faturados_sem_pedido == []
    assert resultado.linhas_sem_fatura == []


def test_nenhum_item_e_consumido_duas_vezes() -> None:
    soma = sum(a.quantidade_consumida_base for a in correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500), linha("B", linha_no=2, qtd=500)],
        itens=[item(n=1, qtd=500)],
    ).atribuicoes)
    assert soma == 0.0  # nada atribuído, logo nada consumido duas vezes


def test_duas_linhas_da_mesma_bitola_com_codigos_distintos_sao_decididas() -> None:
    resultado = correlacionar(
        linhas=[
            linha("A", linha_no=1, qtd=500, codigo="VCA-50/10-LOT-A"),
            linha("B", linha_no=2, qtd=500, codigo="VCA-50/10-LOT-B"),
        ],
        itens=[
            item(n=1, qtd=500, codigo="VCA-50/10-LOT-A"),
            item(n=2, qtd=500, codigo="VCA-50/10-LOT-B"),
        ],
    )

    assert resultado.ambiguidades == []
    por_linha = {a.pedido_item_id: a for a in resultado.atribuicoes}
    assert set(por_linha) == {"A", "B"}
    assert por_linha["A"].n_item == 1 and por_linha["B"].n_item == 2
    assert {a.confianca for a in resultado.atribuicoes} == {CONFIANCA_CODIGO}


def test_codigo_repetido_no_pedido_tambem_e_ambiguo() -> None:
    """Código que se repete na linha seguinte não identifica nada."""
    resultado = correlacionar(
        linhas=[
            linha("A", linha_no=1, qtd=500, codigo="VCA10"),
            linha("B", linha_no=2, qtd=500, codigo="VCA10"),
        ],
        itens=[item(n=1, qtd=500, codigo="VCA10")],
    )
    assert resultado.atribuicoes == []
    assert len(resultado.ambiguidades) == 2
    assert "código" in resultado.ambiguidades[0].motivo.lower()


# ---------------------------------------------------------------------------
# Entrega parcial e múltiplas NF-e
# ---------------------------------------------------------------------------


def test_multiplos_itens_de_mesma_bitola_em_nfe_diferentes_sao_agregados() -> None:
    """Entrega parcial não é ambiguidade quando só existe uma linha para cobrir."""
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=1000)],
        itens=[item(nfe=NF1, n=1, qtd=600), item(nfe=NF2, n=1, qtd=400)],
    )

    assert resultado.ambiguidades == []
    consumido = sum(a.quantidade_consumida_base for a in resultado.atribuicoes)
    assert consumido == pytest.approx(1000.0)
    assert len(resultado.atribuicoes) == 2
    assert {a.nfe_log_id for a in resultado.atribuicoes} == {NF1, NF2}
    assert {a.confianca for a in resultado.atribuicoes} == {CONFIANCA_BITOLA_UNICA}


def test_duas_parciais_e_duas_linhas_iguais_continuam_ambiguas() -> None:
    """Agregação só vale com um candidato. Com dois, o risco de troca volta."""
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500), linha("B", linha_no=2, qtd=500)],
        itens=[item(nfe=NF1, n=1, qtd=500), item(nfe=NF2, n=1, qtd=500)],
    )
    assert resultado.atribuicoes == []
    assert len(resultado.ambiguidades) == 2
    assert all(len(a.candidatos) == 2 for a in resultado.ambiguidades)


def test_bitolas_diferentes_nao_disputam_o_mesmo_item() -> None:
    resultado = correlacionar(
        linhas=[
            linha("A", linha_no=1, qtd=500, bitola=10.0),
            linha("B", linha_no=2, qtd=500, bitola=12.5),
        ],
        itens=[item(n=1, qtd=500, bitola=12.5), item(n=2, qtd=500, bitola=10.0)],
    )
    assert resultado.ambiguidades == []
    por = {a.pedido_item_id: a.n_item for a in resultado.atribuicoes}
    assert por == {"A": 2, "B": 1}


# ---------------------------------------------------------------------------
# Sobras
# ---------------------------------------------------------------------------


def test_item_faturado_sem_pedido_e_reportado() -> None:
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500, bitola=10.0)],
        itens=[item(n=1, qtd=500, bitola=10.0), item(n=2, qtd=200, bitola=20.0)],
    )
    assert [i["n_item"] for i in resultado.faturados_sem_pedido] == [2]
    assert resultado.faturados_sem_pedido[0]["quantidade"] == 200


def test_linha_pedida_sem_fatura_e_reportada() -> None:
    resultado = correlacionar(
        linhas=[
            linha("A", linha_no=1, qtd=500, bitola=10.0),
            linha("B", linha_no=2, qtd=300, bitola=16.0),
        ],
        itens=[item(n=1, qtd=500, bitola=10.0)],
    )
    assert [l["linha"] for l in resultado.linhas_sem_fatura] == [2]
    assert resultado.ambiguidades == []


# ---------------------------------------------------------------------------
# Unidades
# ---------------------------------------------------------------------------


def test_unidades_incompativeis_nao_casam_por_atributo() -> None:
    """1000 m pedidos contra 40 t faturados: sem bitola nos dois lados, não há base comum."""
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=1000, un="M", bitola=None, categoria="cimento")],
        itens=[item(n=1, qtd=40, un="TON", bitola=None)],
    )
    assert resultado.atribuicoes == []
    assert resultado.linhas_sem_fatura and resultado.faturados_sem_pedido


def test_quilo_faturado_casa_com_metro_pedido_quando_ha_bitola() -> None:
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=161.7, un="M", bitola=10.0)],
        itens=[item(n=1, qtd=100.0, un="KG", bitola=10.0)],
    )
    assert len(resultado.atribuicoes) == 1
    assert resultado.atribuicoes[0].base == "m"


def test_cimento_sem_bitola_casa_pela_unidade() -> None:
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=1000, un="SACO", bitola=None, categoria="cimento")],
        itens=[item(n=1, qtd=900, un="SACO", bitola=None)],
    )
    assert len(resultado.atribuicoes) == 1
    assert resultado.atribuicoes[0].quantidade_consumida_base == pytest.approx(900.0)


# ---------------------------------------------------------------------------
# Correlação humana
# ---------------------------------------------------------------------------


def test_correlacao_humana_desambigua_duas_linhas_iguais() -> None:
    linhas = [linha("A", linha_no=1, qtd=500), linha("B", linha_no=2, qtd=500)]
    sem_manual = correlacionar(linhas=linhas, itens=[item(n=1, qtd=500), item(n=2, qtd=500)])
    assert len(sem_manual.ambiguidades) == 2

    com_manual = correlacionar(
        linhas=linhas,
        itens=[item(n=1, qtd=500), item(n=2, qtd=500)],
        manuais=[CorrelacaoHumana(pedido_item_id="A", nfe_log_id=NF1, n_item=1)],
    )
    manual = [a for a in com_manual.atribuicoes if a.confianca == CONFIANCA_MANUAL]
    assert len(manual) == 1 and manual[0].pedido_item_id == "A"
    # Resolvida a linha A por ato de responsável, o item 2 fica sem concorrente:
    # a exclusividade restaura a decisão determinística para a linha B.
    auto = [a for a in com_manual.atribuicoes if a.confianca == CONFIANCA_BITOLA_UNICA]
    assert len(auto) == 1 and auto[0].pedido_item_id == "B"
    assert com_manual.ambiguidades == []


def test_correlacao_humana_parcial_divide_o_item_entre_duas_linhas() -> None:
    """O responsável diz quanto do item é da linha; o saldo segue para a outra."""
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500), linha("B", linha_no=2, qtd=500)],
        itens=[item(n=1, qtd=500)],
        manuais=[CorrelacaoHumana(pedido_item_id="A", nfe_log_id=NF1, n_item=1, quantidade=200.0)],
    )
    consumido = sum(a.quantidade_consumida_base for a in resultado.atribuicoes)
    assert consumido == pytest.approx(500.0)
    por = {a.pedido_item_id: a.quantidade_consumida_base for a in resultado.atribuicoes}
    assert por["A"] == pytest.approx(200.0)
    assert por["B"] == pytest.approx(300.0)


def test_correlacao_humana_nao_duplica_item_ja_consumido() -> None:
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500)],
        itens=[item(n=1, qtd=500)],
        manuais=[
            CorrelacaoHumana(pedido_item_id="A", nfe_log_id=NF1, n_item=1),
            CorrelacaoHumana(pedido_item_id="A", nfe_log_id=NF1, n_item=1),
        ],
    )
    assert len(resultado.atribuicoes) == 1


def test_item_sem_quantidade_nao_e_atribuido_mas_fica_visivel() -> None:
    resultado = correlacionar(
        linhas=[linha("A", linha_no=1, qtd=500)],
        itens=[item(n=1, qtd=0)],
    )
    assert resultado.atribuicoes == []
    assert resultado.faturados_sem_pedido[0]["quantidade"] == 0
