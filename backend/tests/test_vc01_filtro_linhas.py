"""Filtro geométrico de filas regulares (detector `hastes`).

O filtro é a única defesa barata contra o excesso de detecção numa obra: ponta de
vergalhão aparece em fila com vão constante; prego e ripa não. Como não aprende
nada, precisa de teste explícito do que ele aceita e do que descarta.
"""

from __future__ import annotations

from exp_vc01.detectores import filtrar_regulares


def _fila(n: int, *, x0: int = 100, y: int = 200, passo: int = 20) -> list[tuple[int, int, float]]:
    return [(x0 + i * passo, y, 0.5) for i in range(n)]


def test_fila_regular_e_preservada():
    pontos = _fila(6)
    assert len(filtrar_regulares(pontos, minimo_por_linha=4)) == 6


def test_pontos_dispersos_sem_fila_sao_descartados():
    pontos = [(11, 13, 0.1), (211, 401, 0.2), (503, 77, 0.3), (97, 622, 0.4)]
    assert filtrar_regulares(pontos, minimo_por_linha=4) == []


def test_fila_curta_demais_e_descartada():
    assert filtrar_regulares(_fila(3), minimo_por_linha=4) == []


def test_vao_irregular_reprova_a_fila():
    pontos = [(100, 200, 0.5), (104, 200, 0.5), (150, 200, 0.5), (260, 200, 0.5)]
    assert filtrar_regulares(pontos, minimo_por_linha=4) == []


def test_linhas_desalinhadas_viram_duas_filas_aceitas():
    # Duas fileiras paralelas distantes: cada uma vale por si.
    pontos = _fila(4, y=100) + _fila(4, y=400)
    aceitos = filtrar_regulares(pontos, minimo_por_linha=4, tolerancia_px=6.0)
    assert len(aceitos) == 8
