"""Integração multimaterial no conferente (cimento / bloco + aço legado)."""

from app.domain.conferente import ConfigObraConferente, StatusConferencia, conferir_nf_multiplos_itens


def test_cimento_cpii_verde_quando_quantidade_confere():
    itens = [
        {
            "descricao": "CIMENTO PORTLAND CP-II 50 KG",
            "quantidade": 28.0,
            "unidade": "SC",
            "unidade_original": "SC",
        }
    ]
    espec = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "categoria_material": "cimento",
            "material_tipo": "CP-II",
            "atributos_especificos": {"tipo": "CP-II"},
            "quantidade_prevista": 28.0,
            "unidade_prevista": "sacos",
        }
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERDE.value
    assert r["itens_processados"][0]["status_item"] == StatusConferencia.VERDE.value


def test_bloco_dimensoes_verde():
    itens = [
        {
            "descricao": "BLOCO CERAMICO FURADO 19X19X39 CM",
            "quantidade": 125.0,
            "unidade": "PC",
            "unidade_original": "PC",
        }
    ]
    espec = [
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "categoria_material": "bloco",
            "material_tipo": "BLOCO",
            "atributos_especificos": {"dimensoes": "19x19x39"},
            "quantidade_prevista": 125.0,
        }
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERDE.value


def test_cimento_sem_especificacao_vermelho():
    itens = [{"descricao": "CIMENTO CP-V 50KG", "quantidade": 10, "unidade": "SC"}]
    espec = [
        {
            "material_tipo": "CA-50",
            "bitola_mm": 10.0,
            "marca_exigida": "G",
            "qtd_planejada_metros": 100.0,
        }
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERMELHO.value
    assert "cimento" in r["itens_processados"][0]["mensagem_item"].lower()


def test_aco_e_cimento_na_mesma_nf():
    itens = [
        {
            "descricao": "VERGALHAO CA-50 10MM",
            "bitola_mm": 10.0,
            "marca": "GERDAU",
            "quantidade": 61.7,
            "unidade": "KG",
        },
        {
            "descricao": "CIMENTO CP-II 50KG",
            "quantidade": 28.0,
            "unidade": "SC",
        },
    ]
    espec = [
        {
            "material_tipo": "CA-50",
            "bitola_mm": 10.0,
            "marca_exigida": "GERDAU",
            "qtd_planejada_metros": 100.0,
        },
        {
            "categoria_material": "cimento",
            "atributos_especificos": {"tipo": "CP-II"},
            "quantidade_prevista": 28.0,
        },
    ]
    r = conferir_nf_multiplos_itens(itens, espec, ConfigObraConferente(modo_aprendizado=False))
    assert r["status"] == StatusConferencia.VERDE.value
    assert r["resumo"]["total"] == 2
    assert r["resumo"]["verdes"] == 2
