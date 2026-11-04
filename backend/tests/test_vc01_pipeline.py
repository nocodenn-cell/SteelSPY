"""Entrada de fotografia e recusas do pipeline do protótipo.

A entrada reusa `app.services.evidencias`: o teste garante que uma foto que a
produção rejeitaria também é recusada aqui, com o motivo registrado — e que o
protótipo não grava nada em banco nem em storage de evidências.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from exp_vc01 import pipeline


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 120, 120)).save(buf, format="PNG")
    return buf.getvalue()


def test_arquivo_inexistente_e_recusado_sem_inventar_contagem():
    laudo = pipeline.contar("nao-existe.jpg", detector="hastes")
    assert laudo["veredito"] == "RECUSADO"
    assert laudo["contagem_maquina"] == 0
    assert "não encontrado" in laudo["motivos"][0]


def test_conteudo_que_nao_e_imagem_e_recusado_pela_validacao_de_evidencia():
    laudo = pipeline.contar(b"isto nao e uma foto", detector="hastes")
    assert laudo["veredito"] == "RECUSADO"
    assert "validação de evidência" in laudo["motivos"][0]


def test_detector_desconhecido_vira_recusa_e_nao_traceback():
    laudo = pipeline.contar(_png(), detector="inexistente")
    assert laudo["veredito"] == "RECUSADO"
    assert "inexistente" in laudo["motivos"][0]


def test_fotografia_valida_guarda_os_dois_hashes_no_laudo():
    laudo = pipeline.contar(_png(), detector="inexistente")
    assert laudo["fotografia"]["sha256_original"]
    assert laudo["fotografia"]["sha256_normalizada"]
    assert laudo["fotografia"]["largura"] == 64
    assert laudo["fotografia"]["altura"] == 48


def test_gravar_saida_escreve_laudo_e_foto_marcada(tmp_path: Path):
    laudo = {
        "protocolo": "vc01-contagem/1",
        "veredito": "CONTADO",
        "contagem_maquina": 2,
        "marcas": [
            {"numero": 1, "x": 10, "y": 12, "familia": "a", "forca": 0.9},
            {"numero": 2, "x": 30, "y": 12, "familia": "a", "forca": 0.8},
        ],
        "_fotografia_bytes": _png(),
    }
    saida = pipeline.gravar_saida(laudo, tmp_path / "caso")

    assert Path(saida["laudo"]).is_file()
    assert Path(saida["foto_marcada"]).read_bytes().startswith(b"\xff\xd8\xff")
    assert "_fotografia_bytes" not in laudo, "bytes da foto não pertencem ao laudo em disco"
