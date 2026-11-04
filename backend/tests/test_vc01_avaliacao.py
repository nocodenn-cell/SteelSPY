"""Métricas da Etapa 4 e a separação treino/validação/teste.

O valor da métrica depende de ela ser medida só na divisão de teste. Por isso a
separação é testada como comportamento do código, não como boa intenção.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exp_vc01.avaliacao import (
    VazamentoDeDivisao,
    amostra_da_divisao,
    contar_ground_truth,
    garantir_disjuntas,
    metricas,
    validar_uso,
)

XML = """<?xml version="1.0"?>
<annotation>
  <object><name>rebar</name><bndbox><xmin>1</xmin><ymin>1</ymin><xmax>20</xmax><ymax>20</ymax></bndbox></object>
  <object><name>rebar</name><bndbox><xmin>30</xmin><ymin>1</ymin><xmax>49</xmax><ymax>20</ymax></bndbox></object>
</annotation>
"""


def test_ground_truth_e_o_numero_de_caixas(tmp_path: Path):
    caminho = tmp_path / "a.xml"
    caminho.write_text(XML, encoding="utf-8")
    assert contar_ground_truth(caminho) == 2


def _registro(contagem: int, gt: int, veredito: str, latencia: int = 100) -> dict:
    return {"nome": ".", "veredito": veredito, "contagem": contagem, "ground_truth": gt, "latencia_ms": latencia}


def test_metricas_separam_exatas_subcontagem_e_supercontagem():
    registros = [
        _registro(24, 24, "CONTADO"),
        _registro(20, 24, "CONTADO"),
        _registro(28, 24, "CONTADO"),
        _registro(0, 24, "INCONCLUSIVO"),
    ]
    m = metricas(registros)

    assert m["fotografias"] == 4
    assert m["assumidas"] == 3
    assert m["caladas"] == 1
    assert m["taxa_rejeicao_pct"] == 25.0
    assert m["contagens_exatas"] == 1
    assert round(m["taxa_exatas_pct"], 2) == 33.33
    assert m["subcontagens"] == 1
    assert m["supercontagens"] == 1
    assert m["erros_nao_sinalizados"] == 2
    assert m["erro_absoluto_medio"] == pytest.approx(2.667, abs=0.01)
    assert m["ground_truth_medio"] == 24.0


def test_recusa_nao_conta_como_erro_nao_sinalizado():
    m = metricas([_registro(0, 30, "INCONCLUSIVO"), _registro(0, 30, "RECUSADO")])
    assert m["erros_nao_sinalizados"] == 0
    assert m["assumidas"] == 0
    assert m["erro_absoluto_medio"] is None
    assert m["taxa_rejeicao_pct"] == 100.0


def test_latencia_reporta_percentis():
    m = metricas([_registro(10, 10, "CONTADO", lat) for lat in (100, 200, 300, 400)])
    assert m["latencia_ms"] == {"p50": 200, "p95": 400, "max": 400}


def test_calibracao_recusa_a_divisao_de_teste():
    with pytest.raises(VazamentoDeDivisao):
        validar_uso("Test", para="calibracao")
    validar_uso("Validation", para="calibracao")


def test_avaliacao_so_aceita_a_divisao_de_teste():
    with pytest.raises(VazamentoDeDivisao):
        validar_uso("Validation", para="avaliacao")
    validar_uso("Test", para="avaliacao")


def test_imagem_repetida_entre_divisoes_e_denunciada(tmp_path: Path):
    for divisao in ("Training", "Validation", "Test"):
        (tmp_path / divisao).mkdir()
    foto = b"\xff\xd8\xff" + b"conteudo"
    (tmp_path / "Training" / "a.jpg").write_bytes(foto)
    (tmp_path / "Validation" / "b.jpg").write_bytes(b"\xff\xd8\xffoutro")
    (tmp_path / "Test" / "c.jpg").write_bytes(foto)

    with pytest.raises(VazamentoDeDivisao):
        garantir_disjuntas(tmp_path)


def test_excluir_contaminadas_libera_as_divisoes_e_desconta_do_total(tmp_path: Path):
    for divisao in ("Training", "Validation", "Test"):
        (tmp_path / divisao).mkdir()
    foto = b"\xff\xd8\xff" + b"conteudo"
    (tmp_path / "Training" / "a.jpg").write_bytes(foto)
    (tmp_path / "Test" / "c.jpg").write_bytes(foto)
    (tmp_path / "Test" / "d.jpg").write_bytes(b"\xff\xd8\xffproprio")
    (tmp_path / "Test" / "d.xml").write_text(XML, encoding="utf-8")

    totais = garantir_disjuntas(
        tmp_path, excluir={"Training": {"a.jpg"}, "Test": {"c.jpg"}}
    )

    assert totais == {"Training": 0, "Validation": 0, "Test": 1}
    assert amostra_da_divisao(tmp_path / "Test", excluir={"c.jpg"})[0][0].name == "d.jpg"
