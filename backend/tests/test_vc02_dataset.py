"""Contrato do dataset da Sprint 5: vazamento, hash, caminho e rótulos COCO."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from exp_vc02 import cli, dataset

CORES = ((10, 10, 10), (20, 20, 20), (30, 30, 30))


def _escrever_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados), encoding="utf-8")


def _base(tmp_path: Path) -> tuple[Path, Path, Path, list[dict], dict[str, dict]]:
    """Um dataset mínimo válido: uma obra por divisão, uma caixa por imagem."""
    raiz = tmp_path / "dados"
    itens: list[dict] = []
    rotulos: dict[str, dict] = {}
    for indice, (divisao, cor) in enumerate(zip(dataset.DIVISOES, CORES, strict=True), start=1):
        relativo = f"{divisao}/img.png"
        caminho = raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 48), cor).save(caminho)
        itens.append(
            {
                "arquivo": relativo,
                "sha256": dataset.sha256(caminho),
                "divisao": divisao,
                "obra_ref": f"obra-{divisao}",
                "largura": 64,
                "altura": 48,
            }
        )
        rotulos[divisao] = {
            "images": [{"id": indice, "file_name": relativo, "width": 64, "height": 48}],
            "categories": [{"id": 1, "name": "ponta"}],
            "annotations": [
                {"id": indice, "image_id": indice, "category_id": 1, "bbox": [10, 10, 20, 20]}
            ],
        }
    manifesto = {
        "versao": 1,
        "projeto": "steelspy-vergalhoes",
        "licenca": "interna",
        "privacidade": {"anonimizado": True},
        "imagens": itens,
    }
    manifesto_path = raiz / "manifesto.json"
    _escrever_json(manifesto_path, manifesto)
    pasta_rotulos = raiz / "rotulos"
    for divisao, dados in rotulos.items():
        _escrever_json(pasta_rotulos / f"{divisao}.json", dados)
    return raiz, manifesto_path, pasta_rotulos, itens, rotulos


def _gravar(manifesto_path: Path, itens: list[dict]) -> None:
    manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
    manifesto["imagens"] = itens
    _escrever_json(manifesto_path, manifesto)


def test_dataset_valido_passa_com_estatisticas(tmp_path: Path):
    _, manifesto, rotulos, _, _ = _base(tmp_path)
    resultado = dataset.validar(manifesto, rotulos)

    assert resultado["ok"], resultado["erros"]
    assert resultado["total_imagens"] == 3
    assert resultado["total_anotacoes"] == 3
    assert set(resultado["divisoes"]) == set(dataset.DIVISOES)
    assert resultado["divisoes"]["teste"]["categorias"] == {"ponta": 1}


def test_obra_em_duas_divisoes_e_vazamento(tmp_path: Path):
    _, manifesto, rotulos, itens, _ = _base(tmp_path)
    itens[2]["obra_ref"] = itens[0]["obra_ref"]
    _gravar(manifesto, itens)

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("vazamento por obra" in erro for erro in resultado["erros"])


def test_mesmo_hash_em_duas_divisoes_e_vazamento(tmp_path: Path):
    _, manifesto, rotulos, itens, _ = _base(tmp_path)
    itens[2]["sha256"] = itens[0]["sha256"]
    _gravar(manifesto, itens)

    resultado = dataset.validar(manifesto, rotulos, verificar_imagens=False)
    assert not resultado["ok"]
    assert any("vazamento" in erro and "idêntica" in erro for erro in resultado["erros"])


def test_imagem_ausente_e_erro(tmp_path: Path):
    raiz, manifesto, rotulos, itens, _ = _base(tmp_path)
    (raiz / itens[0]["arquivo"]).unlink()

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("imagem ausente" in erro for erro in resultado["erros"])


def test_hash_que_nao_confere_e_erro(tmp_path: Path):
    _, manifesto, rotulos, itens, _ = _base(tmp_path)
    itens[0]["sha256"] = "0" * 64
    _gravar(manifesto, itens)

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("hash" in erro and "não confere" in erro for erro in resultado["erros"])


def test_rotulo_sem_imagem_do_manifesto_e_erro(tmp_path: Path):
    _, manifesto, rotulos, _, dados = _base(tmp_path)
    dados["treino"]["images"] = []
    dados["treino"]["annotations"] = []
    _escrever_json(rotulos / "treino.json", dados["treino"])

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("sem rótulo" in erro for erro in resultado["erros"])


def test_anotacao_desconhecida_e_caixa_invalida_sao_erros(tmp_path: Path):
    _, manifesto, rotulos, _, dados = _base(tmp_path)
    dados["teste"]["annotations"] = [
        {"id": 90, "image_id": 999, "category_id": 1, "bbox": [0, 0, 5, 5]},
        {"id": 91, "image_id": 3, "category_id": 99, "bbox": [-1, 0, 10, 10]},
        {"id": 92, "image_id": 3, "category_id": 1, "bbox": [40, 40, 50, 30]},
    ]
    _escrever_json(rotulos / "teste.json", dados["teste"])

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    texto = " | ".join(resultado["erros"])
    assert "image_id desconhecido" in texto
    assert "category_id desconhecido" in texto
    assert "inválida" in texto or "ultrapassa" in texto


def test_caminho_absoluto_ou_com_pai_e_rejeitado(tmp_path: Path):
    _, manifesto, rotulos, itens, _ = _base(tmp_path)
    itens[0]["arquivo"] = "../fora.png"
    _gravar(manifesto, itens)

    resultado = dataset.validar(manifesto, rotulos, verificar_imagens=False)
    assert not resultado["ok"]
    assert any("relativo" in erro for erro in resultado["erros"])


def test_sem_anonimizacao_e_rejeitado(tmp_path: Path):
    _, manifesto, rotulos, _, _ = _base(tmp_path)
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["privacidade"]["anonimizado"] = False
    _escrever_json(manifesto, dados)

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("anonimizado" in erro for erro in resultado["erros"])


def test_verdade_nao_pode_ter_score(tmp_path: Path):
    _, manifesto, rotulos, _, dados = _base(tmp_path)
    dados["treino"]["annotations"][0]["score"] = 0.9
    _escrever_json(rotulos / "treino.json", dados["treino"])

    resultado = dataset.validar(manifesto, rotulos)
    assert not resultado["ok"]
    assert any("não leva score" in erro for erro in resultado["erros"])


def test_cli_validar_devolve_zero_para_dataset_valido(tmp_path: Path, capsys):
    _, manifesto, rotulos, _, _ = _base(tmp_path)

    codigo = cli.main(["validar", "--manifesto", str(manifesto), "--rotulos", str(rotulos)])

    assert codigo == 0
    assert '"ok": true' in capsys.readouterr().out
