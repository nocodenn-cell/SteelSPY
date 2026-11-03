from app.services.divergencias_pdf import gerar_divergencias_pdf_bytes, nome_arquivo_divergencias


def test_gerar_divergencias_pdf_minimo():
    b = gerar_divergencias_pdf_bytes(
        obra_nome="Obra",
        chave_acesso="3" * 44,
        nfe_log_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        status_nf="AMARELO",
        linhas=[
            {
                "item_numero": 1,
                "status_item": "AMARELO",
                "bitola_recebida": 10.0,
                "marca_recebida": "G",
                "quantidade_recebida": 100.0,
                "unidade_recebida": "KG",
                "divergencias": ["qtd"],
                "mensagem_item": "teste",
            }
        ],
    )
    assert b[:4] == b"%PDF"


def test_nome_arquivo_divergencias():
    assert nome_arquivo_divergencias("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").endswith(".pdf")
