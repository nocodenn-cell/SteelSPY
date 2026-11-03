"""Sprint 3 / P3: recebimento parcial, estados consistentes e trilha de transições.

O que estes testes protegem:

- "parcial" é número, não opinião: a contagem por linha decide o estado;
- o pedido nunca vira `atendido` com linha em falta, nem com divergência crítica
  esperando decisão;
- `encerrado` só existe por decisão de quem tem `encerrar_recebimento`, com
  motivo, e não fecha o pedido;
- cada transição fica na trilha com autor e horário — sem trilha não há auditoria;
- devolução abate o saldo e contagem repetida da mesma linha é recusada.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_pedidos import (  # fixtures e helpers já usados na suíte de pedidos
    _criar_fornecedor,
    _criar_pedido,
    _login,
    _nfe_com_itens,
    _post,
    cliente,  # noqa: F401  (fixture)
    equipe,  # noqa: F401  (fixture)
    storage,  # noqa: F401  (fixture)
)

from app.services.recebimentos import calcular_status_pedido, calcular_status_recebimento


def _pedido_duas_linhas(cliente: Any, equipe: dict[str, Any], csrf: str,
                        cnpj: str | None = None) -> dict[str, Any]:
    """
    Pedido de duas linhas (1000 M de CA-50 e 300 M de CA-60).

    `cnpj` é o do fornecedor: a NF-e só vincula a pedido do mesmo emitente, e a
    regra de negócio é boa demais para contornar no teste.
    """
    cnpj = cnpj or f"{uuid.uuid4().int % 10**14:014d}"
    fornecedor = _criar_fornecedor(cliente, equipe["obra_a"], csrf, cnpj=cnpj)
    r = _criar_pedido(
        cliente, equipe["obra_a"], csrf, fornecedor,
        numero=f"PC-{uuid.uuid4().hex[:6]}",
        itens=[
            {"material_tipo": "CA-50", "categoria_material": "aco", "bitola_mm": 10.0,
             "marca_exigida": "GERDAU", "quantidade": 1000.0, "unidade": "M"},
            {"material_tipo": "CA-60", "categoria_material": "aco", "bitola_mm": 12.5,
             "marca_exigida": "GERDAU", "quantidade": 300.0, "unidade": "M"},
        ],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _receber(cliente: Any, equipe: dict[str, Any], csrf: str, pedido: dict, itens: list[dict],
             **extra: Any) -> Any:
    return _post(
        cliente, f"/obras/{equipe['obra_a']}/recebimentos",
        {"pedido_id": pedido["id"], "itens": itens, **extra}, csrf,
    )


def _itens_do_pedido(cliente: Any, pedido: dict) -> list[dict]:
    corpo = cliente.get(f"/pedidos/{pedido['id']}").json()
    return corpo["itens"]


# ---------------------------------------------------------------------------
# Regra pura, sem banco
# ---------------------------------------------------------------------------


def test_estado_da_entrega_sai_da_quantidade() -> None:
    linhas = [{"id": "a", "quantidade": 1000.0}, {"id": "b", "quantidade": 300.0}]
    assert calcular_status_recebimento(linhas, {}, {"a": 600.0})[0] == "parcial"
    assert calcular_status_recebimento(linhas, {"a": 1000.0}, {"b": 300.0})[0] == "completo"
    assert calcular_status_recebimento(linhas, {}, {})[0] == "pendente"
    # Veio mais do que faltava: não é "completo", é cobrança para auditar.
    estado, motivo = calcular_status_recebimento(linhas, {"a": 900.0}, {"a": 400.0})
    assert estado == "divergente"
    assert "além do que faltava" in motivo


def test_pedido_nao_fecha_com_linha_em_falta() -> None:
    """Nunca encerrar o pedido inteiro por causa de uma entrega parcial."""
    linhas = [{"id": "a", "linha": 1, "quantidade": 1000.0}, {"id": "b", "linha": 2, "quantidade": 300.0}]
    estado, motivo = calcular_status_pedido(linhas, {"a": 1000.0}, divergencia_aberta=False)
    assert estado == "parcial"
    assert "linha 2" in motivo


def test_pedido_sobe_a_atendido_so_com_quantidade_e_sem_divergencia() -> None:
    linhas = [{"id": "a", "linha": 1, "quantidade": 1000.0}]
    coberto = {"a": 1000.0}
    assert calcular_status_pedido(linhas, coberto, divergencia_aberta=True)[0] == "parcial"
    assert calcular_status_pedido(linhas, coberto, divergencia_aberta=False)[0] == "atendido"
    assert calcular_status_pedido(linhas, {}, divergencia_aberta=False)[0] == "aberto"


# ---------------------------------------------------------------------------
# Fluxo registrado pela API
# ---------------------------------------------------------------------------


def test_entrega_parcial_registra_estado_e_trilha(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _linha2 = _itens_do_pedido(cliente, pedido)

    r = _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 600.0}])
    assert r.status_code == 200, r.text
    recebimento = r.json()
    assert recebimento["status"] == "parcial"
    assert recebimento["pedido_status"]["status"] == "parcial"

    corpo = cliente.get(f"/pedidos/{pedido['id']}").json()
    cobertura = {c["id"]: c for c in corpo["cobertura"]}
    assert cobertura[linha1["id"]]["recebido"] == 600.0
    assert cobertura[linha1["id"]]["saldo"] == 400.0
    assert cobertura[linha1["id"]]["status_recebimento"] == "parcial"

    eventos = cliente.get(f"/pedidos/{pedido['id']}/transicoes").json()["itens"]
    tipos = {(e["origem"], e["status_de"], e["status_para"]) for e in eventos}
    assert ("recebimento", None, "parcial") in tipos
    assert ("pedido", "aberto", "parcial") in tipos
    # Responsável pela transição aparece; sem isto a trilha não audita ninguém.
    assert all(e["autor_email"] == equipe["emails"]["eng"] for e in eventos)


def test_completar_o_saldo_fecha_a_entrega_e_o_pedido(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, linha2 = _itens_do_pedido(cliente, pedido)

    _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 1000.0}])
    r = _receber(
        cliente, equipe, csrf, pedido,
        [{"pedido_item_id": linha2["id"], "quantidade": 300.0}],
    )
    assert r.json()["status"] == "completo"
    assert cliente.get(f"/pedidos/{pedido['id']}").json()["status"] == "atendido"


def test_divergencia_critica_sem_decisao_impede_pedido_atendido(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """Quantidade fechada não quita o compromisso enquanto a auditoria está aberta."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_duas_linhas(cliente, equipe, csrf, cnpj=cnpj)
    linha1, linha2 = _itens_do_pedido(cliente, pedido)

    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [
            {"n_item": 1, "descricao": "VERGALHAO CA-50 10MM", "bitola_mm": 10.0,
             "marca": "GERDAU", "quantidade": 1000.0, "unidade": "M"},
            {"n_item": 2, "descricao": "VERGALHAO CA-60 12,5MM", "bitola_mm": 12.5,
             "marca": "GERDAU", "quantidade": 300.0, "unidade": "M"},
        ],
        cnpj,
    )
    vinculo = _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf)
    assert vinculo.status_code == 200, vinculo.text
    conciliacao = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf)
    assert conciliacao.status_code == 201, conciliacao.text
    conc = conciliacao.json()
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE conciliacoes SET severidade_tecnica = 'VERMELHO' WHERE id = :i"),
            {"i": conc["id"]},
        )

    r = _receber(cliente, equipe, csrf, pedido, [
        {"pedido_item_id": linha1["id"], "quantidade": 1000.0},
        {"pedido_item_id": linha2["id"], "quantidade": 300.0},
    ])
    assert r.json()["status"] == "completo"
    # A tela mostra o motivo do estado do pedido: sem esta frase, o portão veria
    # "Estado inalterado" e ninguém saberia que é a auditoria segurando o pedido.
    assert r.json()["pedido_status"]["status"] == "parcial"
    assert "conciliação crítica sem decisão" in r.json()["pedido_status"]["motivo"]
    assert cliente.get(f"/pedidos/{pedido['id']}").json()["status"] == "parcial"

    # A decisão humana é o que libera o estado final.
    _post(cliente, f"/conciliacoes/{conc['id']}/decisao",
          {"decisao": "aceita", "justificativa": "conferido no portao, material dentro do especificado"},
          csrf)
    assert cliente.get(f"/pedidos/{pedido['id']}").json()["status"] == "atendido"


def test_divergencia_critica_substituida_nao_trava_o_pedido_para_sempre(
    cliente: Any, equipe: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    Uma rodada nova reavalia o pedido inteiro; a linha anterior é trilha, não bloqueio.

    A tela de divergências mostra a conciliação mais recente e deixa as outras como
    histórico, sem formulário. Se o bloqueio olhasse todas as linhas, um pedido com
    uma conciliação crítica substituída nunca chegaria a `atendido` — o navegador
    provou exatamente isso numa obra de demonstração.
    """
    csrf = _login(cliente, equipe["emails"]["eng"])
    cnpj = f"{uuid.uuid4().int % 10**14:014d}"
    pedido = _pedido_duas_linhas(cliente, equipe, csrf, cnpj=cnpj)
    linha1, linha2 = _itens_do_pedido(cliente, pedido)

    nfe = _nfe_com_itens(
        sql_owner, equipe,
        [
            {"n_item": 1, "descricao": "VERGALHAO CA-50 10MM", "bitola_mm": 10.0,
             "marca": "GERDAU", "quantidade": 1000.0, "unidade": "M"},
            {"n_item": 2, "descricao": "VERGALHAO CA-60 12,5MM", "bitola_mm": 12.5,
             "marca": "GERDAU", "quantidade": 300.0, "unidade": "M"},
        ],
        cnpj,
    )
    assert _post(cliente, f"/pedidos/{pedido['id']}/vincular-nfe", {"nfe_log_id": str(nfe)}, csrf).status_code == 200
    velha = _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).json()
    with sql_owner.begin() as conn:
        conn.execute(
            text("UPDATE conciliacoes SET severidade_tecnica = 'VERMELHO' WHERE id = :i"),
            {"i": velha["id"]},
        )

    # Segunda rodada sobre o mesmo pedido: é ela que a tela exibe e oferece decidir.
    assert _post(cliente, f"/pedidos/{pedido['id']}/conciliar", {"nfe_log_id": str(nfe)}, csrf).status_code == 201

    _receber(cliente, equipe, csrf, pedido, [
        {"pedido_item_id": linha1["id"], "quantidade": 1000.0},
        {"pedido_item_id": linha2["id"], "quantidade": 300.0},
    ])
    assert cliente.get(f"/pedidos/{pedido['id']}").json()["status"] == "atendido"

    # A substituída continua crítica e sem decisão: o que a liberou foi a nova rodada.
    with sql_owner.connect() as conn:
        relida = conn.execute(
            text("SELECT status, severidade_tecnica FROM conciliacoes WHERE id = :i"), {"i": velha["id"]}
        ).mappings().first()
    assert (relida["status"], relida["severidade_tecnica"]) == ("em_analise", "VERMELHO")


def test_entrega_acima_do_saldo_e_divergente(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)

    r = _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 1500.0}])
    assert r.json()["status"] == "divergente"
    assert "além do que faltava" in r.json()["motivo_status"]


def test_devolucao_abate_o_saldo(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)

    _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 1000.0}])
    r = _receber(
        cliente, equipe, csrf, pedido,
        [{"pedido_item_id": linha1["id"], "quantidade": 400.0}], tipo="devolucao",
    )
    assert r.status_code == 200, r.text
    cobertura = {c["id"]: c for c in cliente.get(f"/pedidos/{pedido['id']}").json()["cobertura"]}
    assert cobertura[linha1["id"]]["recebido"] == 600.0
    assert cobertura[linha1["id"]]["status_recebimento"] == "parcial"


def test_encerrar_exige_decisao_autorizada_e_motivo(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)
    recebimento = _receber(
        cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 500.0}]
    ).json()

    # Fiscal registra no portão, não encerra entrega.
    cliente.cookies.clear()
    csrf_fiscal = _login(cliente, equipe["emails"]["fiscal"])
    r = _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
              {"motivo": "material devolvido ao fornecedor"}, csrf_fiscal)
    assert r.status_code == 403, r.text

    cliente.cookies.clear()
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    sem_motivo = _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
                       {"motivo": "abc"}, csrf_eng)
    assert sem_motivo.status_code == 422, sem_motivo.text

    ok = _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
               {"motivo": "sobra devolvida, entrega fechada no portão"}, csrf_eng)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "encerrado"

    eventos = cliente.get(f"/pedidos/{pedido['id']}/transicoes").json()["itens"]
    encerramento = [e for e in eventos if e["status_para"] == "encerrado"]
    assert len(encerramento) == 1
    assert encerramento[0]["autor_email"] == equipe["emails"]["eng"]
    assert "devolvida" in encerramento[0]["motivo"]


def test_encerrar_entrega_nao_encerra_o_pedido(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)
    recebimento = _receber(
        cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 500.0}]
    ).json()

    _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
          {"motivo": "entrega conferida e finalizada no portão"}, csrf)

    corpo = cliente.get(f"/pedidos/{pedido['id']}").json()
    assert corpo["status"] == "parcial"
    assert cliente.get(f"/pedidos/{pedido['id']}/transicoes").json()


def test_reencerrar_recebimento_encerrado_e_conflito(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)
    recebimento = _receber(
        cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 500.0}]
    ).json()
    _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
          {"motivo": "entrega conferida e finalizada no portão"}, csrf)

    r = _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
              {"motivo": "tentativa de fechar de novo"}, csrf)
    assert r.status_code == 409


def test_contagem_repetida_da_mesma_linha_no_mesmo_portao_e_recusada(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """Somar duas vezes a mesma linha inflaria o saldo — é o erro que a P0 combateu."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)

    r = _receber(cliente, equipe, csrf, pedido, [
        {"pedido_item_id": linha1["id"], "quantidade": 500.0},
        {"pedido_item_id": linha1["id"], "quantidade": 100.0},
    ])
    assert r.status_code == 409, r.text


def test_item_de_outro_pedido_e_item_sem_contagem(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    outro = _pedido_duas_linhas(cliente, equipe, csrf)
    linha_do_outro = _itens_do_pedido(cliente, outro)[0]

    r = _receber(cliente, equipe, csrf, pedido,
                 [{"pedido_item_id": linha_do_outro["id"], "quantidade": 10.0}])
    assert r.status_code == 422, r.text

    # Sem contagem, o recebimento continua sendo o carimbo do portão.
    so_carimbo = _receber(cliente, equipe, csrf, pedido, [])
    assert so_carimbo.json()["status"] == "pendente"


def test_recebimento_sem_pedido_continua_funcionando(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """O fluxo antigo de obra não é quebrado: sem pedido_id, nada de cobertura."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    r = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos", {"tipo": "entrada"}, csrf)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pendente"
    assert r.json()["pedido_id"] is None


def test_contagem_sem_pedido_id_e_recusada(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1 = _itens_do_pedido(cliente, pedido)[0]
    r = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos",
              {"itens": [{"pedido_item_id": linha1["id"], "quantidade": 10.0}]}, csrf)
    assert r.status_code == 422, r.text


def test_fiscal_do_portao_le_o_pedido_para_contar_a_entrega(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """
    Quem recebe no portão precisa saber o que foi comprado para contar o que entrou.

    O navegador pegou isto: o fiscal abriu a tela de recebimento, a lista de pedidos
    respondeu 403 e a contagem por linha ficou impossível. Ler o pedido é leitura de
    operação; o que continua com engenharia é criar, alterar e decidir.
    """
    csrf_eng = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf_eng)
    linha1 = _itens_do_pedido(cliente, pedido)[0]

    cliente.cookies.clear()
    csrf = _login(cliente, equipe["emails"]["fiscal"])
    lista = cliente.get(f"/obras/{equipe['obra_a']}/pedidos")
    assert lista.status_code == 200, lista.text
    assert pedido["numero"] in {p["numero"] for p in lista.json()["itens"]}

    detalhe = cliente.get(f"/pedidos/{pedido['id']}")
    assert detalhe.status_code == 200, detalhe.text
    assert {l["id"] for l in detalhe.json()["itens"]} >= {linha1["id"]}

    r = _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 250.0}])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "parcial"


def test_idempotencia_por_id_cliente_nao_duplica_entrega(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """Reenvio offline do mesmo registro não pode contar o ferro duas vezes."""
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1 = _itens_do_pedido(cliente, pedido)[0]
    chave = str(uuid.uuid4())
    corpo = {"pedido_id": pedido["id"], "id_cliente": chave,
             "itens": [{"pedido_item_id": linha1["id"], "quantidade": 500.0}]}

    primeiro = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos", corpo, csrf)
    segundo = _post(cliente, f"/obras/{equipe['obra_a']}/recebimentos", corpo, csrf)
    assert primeiro.json()["id"] == segundo.json()["id"]
    assert segundo.json()["criado"] is False

    cobertura = {c["id"]: c for c in cliente.get(f"/pedidos/{pedido['id']}").json()["cobertura"]}
    assert cobertura[linha1["id"]]["recebido"] == 500.0


def test_trilha_de_outra_construtora_e_invisivel(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/pedidos/{pedido['id']}/transicoes").status_code == 404
    assert cliente.get(f"/pedidos/{pedido['id']}").status_code == 404


def test_detalhe_da_entrega_traz_estado_contagem_e_quem_fechou(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    """
    A tela do portão lê o estado de uma entrega num só lugar.

    O motivo do estado mora na trilha, não na linha do recebimento — se o
    detalhe não trouxer a trilha, a tela mostra `encerrado` sem dizer quem.
    """
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)
    recebimento = _receber(
        cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 400.0}]
    ).json()

    r = cliente.get(f"/recebimentos/{recebimento['id']}")
    assert r.status_code == 200, r.text
    detalhe = r.json()
    assert detalhe["status"] == "parcial"
    assert detalhe["pedido_numero"] == pedido["numero"]
    assert detalhe["contagem"][0]["linha"] == linha1["linha"]
    assert detalhe["contagem"][0]["quantidade"] == 400.0
    assert "Parte do pedido" in detalhe["motivo_status"]

    _post(cliente, f"/recebimentos/{recebimento['id']}/encerrar",
          {"motivo": "restante chega na sexta, combinado com o fornecedor"}, csrf)

    depois = cliente.get(f"/recebimentos/{recebimento['id']}").json()
    assert depois["status"] == "encerrado"
    fechamento = [e for e in depois["eventos"] if e["status_para"] == "encerrado"]
    assert fechamento[0]["autor_email"] == equipe["emails"]["eng"]
    assert "sexta" in fechamento[0]["motivo"]


def test_detalhe_do_recebimento_respeita_tenant_e_papel(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1 = _itens_do_pedido(cliente, pedido)[0]
    recebimento = _receber(
        cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 400.0}]
    ).json()

    # Quem não tem a ação de encerrar ainda lê a entrega: ver_recebimento é
    # leitura, e o fiscal do canteiro precisa do estado antes de fotografar.
    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["admin_b"])
    assert cliente.get(f"/recebimentos/{recebimento['id']}").status_code == 404

    cliente.cookies.clear()
    _login(cliente, equipe["emails"]["fiscal"])
    assert cliente.get(f"/recebimentos/{recebimento['id']}").status_code == 200


def test_vocabulario_antigo_do_recebimento_nao_sobrevive_a_migracao(
    sql_owner: Any, cenario: dict[str, Any]
) -> None:
    """
    O CHECK novo substituiu o antigo de verdade.

    A migração remapeia `aberto`/`conferido` antes de reinstalar o CHECK. Se a
    ordem errasse, o banco que já tivesse entrega registrada recusaria a
    migração — em banco vazio ela passaria, e o upgrade quebrado só apareceria
    na obra. Este teste fixa o resultado: o vocabulário velho não entra mais.
    """
    with sql_owner.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO recebimentos (tenant_id, obra_id, tipo, status) "
                    "VALUES (:t, :o, 'entrada', 'aberto')"
                ),
                {"t": cenario["tenant_a"], "o": cenario["obra_a"]},
            )
        conn.rollback()
        # Rollback de propósito: o que importa é o CHECK, não uma linha a mais
        # aparecendo no dossiê de outro teste.
        conn.execute(
            text(
                "INSERT INTO recebimentos (tenant_id, obra_id, tipo, status) "
                "VALUES (:t, :o, 'entrada', 'parcial')"
            ),
            {"t": cenario["tenant_a"], "o": cenario["obra_a"]},
        )
        conn.rollback()


def test_dossie_traz_cobertura_e_transicoes(
    cliente: Any, equipe: dict[str, Any], storage: Any
) -> None:
    csrf = _login(cliente, equipe["emails"]["eng"])
    pedido = _pedido_duas_linhas(cliente, equipe, csrf)
    linha1, _ = _itens_do_pedido(cliente, pedido)
    _receber(cliente, equipe, csrf, pedido, [{"pedido_item_id": linha1["id"], "quantidade": 400.0}])

    dossie = cliente.get(f"/pedidos/{pedido['id']}/dossie").json()
    cobertura = {c["id"]: c for c in dossie["cobertura"]}
    assert cobertura[linha1["id"]]["recebido"] == 400.0
    assert any(e["status_para"] == "parcial" for e in dossie["transicoes"])

    pdf = cliente.get(f"/pedidos/{pedido['id']}/dossie.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
