import pytest

from app.domain.conferente import (
    ConfigObraConferente,
    StatusConferencia,
    TipoAlerta,
    analisar_divergencia,
    conferir_nf_multiplos_itens,
    converter_para_metros,
    kg_por_metro_bitola,
)


def test_kg_por_metro_10mm_proximo_tabela_abnt():
    assert abs(kg_por_metro_bitola(10.0) - 0.617) < 0.002


@pytest.mark.parametrize(
    "bitola_mm, peso_kg, metros_esperado",
    [
        (6.3, 24.5, pytest.approx(100.0, rel=0.02)),
        (25.0, 3853.0, pytest.approx(1000.0, rel=0.02)),
        (10.0, 61.7, pytest.approx(100.0, rel=0.01)),
    ],
)
def test_converter_para_metros_edge_bitolas(bitola_mm, peso_kg, metros_esperado):
    m = converter_para_metros(peso_kg, bitola_mm)
    assert m == metros_esperado


def test_analisar_bitola_vermelho():
    item_xml = {"bitola_mm": 8.0, "marca": "X", "quantidade": 100.0, "unidade": "METROS"}
    esp = {"bitola_mm": 10.0, "marca_exigida": "X", "qtd_planejada_metros": 100.0}
    st, m, ck = analisar_divergencia(item_xml, esp, ConfigObraConferente(modo_aprendizado=False))
    assert st == StatusConferencia.VERMELHO
    assert any("Bitola" in x for x in m)
    assert ck is None


def test_analisar_marca_amarelo_se_aceita_similar():
    item_xml = {"bitola_mm": 10.0, "marca": "ARCELOR", "quantidade": 61.7, "unidade": "KG"}
    esp = {"bitola_mm": 10.0, "marca_exigida": "GERDAU", "qtd_planejada_metros": 100.0}
    st, _, _ = analisar_divergencia(
        item_xml, esp, ConfigObraConferente(aceita_similar=True, modo_aprendizado=False)
    )
    assert st == StatusConferencia.AMARELO


def test_analisar_quantidade_verde_margem_2pct():
    item_xml = {"bitola_mm": 10.0, "marca": "G", "quantidade": 61.7, "unidade": "KG"}
    esp = {"bitola_mm": 10.0, "marca_exigida": "G", "qtd_planejada_metros": 100.0}
    st, _, _ = analisar_divergencia(
        item_xml, esp, ConfigObraConferente(margem_tolerancia_float=0.02, modo_aprendizado=False)
    )
    assert st == StatusConferencia.VERDE


def test_modo_aprendizado_checkpoint():
    item_xml = {"bitola_mm": 10.0, "marca": "ARCELOR", "quantidade": 61.7, "unidade": "KG"}
    esp = {"bitola_mm": 10.0, "marca_exigida": "GERDAU", "qtd_planejada_metros": 100.0}
    st, motivos, ck = analisar_divergencia(
        item_xml, esp, ConfigObraConferente(aceita_similar=False, modo_aprendizado=True)
    )
    assert st == StatusConferencia.AMARELO
    assert ck is not None
    assert "Modo Aprendizado" in ck or "modo_aprendizado" in " ".join(motivos).lower() or "DIVERG" in ck


def test_multi_itens_material_nao_solicitado():
    itens = [
        {"bitola_mm": 10.0, "marca": "GERDAU", "quantidade": 61.7, "unidade": "KG"},
        {"bitola_mm": 32.0, "marca": "X", "quantidade": 100.0, "unidade": "KG"},
    ]
    espec = [
        {"material_tipo": "CA-50", "bitola_mm": 10.0, "marca_exigida": "GERDAU", "qtd_planejada_metros": 100.0},
    ]
    r = conferir_nf_multiplos_itens(
        itens, espec, ConfigObraConferente(modo_aprendizado=False)
    )
    assert r["status"] == StatusConferencia.VERMELHO.value
    assert r["alerta"] == TipoAlerta.MATERIAL_NAO_SOLICITADO.value
    assert any("não solicitado" in d.get("conclusão", "").lower() for d in r["detalhes"])
    assert r["resumo"]["total"] == 2
    assert r["resumo"]["vermelhos"] >= 1
    assert len(r["itens_processados"]) == 2


def test_multi_itens_conforme():
    itens = [{"bitola_mm": 10.0, "marca": "GERDAU", "quantidade": 61.7, "unidade": "KG"}]
    espec = [
        {"material_tipo": "CA-50", "bitola_mm": 10.0, "marca_exigida": "GERDAU", "qtd_planejada_metros": 100.0},
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERDE.value
    assert r["alerta"] == TipoAlerta.CONFORME.value
    assert r["can_override"] is False
    assert r["resumo"] == {"total": 1, "verdes": 1, "amarelos": 0, "vermelhos": 0}
    assert r["itens_processados"][0]["status_item"] == StatusConferencia.VERDE.value


@pytest.mark.parametrize(
    "qtd_nf,unidade,esperado_status,substring",
    [
        # 61.7 kg ≈ 100 m em 10mm — dentro de 2%
        (61.7, "KG", StatusConferencia.VERDE, None),
        # ~5% de divergência em metros: amarelo (entre 2% e 10%)
        (58.0, "KG", StatusConferencia.AMARELO, "divergência"),
        # Massa muito baixa → vermelho (>10%)
        (30.0, "KG", StatusConferencia.VERMELHO, ">10%"),
    ],
)
def test_analisar_quantidade_faixas(qtd_nf, unidade, esperado_status, substring):
    item_xml = {"bitola_mm": 10.0, "marca": "G", "quantidade": qtd_nf, "unidade": unidade}
    esp = {"bitola_mm": 10.0, "marca_exigida": "G", "qtd_planejada_metros": 100.0}
    st, motivos, ck = analisar_divergencia(
        item_xml, esp, ConfigObraConferente(margem_tolerancia_float=0.02, modo_aprendizado=False)
    )
    assert st == esperado_status
    if substring:
        assert any(substring in m for m in motivos)


def test_analisar_bitola_ja_casada_nao_redundante():
    item_xml = {"bitola_mm": 12.0, "marca": "X", "quantidade": 100.0, "unidade": "METROS"}
    esp = {"bitola_mm": 10.0, "marca_exigida": "X", "qtd_planejada_metros": 100.0}
    st, motivos, _ = analisar_divergencia(
        item_xml,
        esp,
        ConfigObraConferente(modo_aprendizado=False),
        bitola_ja_casada=True,
    )
    assert st == StatusConferencia.VERDE
    assert not any("Bitola:" in m for m in motivos)


def test_analisar_sem_marca_exigida_nao_falha_marca():
    item_xml = {"bitola_mm": 10.0, "marca": "QUALQUER", "quantidade": 61.7, "unidade": "KG"}
    esp = {"bitola_mm": 10.0, "marca_exigida": None, "qtd_planejada_metros": 100.0}
    st, _, _ = analisar_divergencia(item_xml, esp, ConfigObraConferente(modo_aprendizado=False))
    assert st == StatusConferencia.VERDE


def test_analisar_unidade_barras():
    item_xml = {
        "bitola_mm": 10.0,
        "marca": "G",
        "quantidade": 10.0,
        "unidade": "BARRA",
        "metros_por_barra": 12.0,
    }
    esp = {"bitola_mm": 10.0, "marca_exigida": "G", "qtd_planejada_metros": 120.0}
    st, _, _ = analisar_divergencia(item_xml, esp, ConfigObraConferente(modo_aprendizado=False))
    assert st == StatusConferencia.VERDE


def test_multi_itens_pior_status_vermelho_vence_amarelo():
    itens = [
        {"bitola_mm": 10.0, "marca": "GERDAU", "quantidade": 61.7, "unidade": "KG"},
        {"bitola_mm": 10.0, "marca": "OUTRA", "quantidade": 61.7, "unidade": "KG"},
    ]
    espec = [
        {"material_tipo": "CA-50", "bitola_mm": 10.0, "marca_exigida": "GERDAU", "qtd_planejada_metros": 100.0},
    ]
    r = conferir_nf_multiplos_itens(
        itens, espec, ConfigObraConferente(aceita_similar=False, modo_aprendizado=False)
    )
    assert r["status"] == StatusConferencia.VERMELHO.value
    assert r["resumo"]["verdes"] == 1
    assert r["resumo"]["vermelhos"] == 1
