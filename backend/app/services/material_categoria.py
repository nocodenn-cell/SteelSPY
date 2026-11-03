"""
Heurística para sugerir categoria de material a partir da descrição do item da NF.

Não substitui cadastro na especificação; serve para roteamento futuro e dashboards.
"""

from __future__ import annotations


def detectar_categoria_material(descricao_item_nf: str | None) -> str:
    """Retorna 'aco', 'cimento', 'bloco' ou 'desconhecido'."""
    if not descricao_item_nf:
        return "desconhecido"
    d = descricao_item_nf.upper()

    if any(
        p in d
        for p in (
            "VERGALHAO",
            "VERGALHÃO",
            "CA-50",
            "CA-60",
            "CA50",
            "CA60",
            " ACO ",
            " AÇO ",
            "ACO ",
        )
    ):
        return "aco"
    if any(
        p in d
        for p in (
            "CIMENTO",
            "CP-II",
            "CP-III",
            "CP-V",
            "CP II",
            "CP V",
            "VOTORANTIM",
            "CSN CIMENTO",
        )
    ):
        return "cimento"
    if any(
        p in d
        for p in (
            "BLOCO",
            "CERAMICA",
            "CERÂMICA",
            "CONCRETO CELULAR",
            "TIJOLO",
        )
    ):
        return "bloco"

    return "desconhecido"
