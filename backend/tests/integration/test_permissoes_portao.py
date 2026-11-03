"""Sprint 3 / P4: o contrato de permissões de quem trabalha no portão.

A pergunta que a demonstração vai fazer é concreta: "o fiscal do portão consegue
aprovar uma divergência, fechar a entrega ou mexer no pedido?" A resposta tem de
ser 403, e tem de ser 403 no *endpoint* — não porque o botão não apareceu no PWA.

Estes testes percorrem a API com a sessão de um fiscal e de um auditor e conferem,
endpoint por endpoint, o que a matriz de `app/autorizacao.py` promete. Dois detalhes
que já derrubaram testes antes:

- a validação de corpo roda antes da autorização, então toda requisição de negativa
  usa payload válido — corpo errado daria 422 e pareceria que a permissão passou;
- 403 é differente de 404: para os caminhos que resolvem a linha antes de autorizar,
  o objeto precisa existir, criado por quem tem direito.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.seguranca import hash_senha
from test_evidencias import _upload, imagem_png  # noqa: F401  (helpers de evidência)
from test_pedidos import (  # fixtures e helpers já usados na suíte de pedidos
    SENHA,
    _criar_fornecedor,
    _criar_pedido,
    _login,
    _nfe_com_itens,
    _post,
    cliente,  # noqa: F401  (fixture)
    equipe,  # noqa: F401  (fixture)
    storage,  # noqa: F401  (fixture)
)
from test_recebimento_parcial import _itens_do_pedido

CNPJ = f"{uuid.uuid4().int % 10**14:014d}"


def _auditor(sql_owner: Any, equipe: dict[str, Any]) -> str:
    """
    Auditor da construtora A, com vínculo de `auditor` na obra.

    O fixture `equipe` não traz auditor porque os testes de pedido nunca precisaram
    de um; aqui ele é o segundo papel do contrato, então entra pelo caminho de
    sempre — INSERT com a role dona, sem tocar no fixture compartilhado.
    """
    email = f"auditor.{uuid.uuid4().hex[:8]}@teste.local"
    uid = uuid.uuid4()
    with sql_owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                "VALUES (:id, :t, 'Dino Auditor', :e, :h, 'auditor')"
            ),
            {"id": uid, "t": equipe["tenant_a"], "e": email, "h": hash_senha(SENHA)},
        )
        conn.execute(
            text(
                "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) "
                "VALUES (:t, :o, :u, 'auditor')"
            ),
            {"t": equipe["tenant_a"], "o": equipe["obra_a"], "u": uid},
        )
    return email


def _cenario(cliente: Any, equipe: dict[str, Any], sql_owner: Any, csrf_eng: str) -> dict[str, Any]:
    """
    Pedido com NF-e vinculada, conciliação rodada, correlação criada, entrega e foto.

    Tudo montado pelo engenheiro: o que se testa é a sessão do fiscal sobre um
    cenário que já existe, não a capacidade dele de criar o cenário.
    """
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf_eng, cnpj=CNPJ)
    pedido = _criar_pedido(
        cliente, equipe["obra_a"], csrf_eng, fornecedor,
        numero=f"PC-{uuid.uuid4().hex[:6]}",
        itens=[{"material_tipo": "CA-50", "categoria_material": "aco", "bitola_mm": 10.0,
                "marca_exigida": "GERDAU", "quantidade": 1000.0, "unidade": "M"}],
    ).json()
    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [{"bitola_mm": 10.0, "quantidade": 1000.0, "unidade": "M", "marca": "GERDAU"}], CNPJ,
    )
    _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf_eng)
    conc = _post(
        cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf_eng
    ).json()
    linha = _itens_do_pedido(cliente, pedido)[0]
    corr = _post(
        cliente, f"/pedidos/{pedido['id']}/correlacoes",
        {"pedido_item_id": linha["id"], "nfe_log_id": str(nfe), "nfe_item_numero": 1},
        csrf_eng,
    ).json()
    entrega = _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos",
        {"pedido_id": pedido["id"], "tipo": "entrada", "observacoes": "chegada da manha"},
        csrf_eng,
    )
    assert entrega.status_code == 200, entrega.text
    foto = _upload(cliente, str(equipe["obra_a"]), imagem_png(), csrf=csrf_eng)
    assert foto.status_code == 201, foto.text

    return {
        "pedido": pedido, "nfe": nfe, "conciliacao": conc, "correlacao": corr,
        "entrega": entrega.json(), "foto": foto.json(), "linha": linha,
    }


def test_fiscal_le_tudo_o_que_precisa_para_contar_a_entrega(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    Leitura do fiscal é o caminho inteiro até a contagem — nada pode faltar ali.

    Se qualquer um destes GETs virar 403, a tela para de mostrar o saldo e o
    portão volta a conferir material de memória, que é o que o produto existe
    para evitar.
    """
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    c = _cenario(cliente, equipe, sql_owner, csrf_eng)

    csrf_fiscal = _login(cliente, equipe["emails"]["fiscal"])

    leituras = [
        f"/obras/{equipe['obra_a']}/pedidos",
        f"/pedidos/{c['pedido']['id']}",
        f"/obras/{equipe['obra_a']}/nfe",
        f"/pedidos/{c['pedido']['id']}/nfe",
        f"/pedidos/{c['pedido']['id']}/conciliacoes",
        f"/pedidos/{c['pedido']['id']}/transicoes",
        f"/pedidos/{c['pedido']['id']}/correlacoes",
        f"/obras/{equipe['obra_a']}/recebimentos",
        f"/recebimentos/{c['entrega']['id']}",
        f"/obras/{equipe['obra_a']}/evidencias",
        f"/evidencias/{c['foto']['id']}",
        f"/evidencias/{c['foto']['id']}/conteudo",
    ]
    for url in leituras:
        r = cliente.get(url)
        assert r.status_code == 200, f"fiscal bloqueado na leitura {url}: {r.status_code} {r.text}"

    # Registrar a entrega e fotografar são o trabalho dele — precisa continuar passando.
    # (A rota de recebimento devolve 200 mesmo na criação; o que distingue é `criado`.)
    r = _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos",
        {"pedido_id": c["pedido"]["id"], "tipo": "entrada", "observacoes": "segunda entrada"},
        csrf_fiscal,
    )
    assert r.status_code == 200, r.text
    assert r.json()["criado"] is True, "fiscal não abriu entrega nova"
    r = _upload(cliente, str(equipe["obra_a"]), imagem_png((30, 200, 30)), csrf=csrf_fiscal)
    assert r.status_code == 201, r.text

    # Rodar a conciliação é computar, não decidir: o fiscal pode, e a tela do portão
    # precisa disso para mostrar a divergência antes de chamar a engenharia. Decidir
    # o que ela aponta continua bloqueado (teste abaixo).
    r = _post(
        cliente, f"/pedidos/{c['pedido']['id']}/conciliar",
        {"nfe_log_id": str(c["nfe"])}, csrf_fiscal,
    )
    assert r.status_code == 201, r.text


def test_fiscal_nao_edita_compra_nem_aprova_divergencia(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    Toda escrita que decide algo responde 403 para o fiscal — com payload válido.

    É a lista que a demonstração precisa ler sem ambiguidade: criar fornecedor e
    pedido, vincular NF-e, correlacionar e desfazer correlação, aceitar ou rejeitar
    divergência, encerrar a entrega, fazer override da conferência e emitir o
    dossiê. Nenhuma dessas é conferência de carga.
    """
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    c = _cenario(cliente, equipe, sql_owner, csrf_eng)
    csrf_fiscal = _login(cliente, equipe["emails"]["fiscal"])

    negativas = [
        (f"/obras/{equipe['obra_a']}/fornecedores", {"cnpj": "2" * 14, "razao_social": "Outra"}),
        (
            f"/obras/{equipe['obra_a']}/pedidos",
            {"fornecedor_id": c["pedido"]["fornecedor_id"], "numero": "PC-BLOQUEADO",
             "itens": [{"material_tipo": "CA-50", "categoria_material": "aco",
                        "bitola_mm": 10.0, "marca_exigida": "GERDAU",
                        "quantidade": 10.0, "unidade": "M"}]},
        ),
        (f"/pedidos/{c['pedido']['id']}/vincular-nfe", {"nfe_log_id": str(c["nfe"])}),
        (
            f"/pedidos/{c['pedido']['id']}/correlacoes",
            {"pedido_item_id": c["linha"]["id"], "nfe_log_id": str(c["nfe"]),
             "nfe_item_numero": 1},
        ),
        (
            f"/conciliacoes/{c['conciliacao']['id']}/decisao",
            {"decisao": "aceita", "justificativa": "fiscal tentou aprovar a divergencia"},
        ),
        (
            f"/recebimentos/{c['entrega']['id']}/encerrar",
            {"motivo": "fiscal tentou encerrar a entrega sem direito"},
        ),
        (f"/override/{c['nfe']}", {"justificativa": "override indevido do portao"}),
    ]
    for url, corpo in negativas:
        r = _post(cliente, url, corpo, csrf_fiscal)
        assert r.status_code == 403, f"fiscal conseguiu escrever em {url}: {r.status_code} {r.text}"

    # Desfazer correlação e exportar o dossiê também não são do fiscal.
    r = cliente.delete(f"/correlacoes/{c['correlacao']['id']}", headers={"X-CSRF-Token": csrf_fiscal})
    assert r.status_code == 403, f"fiscal desfez correlação: {r.status_code} {r.text}"
    for url in (
        f"/pedidos/{c['pedido']['id']}/dossie",
        f"/pedidos/{c['pedido']['id']}/dossie.pdf",
        f"/conferir/{c['nfe']}/laudo.pdf",
        f"/conferir/{c['nfe']}/divergencias.pdf",
    ):
        r = cliente.get(url)
        assert r.status_code == 403, f"fiscal exportou {url}: {r.status_code} {r.text}"


def test_auditor_le_e_confere_mas_nao_registra_nem_decide(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    O auditor é a outra metade do contrato: vê tudo, inclusive o PDF, e não escreve.

    Se ele passar a registrar entrega ou encerrar recebimento, a trilha deixa de
    separar "quem viu" de "quem fez" — que é o único motivo de a trilha existir.
    """
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    c = _cenario(cliente, equipe, sql_owner, csrf_eng)
    csrf_auditor = _login(cliente, _auditor(sql_owner, equipe))

    for url in (
        f"/obras/{equipe['obra_a']}/pedidos",
        f"/pedidos/{c['pedido']['id']}",
        f"/pedidos/{c['pedido']['id']}/transicoes",
        f"/recebimentos/{c['entrega']['id']}",
        f"/evidencias/{c['foto']['id']}/conteudo",
    ):
        assert cliente.get(url).status_code == 200, f"auditor sem leitura em {url}"

    # O dossiê é o produto que ele audita: exportar é permitido a ele.
    r = cliente.get(f"/pedidos/{c['pedido']['id']}/dossie.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")

    negativas = [
        (f"/obras/{equipe['obra_a']}/recebimentos",
         {"pedido_id": c["pedido"]["id"], "tipo": "entrada"}),
        (f"/pedidos/{c['pedido']['id']}/conciliar", {"nfe_log_id": str(c["nfe"])}),
        (f"/recebimentos/{c['entrega']['id']}/encerrar",
         {"motivo": "auditor tentou encerrar a entrega"}),
        (f"/conciliacoes/{c['conciliacao']['id']}/decisao",
         {"decisao": "aceita", "justificativa": "auditor tentou decidir a divergencia"}),
    ]
    for url, corpo in negativas:
        r = _post(cliente, url, corpo, csrf_auditor)
        assert r.status_code == 403, f"auditor escreveu em {url}: {r.status_code} {r.text}"

    r = _upload(cliente, str(equipe["obra_a"]), imagem_png((0, 0, 200)), csrf=csrf_auditor)
    assert r.status_code == 403, "auditor não anexa evidência: ele confere a que existe"
