from app.services.nfe_io import _adaptar_resposta_nfe_io


def test_adapter_emitente_ide_e_unidade_original():
    raw = {
        "chave_acesso": "12345678901234567890123456789012345678901234",
        "emit": {
            "xNome": "Fornecedor XYZ Ltda",
            "CNPJ": "11222333000181",
        },
        "ide": {"nNF": 4521, "serie": 2},
        "itens": [
            {
                "prod": {
                    "xProd": "Vergalhão 10mm",
                    "qCom": 50.0,
                    "uCom": "M",
                    "bitola_mm": 10,
                }
            },
        ],
    }
    out = _adaptar_resposta_nfe_io(raw)
    assert out["emitente_nome"] == "Fornecedor XYZ Ltda"
    assert out["emitente_cnpj"] == "11222333000181"
    assert out["nfe_numero"] == "4521"
    assert out["nfe_serie"] == "2"
    assert out["emitente"]["nome"] == "Fornecedor XYZ Ltda"
    assert out["emitente"]["cnpj"] == "11222333000181"
    assert len(out["itens"]) == 1
    it0 = out["itens"][0]
    assert it0["unidade_original"] == "M"
    assert it0["unidade"] == "M"
    assert it0["quantidade"] == 50.0


def test_adapter_raiz_emitente_nome_e_item_plano():
    raw = {
        "chave": "12345678901234567890123456789012345678901234",
        "emitente_nome": "ACME",
        "emitente_cnpj": "99887766000155",
        "nfe_numero": "100",
        "nfe_serie": "1",
        "items": [{"bitola_mm": 8, "quantidade": 10, "unidade": "UN", "marca": "G"}],
    }
    out = _adaptar_resposta_nfe_io(raw)
    assert out["emitente_nome"] == "ACME"
    assert out["itens"][0]["unidade_original"] == "UN"


def test_adapter_preserva_codigo_do_produto():
    """`cProd` é o que decide a correlação sem ambiguidade: perdê-lo é voltar a chutar."""
    raw = {
        "itens": [
            {"prod": {"cProd": "ACO-10-GEU", "xProd": "Vergalhão 10mm", "qCom": 500.0, "uCom": "M"}},
            {"cProd": "ACO-12-GEU", "xProd": "Vergalhão 12,5mm", "qCom": 300.0, "uCom": "M"},
            {"xProd": "Sem código", "qCom": 10.0, "uCom": "M"},
        ],
    }
    out = _adaptar_resposta_nfe_io(raw)
    assert [i["codigo_produto"] for i in out["itens"]] == ["ACO-10-GEU", "ACO-12-GEU", None]
