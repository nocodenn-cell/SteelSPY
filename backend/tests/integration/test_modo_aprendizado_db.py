"""Achado A2, parte de banco: novas obras não nascem mais em modo de aprendizado.

O defeito original era silencioso: a obra criada com os defaults rebaixava
VERMELHO para AMARELO, e nada no fluxo avisava. Este teste trava o padrão para
que ele não volte sem alguém perceber.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text


def test_nova_obra_nasce_fora_do_modo_de_aprendizado(sql_owner: Any, cenario: dict[str, Any]) -> None:
    nova = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO obras (id, tenant_id, nome, cnpj_destinatario) "
                "VALUES (:id, :t, 'Obra Nova', :cnpj)"
            ),
            {
                "id": nova,
                "t": cenario["tenant_a"],
                "cnpj": f"{uuid.uuid4().int % 10**14:014d}",
            },
        )

    with sql_owner.connect() as conn:
        modo = conn.execute(
            text("SELECT modo_aprendizado FROM obras WHERE id = :id"), {"id": nova}
        ).scalar_one()

    assert modo is False, "obra nova não deve nascer rebaixando severidade"


def test_obra_existente_preserva_a_configuracao(sql_owner: Any, cenario: dict[str, Any]) -> None:
    """A migração não pode reescrever a escolha de obras já cadastradas."""
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE obras SET modo_aprendizado = TRUE WHERE id = :id"),
            {"id": cenario["obra_a"]},
        )

    with sql_owner.connect() as conn:
        modo = conn.execute(
            text("SELECT modo_aprendizado FROM obras WHERE id = :id"), {"id": cenario["obra_a"]}
        ).scalar_one()

    assert modo is True
