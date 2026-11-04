"""Laudo do protótipo: o que fica registrado e o que a correção humana pode mudar."""

from __future__ import annotations

import io

from PIL import Image

from exp_vc01.decisao import decidir
from exp_vc01.foto import de_bytes
from exp_vc01.laudo import aplicar_correcao, marcar_na_foto, montar_laudo
from exp_vc01.tipos import Limites, Marca, ResultadoDetector


def _foto() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 90), (140, 140, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _resultado(n: int = 3) -> ResultadoDetector:
    marcas = tuple(Marca(numero=i + 1, x=20 + i * 10, y=30, familia="a", forca=0.7) for i in range(n))
    return ResultadoDetector(
        detector="teste",
        alvo="ponta",
        marcas=marcas,
        confianca=0.8,
        instabilidade=0.1,
        nota="nota do detector",
        latencia_ms={"total": 12},
        dimensoes=(120, 90),
    )


def test_laudo_carrega_os_dois_hashes_e_o_veredito():
    foto = de_bytes(_foto(), origem="teste.png")
    resultado = _resultado()
    laudo = montar_laudo(foto, resultado, decidir(resultado, Limites()), Limites(), ("limite conhecido",))

    assert laudo["protocolo"] == "vc01-contagem/1"
    assert laudo["fotografia"]["sha256_original"] == foto.sha256_original
    assert laudo["fotografia"]["sha256_normalizada"] == foto.sha256_normalizada
    assert laudo["fotografia"]["sha256_original"] != laudo["fotografia"]["sha256_normalizada"]
    assert laudo["veredito"] == "CONTADO"
    assert laudo["contagem_maquina"] == 3
    assert laudo["correcao_humana"] is None
    assert laudo["limitacoes"] == ["limite conhecido"]
    assert len(laudo["marcas"]) == 3


def test_correcao_humana_preserva_o_numero_da_maquina():
    foto = de_bytes(_foto(), origem="teste.png")
    resultado = _resultado(3)
    laudo = montar_laudo(foto, resultado, decidir(resultado, Limites()), Limites(), ())

    aplicar_correcao(laudo, contagem_humana=5, quem="fiscal@alfa.demo", motivo="duas pontas ocultas")

    assert laudo["contagem_maquina"] == 3, "a correção não pode apagar o que a máquina disse"
    assert laudo["correcao_humana"]["contagem"] == 5
    assert laudo["correcao_humana"]["delta"] == 2
    assert laudo["correcao_humana"]["quem"] == "fiscal@alfa.demo"


def test_marcacao_numerada_produz_jpeg_valido():
    foto = de_bytes(_foto(), origem="teste.png")
    marcas = tuple(Marca(numero=i + 1, x=20 + i * 15, y=40, familia="a", forca=0.9) for i in range(4))
    saida = marcar_na_foto(foto.normalizada, marcas)

    assert saida.startswith(b"\xff\xd8\xff")
    with Image.open(io.BytesIO(saida)) as img:
        assert img.size == (foto.largura, foto.altura)
