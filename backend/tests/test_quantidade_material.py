"""Normalização de unidade na conferência de cimento e bloco (P-10)."""

import pytest

from app.domain.conferente import (
    ConfigObraConferente,
    StatusConferencia,
    conferir_nf_multiplos_itens,
    divergencias_from_motivos,
)
from app.services.comparador_bloco import classificar_item_bloco
from app.services.comparador_cimento import classificar_item_cimento
from app.services.quantidade_material import (
    converter_quantidade_recebida,
    normalizar_dimensoes,
)


def test_28_sacos_equivalem_a_1_m3():
    r = converter_quantidade_recebida(28, "SC", "m3")
    assert r.comparavel and r.recebida == pytest.approx(1.0) and r.unidade == "m3"


def test_1400_kg_equivalem_a_28_sacos():
    r = converter_quantidade_recebida(1400, "KG", "sacos")
    assert r.comparavel and r.recebida == pytest.approx(28.0)
    assert "convertida" in r.nota


def test_toneladas_para_sacos():
    r = converter_quantidade_recebida(1.4, "TON", "sacos")
    assert r.comparavel and r.recebida == pytest.approx(28.0)


def test_unidade_incomparavel_nao_inventa_numero():
    r = converter_quantidade_recebida(10, "M2", "sacos")
    assert not r.comparavel and "sem conversão segura" in r.nota


def test_cadastro_legado_sem_unidade_compara_como_veio():
    r = converter_quantidade_recebida(28, "SC", None)
    assert r.comparavel and r.recebida == 28 and r.nota is None


def test_milheiro_de_blocos():
    r = converter_quantidade_recebida(1, "MIL", "un")
    assert r.comparavel and r.recebida == 1000


def test_cimento_kg_contra_sacos_previstos_e_verde():
    esp = {"quantidade_prevista": 28, "unidade_prevista": "sacos", "atributos_especificos": {"tipo": "CP-II"}}
    st, msg = classificar_item_cimento(esp, {"tipo_cimento": "CP-II", "quantidade": 1400, "unidade": "KG"})
    assert st == "VERDE", msg
    assert "convertida" in msg  # a evidência da conversão aparece


def test_cimento_divergencia_real_continua_sendo_detectada_apos_conversao():
    esp = {"quantidade_prevista": 28, "unidade_prevista": "sacos", "atributos_especificos": {"tipo": "CP-II"}}
    st, msg = classificar_item_cimento(esp, {"tipo_cimento": "CP-II", "quantidade": 700, "unidade": "KG"})
    assert st == "VERMELHO" and "50.0%" in msg


def test_cimento_unidade_incomparavel_e_amarelo_nao_vermelho():
    esp = {"quantidade_prevista": 28, "unidade_prevista": "sacos", "atributos_especificos": {"tipo": "CP-II"}}
    st, msg = classificar_item_cimento(esp, {"tipo_cimento": "CP-II", "quantidade": 3, "unidade": "M2"})
    assert st == "AMARELO" and "não comparável" in msg


def test_bloco_dimensoes_com_formatacao_diferente_nao_divergem():
    esp = {"atributos_especificos": {"dimensoes": "19 x 19 x 39 cm"}, "quantidade_prevista": 100}
    st, _ = classificar_item_bloco(esp, {"dimensoes": "19x19x39", "quantidade": 100, "unidade": "UN"})
    assert st == "VERDE"
    assert normalizar_dimensoes("19 X 19 X 39 cm") == "19x19x39"


def test_bloco_dimensoes_realmente_diferentes_continuam_vermelho():
    esp = {"atributos_especificos": {"dimensoes": "14x19x39"}, "quantidade_prevista": 100}
    st, _ = classificar_item_bloco(esp, {"dimensoes": "19x19x39", "quantidade": 100})
    assert st == "VERMELHO"


def test_divergencia_de_quantidade_de_cimento_gera_tag_e_alerta_corretos():
    """Antes a mensagem vinha em CAIXA ALTA e escapava da tag 'quantidade'."""
    assert "quantidade" in divergencias_from_motivos(["Quantidade: divergência 50.0% (>10%)."])
    itens = [{"descricao": "CIMENTO CP-II 50KG", "quantidade": 700, "unidade": "KG"}]
    espec = [
        {
            "categoria_material": "cimento",
            "atributos_especificos": {"tipo": "CP-II"},
            "quantidade_prevista": 28,
            "unidade_prevista": "sacos",
        }
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERMELHO.value
    assert r["alerta"] == "QUANTIDADE_DIVERGENTE"
    assert "quantidade" in r["itens_processados"][0]["divergencias"]


def test_nf_em_kg_contra_previsto_em_sacos_fim_a_fim_verde():
    itens = [{"descricao": "CIMENTO CP-II 50KG", "quantidade": 1400, "unidade": "KG"}]
    espec = [
        {
            "categoria_material": "cimento",
            "atributos_especificos": {"tipo": "CP-II"},
            "quantidade_prevista": 28,
            "unidade_prevista": "sacos",
        }
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERDE.value


# --- aço: normalização de unidade (extensão do P-10) -------------------------
from app.domain.conferente import analisar_divergencia, quantidade_recebida_em_metros


def _aco(q, un, **kw):
    return {"quantidade": q, "unidade": un, "bitola_mm": 10.0, **kw}


def test_aco_toneladas_viram_metros():
    # 10 mm = 100/162 kg/m  ->  1 t = 1620 m
    assert quantidade_recebida_em_metros(_aco(1, "TON")) == pytest.approx(1620.0)


def test_aco_unidade_pc_e_metros_por_barra_nulo_usam_padrao():
    assert quantidade_recebida_em_metros(_aco(10, "PC", metros_por_barra=None)) == 120.0
    assert quantidade_recebida_em_metros(_aco(10, "pcs")) == 120.0


def test_aco_unidade_em_minusculo_e_alias_de_metro():
    assert quantidade_recebida_em_metros(_aco(50, "mt")) == 50.0


def test_aco_unidade_desconhecida_continua_levantando():
    with pytest.raises(ValueError):
        quantidade_recebida_em_metros(_aco(5, "LATA"))


def test_aco_nf_em_toneladas_confere_contra_metros_planejados():
    esp = {"bitola_mm": 10.0, "qtd_planejada_metros": 1620.0}
    st, _, _ = analisar_divergencia(_aco(1, "TON"), esp, ConfigObraConferente(modo_aprendizado=False), bitola_ja_casada=True)
    assert st == StatusConferencia.VERDE
