"""
Conteúdo do dossiê em PDF.

O binário do fpdf2 sai com streams compactadas, então o que importa para o
auditor (chave inteira, estado atual dos itens sem pedido) é testado nas
funções que montam essas linhas, antes de irem para a página.
"""

from datetime import datetime, timezone

from app.services.dossie_pdf import (
    _faturados_sem_pedido_atual,
    _linha_nota,
    gerar_dossie_pdf_bytes,
)

CHAVE = "35240100000101010101010101010101010101010101"


def test_cabecalho_da_nota_traz_a_chave_inteira():
    linha = _linha_nota(
        {"chave_acesso": CHAVE, "processado_em": datetime(2026, 11, 3, 17, 22, tzinfo=timezone.utc)}
    )
    assert CHAVE in linha, "chave abreviada não permite conferir a NF-e original"
    assert "03/11/2026" in linha


def test_cabecalho_da_nota_sem_chave_nao_quebra():
    assert _linha_nota({}).startswith("Chave —")


def test_itens_sem_pedido_usam_a_conciliacao_mais_recente():
    """
    A lista chega em `criado_em DESC`. O item que foi correlacionado depois
    deixa de estar sem correspondência: reexibi-lo contradiria a decisão
    registrada no próprio dossiê.
    """
    conciliacoes = [
        {"criado_em": "3", "faturados_sem_pedido": [{"n_item": 3, "descricao": "ARAME"}]},
        {"criado_em": "1", "faturados_sem_pedido": [{"n_item": 3, "descricao": "ARAME"},
                                                    {"n_item": 1, "descricao": "VERGALHAO"}]},
    ]
    assert _faturados_sem_pedido_atual(conciliacoes) == [{"n_item": 3, "descricao": "ARAME"}]


def test_itens_sem_pedido_toleram_dossie_sem_conciliacao():
    assert _faturados_sem_pedido_atual([]) == []
    assert _faturados_sem_pedido_atual([{"criado_em": "1"}]) == []


def test_pdf_de_dois_conciliacoes_e_dois_hashes_sai_inteiro():
    bytes_ = gerar_dossie_pdf_bytes(
        {
            "pedido": {"numero": "PC-1", "status": "aberto"},
            "nfe": [{"chave_acesso": CHAVE, "itens": []}],
            "evidencias": [{"sha256": "a" * 64, "tipo": "material", "origem": "galeria"}],
            "conciliacoes": [
                {"status": "aceita", "severidade_tecnica": "VERMELHO",
                 "faturados_sem_pedido": [{"n_item": 3}]},
                {"status": "em_analise", "severidade_tecnica": "VERMELHO",
                 "faturados_sem_pedido": [{"n_item": 3}, {"n_item": 1}]},
            ],
        }
    )
    assert bytes_[:4] == b"%PDF"
