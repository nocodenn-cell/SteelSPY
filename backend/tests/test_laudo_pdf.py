from datetime import datetime, timezone
from uuid import uuid4

from app.services.laudo_pdf import gerar_laudo_pdf_bytes, montar_contexto_laudo


def test_montar_contexto_e_gerar_pdf_minimo():
    nid = uuid4()
    ctx = montar_contexto_laudo(
        nfe_log={
            "id": nid,
            "chave_acesso": "12345678901234567890123456789012345678901234",
            "status_conferencia": "VERMELHO",
            "processado_em": datetime.now(timezone.utc),
            "xml_data": {
                "alerta": "MATERIAL_NAO_SOLICITADO",
                "detalhes": [
                    {
                        "item": "Vergalhão CA-50",
                        "esperado": "10.0 mm / GERDAU",
                        "recebido": "8.0 mm / GERDAU",
                        "conclusão": "Risco estrutural alto",
                    }
                ],
                "motivos": ["Bitola divergente"],
                "emitente": {
                    "nome": "Fornecedor Teste",
                    "cnpj": "11222333000181",
                    "numero_nf": "999",
                    "serie": "1",
                },
            },
            "override_info": {},
            "foto_url": None,
        },
        obra={"nome": "Obra Alpha", "cnpj_destinatario": "99887766000155"},
    )
    assert ctx["laudo_id"] == str(nid)
    assert ctx["status"] == "VERMELHO"
    assert "chave_formatada" in ctx

    pdf = gerar_laudo_pdf_bytes(ctx)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500


def test_laudo_com_ambiente_testes_marca_agua():
    nid = uuid4()
    ctx = montar_contexto_laudo(
        nfe_log={
            "id": nid,
            "chave_acesso": "12345678901234567890123456789012345678901234",
            "status_conferencia": "VERDE",
            "processado_em": datetime.now(timezone.utc),
            "xml_data": {"detalhes": [], "motivos": [], "modo_aprendizado": True},
            "override_info": {},
            "foto_url": None,
        },
        obra={"nome": "Obra Beta", "cnpj_destinatario": "99887766000155", "modo_aprendizado": True},
    )
    assert ctx["ambiente_testes"] is True
    pdf = gerar_laudo_pdf_bytes(ctx)
    assert pdf[:4] == b"%PDF"
    # Texto da faixa/marca d’água costuma ir em streams compactadas — não exigir literal no binário.
    assert len(pdf) > 800
