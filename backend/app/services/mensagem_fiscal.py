"""
Mensagens para WhatsApp / PWA com resumo por item (status global = pior item).
"""

from __future__ import annotations

from typing import Any


def gerar_mensagem_fiscal(
    status_global: str,
    resumo: dict[str, int],
    itens_conferidos: list[dict[str, Any]],
) -> str:
    total = resumo.get("total", 0)
    v_ok = resumo.get("verdes", 0)
    v_am = resumo.get("amarelos", 0)
    v_vm = resumo.get("vermelhos", 0)

    if status_global == "VERDE":
        return (
            "\u2705 CONFER\u00caNCIA CONCLU\u00cdDA — STATUS: VERDE\n\n"
            f"Resumo: {v_ok}/{total} itens conferidos.\n"
            "Todos os itens est\u00e3o dentro da especifica\u00e7\u00e3o.\n\n"
            "Pode descarregar o material."
        )

    if status_global == "AMARELO":
        amarelos = [i for i in itens_conferidos if i.get("status_item") == "AMARELO"]
        linhas = "\n".join(
            f"\u26a0\ufe0f Item {i.get('item_numero')}: {i.get('material_recebido', '')} "
            f"{i.get('bitola_recebida', '')} mm — {i.get('mensagem_item', '')}"
            for i in amarelos[:15]
        )
        extra = f"\n… (+{len(amarelos) - 15} itens)" if len(amarelos) > 15 else ""
        return (
            "\u26a0\ufe0f CONFER\u00caNCIA CONCLU\u00cdDA — STATUS: AMARELO\n\n"
            f"Resumo: {v_ok} \u2705, {v_am} \u26a0\ufe0f, {v_vm} \u274c\n\n"
            "Itens com aten\u00e7\u00e3o:\n"
            f"{linhas}{extra}\n\n"
            "Recomenda\u00e7\u00e3o: validar com engenharia antes de consolidar o recebimento.\n"
            "Laudo PDF dispon\u00edvel na API (se configurado)."
        )

    vermelhos = [i for i in itens_conferidos if i.get("status_item") == "VERMELHO"]
    linhas_v = "\n".join(
        f"\u274c Item {i.get('item_numero')}: {i.get('material_recebido', '')} "
        f"{i.get('bitola_recebida', '')} mm — {i.get('mensagem_item', '')}"
        for i in vermelhos[:15]
    )
    extra_v = f"\n… (+{len(vermelhos) - 15} itens)" if len(vermelhos) > 15 else ""
    return (
        "\U0001f534 CONFER\u00caNCIA CONCLU\u00cdDA — STATUS: VERMELHO\n\n"
        f"Resumo: {v_ok} \u2705, {v_am} \u26a0\ufe0f, {v_vm} \u274c\n\n"
        "ITENS BLOQUEANTES:\n"
        f"{linhas_v}{extra_v}\n\n"
        "A\u00c7\u00c3O SUGERIDA:\n"
        "1) N\u00e3o descarregar at\u00e9 alinhamento com engenharia/fornecedor.\n"
        "2) Usar laudo PDF como registro t\u00e9cnico.\n"
        "3) Devolu\u00e7\u00e3o parcial: marcar itens no app (fase 2) e vincular NF de devolu\u00e7\u00e3o."
    )


def resumo_global_texto_curto(status: str, resumo: dict[str, int]) -> str:
    return (
        f"Status {status}: {resumo.get('verdes', 0)} verde(s), "
        f"{resumo.get('amarelos', 0)} amarelo(s), {resumo.get('vermelhos', 0)} vermelho(s) "
        f"de {resumo.get('total', 0)} itens."
    )
