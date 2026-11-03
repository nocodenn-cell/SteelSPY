from app.services.mensagem_fiscal import gerar_mensagem_fiscal, resumo_global_texto_curto


def test_resumo_global_texto_curto():
    s = resumo_global_texto_curto(
        "VERDE",
        {"total": 3, "verdes": 3, "amarelos": 0, "vermelhos": 0},
    )
    assert "VERDE" in s
    assert "3" in s
    assert "itens" in s.lower()


def test_gerar_mensagem_verde():
    msg = gerar_mensagem_fiscal(
        "VERDE",
        {"total": 2, "verdes": 2, "amarelos": 0, "vermelhos": 0},
        [],
    )
    assert "VERDE" in msg
    assert "2/2" in msg or "2" in msg


def test_gerar_mensagem_amarelo_lista_itens():
    itens = [
        {
            "item_numero": 1,
            "material_recebido": "CA-50",
            "bitola_recebida": 10.0,
            "status_item": "AMARELO",
            "mensagem_item": "Marca divergente",
        },
        {
            "item_numero": 2,
            "material_recebido": "CA-50",
            "bitola_recebida": 10.0,
            "status_item": "VERDE",
            "mensagem_item": "OK",
        },
    ]
    msg = gerar_mensagem_fiscal(
        "AMARELO",
        {"total": 2, "verdes": 1, "amarelos": 1, "vermelhos": 0},
        itens,
    )
    assert "AMARELO" in msg
    assert "Item 1" in msg
    assert "Marca divergente" in msg


def test_gerar_mensagem_vermelho_so_bloqueantes():
    itens = [
        {
            "item_numero": 1,
            "material_recebido": "X",
            "bitola_recebida": 32.0,
            "status_item": "VERMELHO",
            "mensagem_item": "Não especificado",
        },
    ]
    msg = gerar_mensagem_fiscal(
        "VERMELHO",
        {"total": 1, "verdes": 0, "amarelos": 0, "vermelhos": 1},
        itens,
    )
    assert "VERMELHO" in msg
    assert "Item 1" in msg
