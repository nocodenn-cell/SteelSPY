"""Política de recusa do protótipo VC-01.

Estes testes rodam no venv da aplicação: a decisão não depende de cv2 nem torch,
e é justamente a parte que precisa estar certa antes de qualquer inferência.
"""

from __future__ import annotations

from exp_vc01.decisao import decidir, recusar
from exp_vc01.tipos import CONTADO, INCONCLUSIVO, RECUSADO, Limites, Marca, ResultadoDetector


def _resultado(n: int, *, confianca: float = 0.9, instabilidade: float = 0.05) -> ResultadoDetector:
    marcas = tuple(Marca(numero=i + 1, x=i * 10, y=10, familia="a", forca=0.8) for i in range(n))
    return ResultadoDetector(
        detector="teste",
        alvo="ponta",
        marcas=marcas,
        confianca=confianca,
        instabilidade=instabilidade,
        nota="",
    )


def test_contagem_dentro_dos_limites_e_afirmada():
    d = decidir(_resultado(24), Limites())
    assert d.veredito == CONTADO
    assert d.contagem == 24
    assert d.motivos == ()


def test_acima_do_teto_fisico_vira_inconclusivo():
    d = decidir(_resultado(185), Limites())
    assert d.veredito == INCONCLUSIVO
    assert any("teto calibrado" in m for m in d.motivos)


def test_confianca_baixa_vira_inconclusivo():
    d = decidir(_resultado(24, confianca=0.34), Limites())
    assert d.veredito == INCONCLUSIVO
    assert any("confiança" in m for m in d.motivos)


def test_varreduras_divergentes_viram_inconclusivo():
    d = decidir(_resultado(24, instabilidade=0.8), Limites())
    assert d.veredito == INCONCLUSIVO
    assert any("divergem" in m for m in d.motivos)


def test_contagem_zero_nao_e_afirmada():
    d = decidir(_resultado(0), Limites())
    assert d.veredito == INCONCLUSIVO
    assert d.contagem == 0


def test_recusa_carrega_o_motivo_e_nao_inventa_contagem():
    d = recusar("fotografia recusada pela validação")
    assert d.veredito == RECUSADO
    assert d.contagem == 0
    assert "validação" in d.motivos[0]


def test_limites_padrao_sao_serializaveis_no_laudo():
    assert Limites().a_dicionario() == {
        "minimo": 1,
        "maximo": 120,
        "confianca_minima": 0.55,
        "instabilidade_maxima": 0.35,
    }
