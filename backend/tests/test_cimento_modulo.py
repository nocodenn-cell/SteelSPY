"""Testes do módulo cimento (normalização, comparador, detecção de categoria)."""

from datetime import date, timedelta

import pytest

from app.services.comparador_cimento import classificar_item_cimento
from app.services.material_categoria import detectar_categoria_material
from app.services.normalizacao_cimento import SACOS_POR_M3, normalizar_cimento


def test_normalizar_28_sacos_para_1_m3():
    q, u = normalizar_cimento(28, "sacos", "m3")
    assert u == "m3"
    assert abs(q - 1.0) < 1e-9


def test_normalizar_1400_kg_para_1_m3():
    q, u = normalizar_cimento(1400, "kg", "m3")
    assert u == "m3"
    assert abs(q - 1.0) < 1e-9


def test_normalizar_m3_para_sacos():
    q, u = normalizar_cimento(1, "m3", "sacos")
    assert u == "sacos"
    assert abs(q - SACOS_POR_M3) < 1e-9


def test_conversao_invalida_levanta():
    with pytest.raises(ValueError, match="não suportada"):
        normalizar_cimento(1, "litros", "m3")


def test_comparador_tipo_divergente_vermelho():
    esp = {
        "atributos_especificos": {"tipo": "CP-II"},
        "quantidade_prevista": 10,
    }
    st, msg = classificar_item_cimento(esp, {"tipo": "CP-V", "quantidade": 10})
    assert st == "VERMELHO"
    assert "TIPO" in msg


def test_comparador_fck_delta_grande():
    esp = {"atributos_especificos": {"fck_mpa": 30}, "quantidade_prevista": 1}
    st, _ = classificar_item_cimento(esp, {"fck_mpa": 20, "quantidade": 1})
    assert st == "VERMELHO"


def test_comparador_validade_vencida():
    esp = {"quantidade_prevista": 1}
    ontem = date.today() - timedelta(days=1)
    st, msg = classificar_item_cimento(
        esp,
        {"quantidade": 1, "data_validade": ontem.isoformat()},
        hoje=date.today(),
    )
    assert st == "VERMELHO"
    assert "VALIDADE" in msg


def test_detectar_aco_cimento_bloco():
    assert detectar_categoria_material("VERGALHAO CA-50 10MM") == "aco"
    assert detectar_categoria_material("CIMENTO CP-II 50KG") == "cimento"
    assert detectar_categoria_material("BLOCO CERAMICO 9X19X39") == "bloco"
