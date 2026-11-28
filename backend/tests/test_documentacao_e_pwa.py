"""Guardas de documentação e de arquivos não-Python (B1, B2, B3, B11, M3).

Cada teste fixa um item da revalidação de 2026-11-21 para que ele não volte.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _ler(rel: str) -> str:
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_b1_sem_linhas_vazias_em_excesso_no_relatorio_semanal() -> None:
    s = _ler("backend/app/relatorio_semanal_main.py")
    assert not re.search(r"\n[ \t]*\n[ \t]*\n[ \t]*\n", s), "mais de duas linhas vazias seguidas"


def test_b2_docstring_do_comparador_cimento_nao_promete_integracao_futura() -> None:
    assert "virá após" not in _ler("backend/app/services/comparador_cimento.py")


def test_b3_checklist_manda_aplicar_todas_as_migracoes_em_ordem() -> None:
    doc = _ler("docs/CHECKLIST_GOLIVE_SUPABASE.md")
    assert "scripts/apply_migrations.py" in doc or "supabase db push" in doc
    # a lista fixa de 5 arquivos ficava desatualizada (supabase/migrations tem dezenas)
    assert "20260410240000_obras_api_key_idempotencia.sql" not in doc


def test_b11_variaveis_e_reset_ficam_em_layer_base_e_sr_only_vem_do_tailwind() -> None:
    css = _ler("pwa/src/input.css")
    assert re.search(r"@layer base\s*\{[^@]*:root", css), ":root deve estar em @layer base"
    assert not re.search(r"@layer components\s*\{[^@]*:root", css)
    assert ".sr-only {" not in css, "sr-only deve vir do utilitário do Tailwind"


def test_m3_arquitetura_nao_promete_dicionario_de_sinonimos_ativo() -> None:
    doc = _ler("docs/ARQUITETURA.md")
    for termo in ("DICIONARIO_IA", "Dicionário sinônimos", "sinônimos com confirmação", "sinônimos iniciais"):
        assert termo not in doc, f"promessa ainda presente: {termo}"
