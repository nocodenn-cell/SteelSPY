"""Métricas de detecção e portão de validação humana (Sprint 5)."""

from __future__ import annotations

import copy
import json

import pytest

from exp_vc02 import cli, metricas

VERDADE = {
    "images": [{"id": 1}, {"id": 2}],
    "categories": [{"id": 1, "name": "ponta"}],
    "annotations": [
        {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 20, 20]},
        {"id": 2, "image_id": 2, "category_id": 1, "bbox": [10, 10, 20, 20]},
    ],
}


def _predicoes(*caixas: tuple[int, int, float], validacao: dict | None = None) -> dict:
    preds = {
        "annotations": [
            {"id": indice, "image_id": imagem, "category_id": 1, "bbox": list(caixa), "score": score}
            for indice, (imagem, caixa, score) in enumerate(caixas, start=1)
        ]
    }
    if validacao is not None:
        preds["validacao_humana"] = validacao
    return preds


def test_predicao_perfeita_tem_ap_e_precisao_inteiros():
    resultado = metricas.avaliar(
        VERDADE,
        _predicoes((1, (10, 10, 20, 20), 0.9), (2, (10, 10, 20, 20), 0.8)),
        min_map50=0.99,
        min_precisao=0.99,
        min_recall=0.99,
    )
    assert resultado["map50"] == 1.0
    assert resultado["map75"] == 1.0
    assert resultado["map50_95"] == 1.0
    assert resultado["precisao"] == 1.0
    assert resultado["recall"] == 1.0
    assert resultado["f1"] == 1.0
    assert resultado["aprovado"], resultado["reprovacoes"]


def test_deteccao_faltante_reduz_recall():
    resultado = metricas.avaliar(VERDADE, _predicoes((1, (10, 10, 20, 20), 0.9)))
    assert resultado["recall"] == 0.5
    assert resultado["gt"] == {"verdadeiros_positivos": 1, "falsos_positivos": 0, "falsos_negativos": 1}


def test_falso_positivo_reduz_precisao():
    resultado = metricas.avaliar(
        VERDADE,
        _predicoes((1, (10, 10, 20, 20), 0.9), (2, (10, 10, 20, 20), 0.9), (2, (200, 200, 10, 10), 0.8)),
    )
    assert resultado["precisao"] == pytest.approx(2 / 3, abs=1e-4)
    assert resultado["recall"] == 1.0


def test_caixa_deslocada_nao_casa():
    resultado = metricas.avaliar(VERDADE, _predicoes((1, (100, 100, 20, 20), 0.9)))
    assert resultado["gt"]["verdadeiros_positivos"] == 0
    assert resultado["gt"]["falsos_positivos"] == 1
    assert resultado["gt"]["falsos_negativos"] == 2
    assert resultado["map50"] == 0.0


def test_map50_95_nao_supera_map50_com_predicao_imperfeita():
    verdade = copy.deepcopy(VERDADE)
    resultado = metricas.avaliar(
        verdade,
        _predicoes((1, (12, 12, 20, 20), 0.9), (2, (10, 10, 20, 20), 0.9)),
    )
    assert resultado["map50_95"] <= resultado["map50"]


def test_validacao_humana_e_portao():
    preds = _predicoes((1, (10, 10, 20, 20), 0.9), (2, (10, 10, 20, 20), 0.9))
    sem = metricas.avaliar(VERDADE, preds, exigir_validacao_humana=True)
    assert not sem["aprovado"]
    assert any("validação humana" in motivo for motivo in sem["reprovacoes"])

    curta = metricas.avaliar(
        VERDADE,
        _predicoes(
            (1, (10, 10, 20, 20), 0.9),
            (2, (10, 10, 20, 20), 0.9),
            validacao={"aprovado": True, "amostras": 50},
        ),
        exigir_validacao_humana=True,
        min_amostras_humanas=100,
    )
    assert not curta["aprovado"]

    aprovada = metricas.avaliar(
        VERDADE,
        _predicoes(
            (1, (10, 10, 20, 20), 0.9),
            (2, (10, 10, 20, 20), 0.9),
            validacao={"aprovado": True, "amostras": 120},
        ),
        exigir_validacao_humana=True,
        min_amostras_humanas=100,
    )
    assert aprovada["aprovado"], aprovada["reprovacoes"]


def test_predicao_para_imagem_inexistente_e_erro():
    with pytest.raises(metricas.ErroAvaliacao):
        metricas.avaliar(VERDADE, _predicoes((99, (0, 0, 10, 10), 0.9)))


def test_verdade_com_score_e_erro():
    verdade = copy.deepcopy(VERDADE)
    verdade["annotations"][0]["score"] = 0.9
    with pytest.raises(metricas.ErroAvaliacao):
        metricas.avaliar(verdade, _predicoes())


def test_iou_basico():
    assert metricas.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert metricas.iou([0, 0, 10, 10], [10, 0, 10, 10]) == 0.0
    assert metricas.iou([0, 0, 10, 10], [5, 0, 10, 10]) == pytest.approx(1 / 3)


def test_cli_avaliar_reprova_sem_validacao_humana(tmp_path, capsys):
    verdade = tmp_path / "verdade.json"
    predicoes = tmp_path / "predicoes.json"
    verdade.write_text(json.dumps(VERDADE), encoding="utf-8")
    predicoes.write_text(
        json.dumps(_predicoes((1, (10, 10, 20, 20), 0.9), (2, (10, 10, 20, 20), 0.9))),
        encoding="utf-8",
    )

    codigo = cli.main(
        [
            "avaliar",
            "--verdade",
            str(verdade),
            "--predicoes",
            str(predicoes),
            "--exigir-validacao-humana",
        ]
    )

    assert codigo == 1
    assert '"aprovado": false' in capsys.readouterr().out
