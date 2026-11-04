"""Comparação de migrations do HML usa o nome completo do arquivo.

Regressão: o script cortava o nome em 14 caracteres (o timestamp) e comparava
com `schema_migrations.versao` (nome completo), acusando 30 migrations
faltando mesmo com 30/30 aplicadas.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hml_staging.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("_hml_staging", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


hml = _modulo()


def test_nomes_completos_nao_geram_falso_pendente():
    locais = [
        "20261103120000_construtoras",
        "20261104160000_storage_buckets",
    ]
    diferenca = hml._diferenca_migrations(locais, set(locais))

    assert diferenca == {"faltando_no_servidor": [], "no_servidor_sem_arquivo_local": []}


def test_banco_vazio_lista_todas_as_locais():
    locais = ["20261103120000_construtoras", "20261104160000_storage_buckets"]
    diferenca = hml._diferenca_migrations(locais, set())

    assert diferenca["faltando_no_servidor"] == locais
    assert diferenca["no_servidor_sem_arquivo_local"] == []
