"""Achado A2 — o modo de aprendizado não pode esconder a severidade técnica.

O comportamento antigo: uma divergência de 90% era rebaixada de VERMELHO para
AMARELO e o rebaixamento sobrescrevia o único campo de status. Resultado: o
fiscal via "atenção" onde a regra dizia "risco estrutural alto".

Agora existem dois campos independentes:

- `severidade_tecnica` — o que a auditoria concluiu. **Nunca** é rebaixada.
- `status` — a decisão operacional sugerida, que o modo de aprendizado pode
  rebaixar enquanto a obra está em implantação.

E três eixos separados, que antes viviam misturados no mesmo campo:
auditoria (severidade) · política de implantação (modo de aprendizado) ·
decisão humana (override).
"""

from __future__ import annotations

from app.domain.conferente import (
    ConfigObraConferente,
    StatusConferencia,
    analisar_divergencia,
    analisar_divergencia_detalhada,
    conferir_nf_multiplos_itens,
)

ESPEC = {
    "id": "00000000-0000-0000-0000-000000000001",
    "material_tipo": "CA-50",
    "bitola_mm": 10.0,
    "marca_exigida": "GERDAU",
    "qtd_planejada_metros": 100.0,
}


def _item(quantidade_kg: float) -> dict:
    return {
        "descricao": "VERGALHAO CA-50 10MM",
        "bitola_mm": 10.0,
        "marca": "GERDAU",
        "quantidade": quantidade_kg,
        "unidade": "KG",
    }


# ---------------------------------------------------------------------------
# A divergência de 90%
# ---------------------------------------------------------------------------


def test_divergencia_90_por_cento_com_modo_aprendizado() -> None:
    """
    61,7 kg em 10 mm ≈ 100 m. Entregar ~10 m é divergência de 90%.

    Antes: status AMARELO e nada mais — a severidade desaparecia.
    Agora: severidade VERMELHO preservada, operação AMARELO, e o rebaixamento
    explicitamente sinalizado.
    """
    item = _item(6.17)  # ~10 m
    cfg = ConfigObraConferente(modo_aprendizado=True)

    detalhe = analisar_divergencia_detalhada(item, ESPEC, cfg)

    assert detalhe["status_tecnico"] == StatusConferencia.VERMELHO
    assert detalhe["status"] == StatusConferencia.AMARELO
    assert detalhe["checkpoint"], "o rebaixamento precisa ser comunicado ao fiscal"
    assert any("90" in m or "89" in m for m in detalhe["motivos"]), detalhe["motivos"]
    assert any("severidade" in m.lower() for m in detalhe["motivos"])


def test_divergencia_90_por_cento_sem_modo_aprendizado() -> None:
    """Com aprendizado desligado, operação e técnica coincidem em VERMELHO."""
    detalhe = analisar_divergencia_detalhada(
        _item(6.17), ESPEC, ConfigObraConferente(modo_aprendizado=False)
    )
    assert detalhe["status_tecnico"] == StatusConferencia.VERMELHO
    assert detalhe["status"] == StatusConferencia.VERMELHO
    assert detalhe["checkpoint"] is None


def test_assinatura_antiga_continua_funcionando() -> None:
    """`analisar_divergencia` mantém o contrato de 3 valores usado em 20+ testes."""
    status, motivos, checkpoint = analisar_divergencia(
        _item(6.17), ESPEC, ConfigObraConferente(modo_aprendizado=True)
    )
    assert status == StatusConferencia.AMARELO
    assert isinstance(motivos, list) and motivos
    assert checkpoint


# ---------------------------------------------------------------------------
# Agregação: severidade não se perde ao juntar itens
# ---------------------------------------------------------------------------


def test_agregado_preserva_severidade_tecnica() -> None:
    r = conferir_nf_multiplos_itens(
        [_item(6.17)], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert r["severidade_tecnica"] == StatusConferencia.VERMELHO.value
    assert r["status"] == StatusConferencia.AMARELO.value
    assert r["decisao_operacional"] == StatusConferencia.AMARELO.value
    assert r["rebaixado_por_aprendizado"] is True
    assert r["modo_aprendizado"] is True


def test_agregado_item_verde_nao_vira_vermelho() -> None:
    r = conferir_nf_multiplos_itens(
        [_item(61.7)], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert r["severidade_tecnica"] == StatusConferencia.VERDE.value
    assert r["status"] == StatusConferencia.VERDE.value
    assert r["rebaixado_por_aprendizado"] is False


def test_item_carrega_as_duas_leituras() -> None:
    r = conferir_nf_multiplos_itens(
        [_item(6.17)], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    item = r["itens_processados"][0]
    assert item["severidade_tecnica"] == StatusConferencia.VERMELHO.value
    assert item["status_item"] == StatusConferencia.AMARELO.value


def test_o_pior_item_define_os_dois_agregados() -> None:
    """Um item crítico e um conforme: técnica é VERMELHO, operação é AMARELO."""
    item_ok = _item(61.7)
    item_ruim = _item(6.17)
    r = conferir_nf_multiplos_itens(
        [item_ok, item_ruim], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert r["severidade_tecnica"] == StatusConferencia.VERMELHO.value
    assert r["status"] == StatusConferencia.AMARELO.value
    assert r["resumo"]["vermelhos"] == 0, "operação rebaixada não deve contar como vermelho operacional"
    assert r["resumo"]["amarelos"] == 1


# ---------------------------------------------------------------------------
# Material não solicitado: crítico por definição, sem amortecedor
# ---------------------------------------------------------------------------


def test_material_nao_solicitado_mantem_severidade_critica() -> None:
    item = {**_item(61.7), "bitola_mm": 32.0}
    r = conferir_nf_multiplos_itens(
        [item], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert r["severidade_tecnica"] == StatusConferencia.VERMELHO.value
    assert r["itens_processados"][0]["severidade_tecnica"] == StatusConferencia.VERMELHO.value


# ---------------------------------------------------------------------------
# O aceite humano deixa de depender do status operacional
# ---------------------------------------------------------------------------


def test_override_permitido_quando_ha_divergencia_tecnica_mesmo_rebaixada() -> None:
    """
    Antes, `can_override` só era True com status VERMELHO — e o modo de
    aprendizado rebaixava para AMARELO, tornando o override inalcançável.
    Agora ele se apoia na severidade técnica.
    """
    com_aprendizado = conferir_nf_multiplos_itens(
        [_item(6.17)], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert com_aprendizado["can_override"] is True

    conforme = conferir_nf_multiplos_itens(
        [_item(61.7)], [ESPEC], ConfigObraConferente(modo_aprendizado=True)
    )
    assert conforme["can_override"] is False
