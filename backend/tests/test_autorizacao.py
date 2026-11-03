"""Testes da matriz de autorização (RBAC).

Regra pura, sem banco: a permissão efetiva é a interseção do papel global com o
papel na obra. Cobrir a matriz inteira é barato e impede regressão silenciosa
de permissão — o tipo de bug que só aparece em produção, com dado de cliente.
"""

from __future__ import annotations

import pytest

from app.autorizacao import (
    ACOES,
    MATRIZ,
    PAPEIS_GLOBAIS,
    PAPEIS_OBRA,
    acoes_permitidas,
    papel_na_acao,
    pode_executar,
)

# Resposta esperada por (ação, papel). Fonte única: a matriz do produto.
ESPERADO: dict[tuple[str, str], bool] = {
    ("criar_obra", "admin_tenant"): True,
    ("criar_obra", "engenheiro"): False,
    ("criar_obra", "fiscal"): False,
    ("criar_obra", "auditor"): False,
    ("editar_especificacao", "admin_tenant"): True,
    ("editar_especificacao", "engenheiro"): True,
    ("editar_especificacao", "fiscal"): False,
    ("editar_especificacao", "auditor"): False,
    ("gerenciar_pedido", "admin_tenant"): True,
    ("gerenciar_pedido", "engenheiro"): True,
    ("gerenciar_pedido", "fiscal"): False,
    ("gerenciar_pedido", "auditor"): False,
    ("criar_recebimento", "admin_tenant"): True,
    ("criar_recebimento", "engenheiro"): True,
    ("criar_recebimento", "fiscal"): True,
    ("criar_recebimento", "auditor"): False,
    ("anexar_evidencia", "admin_tenant"): True,
    ("anexar_evidencia", "engenheiro"): True,
    ("anexar_evidencia", "fiscal"): True,
    ("anexar_evidencia", "auditor"): False,
    ("ver_evidencia", "admin_tenant"): True,
    ("ver_evidencia", "engenheiro"): True,
    ("ver_evidencia", "fiscal"): True,
    ("ver_evidencia", "auditor"): True,
    ("ver_recebimento", "admin_tenant"): True,
    ("ver_recebimento", "engenheiro"): True,
    ("ver_recebimento", "fiscal"): True,
    ("ver_recebimento", "auditor"): True,
    ("revisar_contagem", "admin_tenant"): True,
    ("revisar_contagem", "engenheiro"): True,
    ("revisar_contagem", "fiscal"): True,
    ("revisar_contagem", "auditor"): False,
    ("override", "admin_tenant"): True,
    ("override", "engenheiro"): True,
    ("override", "fiscal"): False,
    ("override", "auditor"): False,
    ("solicitar_retencao", "admin_tenant"): True,
    ("solicitar_retencao", "engenheiro"): True,
    ("solicitar_retencao", "fiscal"): False,
    ("solicitar_retencao", "auditor"): False,
    ("exportar_dossie", "admin_tenant"): True,
    ("exportar_dossie", "engenheiro"): True,
    ("exportar_dossie", "fiscal"): False,
    ("exportar_dossie", "auditor"): True,
    ("gerenciar_usuarios", "admin_tenant"): True,
    ("gerenciar_usuarios", "engenheiro"): False,
    ("gerenciar_usuarios", "fiscal"): False,
    ("gerenciar_usuarios", "auditor"): False,
}


def test_matriz_tem_48_celulas() -> None:
    """12 ações × 4 papéis. Se alguém adicionar ação sem papel, o teste avisa."""
    assert len(ACOES) == 12
    assert len(PAPEIS_GLOBAIS) == 4
    assert len(ESPERADO) == 48
    assert set(ACOES) == set(MATRIZ), "ACOES e MATRIZ precisam ter as mesmas ações"
    for acao in ACOES:
        for papel in PAPEIS_GLOBAIS:
            assert (acao, papel) in ESPERADO, f"célula ausente na especificação: {acao}/{papel}"


@pytest.mark.parametrize("acao,papel,esperado", [(a, p, e) for (a, p), e in ESPERADO.items()])
def test_papel_isolado(acao: str, papel: str, esperado: bool) -> None:
    assert papel_na_acao(papel, acao) is esperado


@pytest.mark.parametrize("acao,papel_global", [(a, p) for (a, p) in ESPERADO])
def test_sem_vinculo_com_obra_nada_e_permitido(acao: str, papel_global: str) -> None:
    """Sem vínculo na obra, nem admin_tenant passa — é o que impede acesso cruzado."""
    assert pode_executar(acao, papel_global=papel_global, papel_obra=None) is False


@pytest.mark.parametrize("acao", ACOES)
def test_intersecao_global_e_obra(acao: str) -> None:
    """A ação só passa quando os DOIS papéis permitem."""
    for global_ in PAPEIS_GLOBAIS:
        for obra in PAPEIS_OBRA:
            esperado = papel_na_acao(global_, acao) and papel_na_acao(obra, acao)
            assert pode_executar(acao, papel_global=global_, papel_obra=obra) is esperado


def test_auditor_nao_ganha_escrita_por_ser_admin_em_outra_obra() -> None:
    """admin_tenant global + auditor na obra = somente leitura naquela obra."""
    permitidas = acoes_permitidas(papel_global="admin_tenant", papel_obra="auditor")
    assert permitidas == ["ver_evidencia", "ver_recebimento", "exportar_dossie"]


def test_ver_recebimento_e_leitura_sem_escrita() -> None:
    """Ler o histórico não autoriza registrar recebimento nem anexar foto."""
    assert pode_executar("ver_recebimento", papel_global="auditor", papel_obra="auditor") is True
    assert pode_executar("criar_recebimento", papel_global="auditor", papel_obra="auditor") is False
    assert pode_executar("anexar_evidencia", papel_global="auditor", papel_obra="auditor") is False


def test_fiscal_nao_faz_override_nem_retem_pagamento() -> None:
    assert pode_executar("override", papel_global="fiscal", papel_obra="fiscal") is False
    assert pode_executar("solicitar_retencao", papel_global="fiscal", papel_obra="fiscal") is False


def test_papel_desconhecido_nao_autoriza() -> None:
    assert papel_na_acao("superusuario", "override") is False
    assert papel_na_acao(None, "override") is False
    assert papel_na_acao("admin_tenant", "acao_inexistente") is False


def test_matriz_e_a_unica_fonte() -> None:
    """A especificação do teste precisa refletir exatamente a matriz do produto."""
    for acao, por_papel in MATRIZ.items():
        for papel, permitido in por_papel.items():
            assert ESPERADO[(acao, papel)] is permitido
