"""B12: uma obra não pode ter duas especificações para a mesma bitola.

O cenário já grava CA-50 de 10 mm (obra A); os testes usam outras bitolas.

Sem unicidade, a conferência escolhe uma das duas linhas ao acaso (ou pela ordem
de criação) e o laudo pode sair com a régua errada sem aviso. A migração
20261127120000 cria o índice único parcial (obra_id, bitola_mm) WHERE bitola_mm IS NOT NULL.
Ela aborta, sem apagar nada, se já houver duplicatas.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _inserir_especificacao(conn: Any, cenario: dict[str, Any], bitola: float | None) -> None:
    conn.execute(
        text(
            "INSERT INTO especificacoes (id, tenant_id, obra_id, material_tipo, bitola_mm, "
            "categoria_material) VALUES (:id, :t, :o, 'vergalhao', :b, 'aco')"
        ),
        {"id": uuid.uuid4(), "t": cenario["tenant_a"], "o": cenario["obra_a"], "b": bitola},
    )


def test_segunda_especificacao_com_mesma_bitola_na_mesma_obra_e_recusada(
    sql_owner: Any, cenario: dict[str, Any]
) -> None:
    with sql_owner.begin() as conn:
        _inserir_especificacao(conn, cenario, 16.0)
    with pytest.raises(IntegrityError):
        with sql_owner.begin() as conn:
            _inserir_especificacao(conn, cenario, 16.0)


def test_bitolas_diferentes_na_mesma_obra_continuam_permitidas(
    sql_owner: Any, cenario: dict[str, Any]
) -> None:
    with sql_owner.begin() as conn:
        _inserir_especificacao(conn, cenario, 16.0)
        _inserir_especificacao(conn, cenario, 20.0)


def test_bitola_nula_nao_entra_na_regra_de_unicidade(
    sql_owner: Any, cenario: dict[str, Any]
) -> None:
    with sql_owner.begin() as conn:
        _inserir_especificacao(conn, cenario, None)
        _inserir_especificacao(conn, cenario, None)
