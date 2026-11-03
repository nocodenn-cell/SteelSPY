"""Autorização por papel (RBAC) — regra pura, sem banco e sem HTTP.

Modelo de duas camadas:

- `usuarios.papel_global` — teto do que a pessoa pode fazer na construtora;
- `obra_usuarios.papel`   — alcance dentro de cada obra.

A permissão efetiva é a **interseção** dos dois: a ação precisa ser permitida
pelo papel global E pelo papel na obra. Assim um `auditor` global vinculado
como `fiscal` numa obra não ganha poder de escrita nela, e um `admin_tenant`
vinculado como `auditor` numa obra fica só leitura ali.

Quem não tem vínculo com a obra não tem papel nenhum — e sem papel, nenhuma
ação é permitida.
"""

from __future__ import annotations

from typing import Final

PAPEIS_GLOBAIS: Final = ("admin_tenant", "engenheiro", "fiscal", "auditor")
PAPEIS_OBRA: Final = ("engenheiro", "fiscal", "auditor")

ACOES: Final = (
    "criar_obra",
    "editar_especificacao",
    "gerenciar_pedido",
    "criar_recebimento",
    "anexar_evidencia",
    "ver_evidencia",
    "revisar_contagem",
    "override",
    "solicitar_retencao",
    "exportar_dossie",
    "gerenciar_usuarios",
)

# Matriz única de verdade: ação -> papel -> permitido.
# Alterar aqui é alterar o contrato de autorização do produto.
MATRIZ: Final[dict[str, dict[str, bool]]] = {
    "criar_obra": {
        "admin_tenant": True, "engenheiro": False, "fiscal": False, "auditor": False,
    },
    "editar_especificacao": {
        "admin_tenant": True, "engenheiro": True, "fiscal": False, "auditor": False,
    },
    "gerenciar_pedido": {
        # Quem compra é engenharia/suprimentos, não o fiscal do canteiro.
        "admin_tenant": True, "engenheiro": True, "fiscal": False, "auditor": False,
    },
    "criar_recebimento": {
        "admin_tenant": True, "engenheiro": True, "fiscal": True, "auditor": False,
    },
    "anexar_evidencia": {
        "admin_tenant": True, "engenheiro": True, "fiscal": True, "auditor": False,
    },
    "ver_evidencia": {
        # Quem fotografou precisa rever a foto; quem audita precisa vê-la.
        "admin_tenant": True, "engenheiro": True, "fiscal": True, "auditor": True,
    },
    "revisar_contagem": {
        "admin_tenant": True, "engenheiro": True, "fiscal": True, "auditor": False,
    },
    "override": {
        "admin_tenant": True, "engenheiro": True, "fiscal": False, "auditor": False,
    },
    "solicitar_retencao": {
        "admin_tenant": True, "engenheiro": True, "fiscal": False, "auditor": False,
    },
    "exportar_dossie": {
        "admin_tenant": True, "engenheiro": True, "fiscal": False, "auditor": True,
    },
    "gerenciar_usuarios": {
        "admin_tenant": True, "engenheiro": False, "fiscal": False, "auditor": False,
    },
}


def papel_na_acao(papel: str | None, acao: str) -> bool:
    """O papel isolado permite a ação? Papel desconhecido ou ausente nunca permite."""
    if not papel or acao not in MATRIZ:
        return False
    return bool(MATRIZ[acao].get(papel, False))


def pode_executar(
    acao: str,
    *,
    papel_global: str | None,
    papel_obra: str | None,
) -> bool:
    """
    Permissão efetiva = interseção do papel global com o papel na obra.

    Sem vínculo com a obra (`papel_obra` None), nada é permitido — mesmo para
    `admin_tenant`. É o que impede o admin de uma construtora enxergar obra de
    outra: ele nem tem vínculo lá.
    """
    if papel_obra is None:
        return False
    return papel_na_acao(papel_global, acao) and papel_na_acao(papel_obra, acao)


def acoes_permitidas(*, papel_global: str | None, papel_obra: str | None) -> list[str]:
    """Lista as ações liberadas — útil para montar menu/UI e para auditoria."""
    if papel_obra is None:
        return []
    return [a for a in ACOES if pode_executar(a, papel_global=papel_global, papel_obra=papel_obra)]
