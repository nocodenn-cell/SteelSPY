"""O dashboard só enxerga várias construtoras com credencial de back-office.

A rota da aplicação (`stellspy_app`) está sob `FORCE ROW LEVEL SECURITY`: sem
`app.tenant_id` na transação, `obras` volta vazia. O dashboard não pode
"consertar" isso pedindo BYPASSRLS para a role da API — ele precisa falhar de
forma explícita quando recebe a credencial errada. Estes testes provam as duas
pontas do diagnóstico, com conexões reais.
"""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Any

RAIZ = pathlib.Path(__file__).resolve().parents[3]


def _carregar_diagnostico() -> Any:
    caminho = RAIZ / "dashboard" / "diagnostico.py"
    spec = importlib.util.spec_from_file_location("_dashboard_diagnostico", caminho)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


diagnostico_conexao = _carregar_diagnostico().diagnostico_conexao


def test_role_da_aplicacao_sem_contexto_nao_ve_obras(sql_app: Any, cenario: dict[str, Any]) -> None:
    diag = diagnostico_conexao(sql_app)

    assert diag["usuario"] == "stellspy_app"
    assert diag["superusuario"] is False
    assert diag["bypass_rls"] is False
    assert diag["obras_visiveis"] == 0, "sem tenant, RLS deve esconder até as obras do próprio teste"


def test_credencial_de_backoffice_atravessa_tenants(sql_owner: Any, cenario: dict[str, Any]) -> None:
    diag = diagnostico_conexao(sql_owner)

    assert diag["superusuario"] or diag["bypass_rls"], (
        "a credencial do dashboard precisa enxergar além de um tenant"
    )
    assert diag["obras_visiveis"] >= 2
