"""Isolamento nas tabelas operacionais: conferência, itens, especificações e fila.

Antes desta etapa só a identidade (construtoras, obras, usuários) era protegida
por RLS. O dado de negócio — a NF, o item conferido, a especificação e a fila —
ficava fora. Estes testes fecham essa lacuna e provam que ela continua fechada.

Mesmo padrão de prova usado antes: além de verificar que A não vê B, um teste
de mutação troca a policy por uma permissiva e exige que o vazamento apareça.
Se o vazamento não aparecer, o verde dos outros testes não estaria provando nada.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

TABELAS_OPERACIONAIS = ["nfe_logs", "nfe_itens", "especificacoes", "fila_nfe"]


# ---------------------------------------------------------------------------
# Estrutura de proteção
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabela", TABELAS_OPERACIONAIS)
def test_rls_ligado_e_forcado(sql_owner: Any, tabela: str) -> None:
    with sql_owner.connect() as conn:
        linha = conn.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"),
            {"t": tabela},
        ).one()
    assert linha.relrowsecurity is True, f"{tabela} sem RLS"
    assert linha.relforcerowsecurity is True, f"{tabela} sem FORCE ROW LEVEL SECURITY"


@pytest.mark.parametrize("tabela", TABELAS_OPERACIONAIS)
def test_tabela_operacional_tem_policy(sql_owner: Any, tabela: str) -> None:
    with sql_owner.connect() as conn:
        qtd = conn.execute(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": tabela}
        ).scalar_one()
    assert qtd >= 1, f"{tabela} com RLS e sem policy negaria tudo — e ninguém perceberia"


@pytest.mark.parametrize("tabela", TABELAS_OPERACIONAIS)
def test_tenant_id_e_obrigatorio(sql_owner: Any, tabela: str) -> None:
    with sql_owner.connect() as conn:
        anulavel = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'tenant_id'"
            ),
            {"t": tabela},
        ).scalar_one()
    assert anulavel == "NO"


# ---------------------------------------------------------------------------
# Isolamento de leitura
# ---------------------------------------------------------------------------


def test_sem_contexto_nenhuma_tabela_operacional_e_visivel(abrir_como: Any) -> None:
    with abrir_como(None) as conn:
        for tabela in TABELAS_OPERACIONAIS:
            total = conn.execute(text(f"SELECT count(*) FROM {tabela}")).scalar_one()
            assert total == 0, f"{tabela} vazou sem contexto de tenant"


def test_tenant_a_ve_apenas_seus_logs(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        ids = {r.id for r in conn.execute(text("SELECT id FROM nfe_logs"))}
    assert ids == {cenario["nfe_a"]}


def test_tenant_b_nao_alcanca_log_do_tenant_a(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_b"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM nfe_logs WHERE id = :id"), {"id": cenario["nfe_a"]}
        ).scalar_one()
    assert achou == 0


def test_tenant_a_nao_ve_itens_do_tenant_b(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM nfe_itens WHERE nfe_log_id = :l"), {"l": cenario["nfe_b"]}
        ).scalar_one()
    assert achou == 0


def test_tenant_a_nao_ve_especificacao_do_tenant_b(
    abrir_como: Any, cenario: dict[str, Any]
) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM especificacoes WHERE obra_id = :o"), {"o": cenario["obra_b"]}
        ).scalar_one()
    assert achou == 0


def test_tenant_a_nao_ve_fila_do_tenant_b(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM fila_nfe WHERE obra_id = :o"), {"o": cenario["obra_b"]}
        ).scalar_one()
    assert achou == 0


# ---------------------------------------------------------------------------
# Isolamento de escrita
# ---------------------------------------------------------------------------


def test_nao_insere_log_em_tenant_alheio(abrir_como: Any, cenario: dict[str, Any]) -> None:
    """WITH CHECK impede gravar conferência na obra de outra construtora."""
    with pytest.raises(Exception) as exc:
        with abrir_como(cenario["tenant_a"]) as conn:
            conn.execute(
                text(
                    "INSERT INTO nfe_logs (tenant_id, chave_acesso, obra_id, status_conferencia) "
                    "VALUES (:t, :k, :o, 'VERDE')"
                ),
                {"t": cenario["tenant_b"], "k": "9" * 44, "o": cenario["obra_b"]},
            )
    mensagem = str(exc.value).lower()
    assert "row-level security" in mensagem or "policy" in mensagem


def test_nao_insere_item_em_log_alheio(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with pytest.raises(Exception) as exc:
        with abrir_como(cenario["tenant_a"]) as conn:
            conn.execute(
                text(
                    "INSERT INTO nfe_itens (tenant_id, nfe_log_id, item_numero, status_item, divergencias) "
                    "VALUES (:t, :l, 99, 'VERDE', '[]'::jsonb)"
                ),
                {"t": cenario["tenant_b"], "l": cenario["nfe_b"]},
            )
    mensagem = str(exc.value).lower()
    assert "row-level security" in mensagem or "policy" in mensagem


# ---------------------------------------------------------------------------
# Fila multi-tenant: o worker começa sem contexto
# ---------------------------------------------------------------------------


def test_claim_do_worker_alcanca_varios_tenants(abrir_como: Any, cenario: dict[str, Any]) -> None:
    """
    O worker não tem tenant na sessão. O claim precisa atravessar os tenants
    e devolver o `tenant_id` de cada linha — é o que permite abrir contexto
    item a item sem dar BYPASSRLS à role da aplicação.
    """
    with abrir_como(None) as conn:
        linhas = conn.execute(
            text("SELECT id, tenant_id FROM fila_reivindicar_lote(10)")
        ).fetchall()

    tenants = {r.tenant_id for r in linhas}
    assert cenario["tenant_a"] in tenants
    assert cenario["tenant_b"] in tenants


def test_claim_marca_como_processando(abrir_como: Any, cenario: dict[str, Any]) -> None:
    with abrir_como(None) as conn:
        conn.execute(text("SELECT fila_reivindicar_lote(10)"))

    # Depois do claim, as linhas saem de 'pendente' — visível só com contexto.
    with abrir_como(cenario["tenant_a"]) as conn:
        status = conn.execute(
            text("SELECT status FROM fila_nfe WHERE obra_id = :o"), {"o": cenario["obra_a"]}
        ).scalar_one()
    assert status == "processando"


def test_worker_processa_dois_tenants_no_mesmo_tick(
    sessao_app_factory: Any, cenario: dict[str, Any]
) -> None:
    """
    Exercita o fluxo real do worker: claim multi-tenant, abre contexto por
    item, e grava a próxima tentativa sob RLS.

    `buscar_xml` devolve None de propósito — simula XML ainda indisponível, que
    é justamente o caminho que reagenda a linha.
    """
    from app.services.fila_retentativa import processar_tick_fila
    from app.tenant import vincular_sessao

    session = sessao_app_factory()
    try:
        resultados = processar_tick_fila(session, buscar_xml=lambda _chave: None)
    finally:
        session.close()

    reagendados = [r for r in resultados if r["resultado"] == "reagendado"]
    chaves = {r["chave_acesso"] for r in reagendados}
    assert "1" * 44 in chaves
    assert "2" * 44 in chaves

    # E o estado final continua isolado por tenant.
    session = sessao_app_factory()
    try:
        vincular_sessao(session, cenario["tenant_a"])
        linhas = session.execute(
            text("SELECT chave_acesso, tentativas FROM fila_nfe WHERE obra_id = :o"),
            {"o": cenario["obra_a"]},
        ).all()
        assert len(linhas) == 1
        assert linhas[0].chave_acesso == "1" * 44
        assert linhas[0].tentativas == 1
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Escrita ponta a ponta: a conferência real grava sob RLS
# ---------------------------------------------------------------------------


def test_conferencia_real_grava_com_tenant_correto(
    sessao_app_factory: Any, cenario: dict[str, Any], sql_owner: Any, abrir_como: Any
) -> None:
    """
    Exercita o caminho de escrita de produção: carrega a obra (bootstrap),
    lê as especificações sob RLS, grava `nfe_logs` e `nfe_itens`.

    Se o tenant não fosse propagado, o INSERT falharia no WITH CHECK ou o item
    ficaria invisível para o próprio dono.
    """
    from app.services.conferencia_persist import gravar_conferencia_com_xml
    from app.tenant import resolver_tenant_de_obra

    chave = "5" * 44
    session = sessao_app_factory()
    try:
        resolvido = resolver_tenant_de_obra(session, cenario["obra_a"])
        assert resolvido is not None and resolvido["tenant_id"] == cenario["tenant_a"]

        payload = {
            "emitente_nome": "Fornecedor Teste",
            "itens": [
                {
                    "descricao": "VERGALHAO CA-50 10MM",
                    "bitola_mm": 10.0,
                    "marca": "GERDAU",
                    "quantidade": 61.7,
                    "unidade": "KG",
                }
            ],
        }
        nfe_log_id, resultado = gravar_conferencia_com_xml(
            session,
            obra_id=cenario["obra_a"],
            chave=chave,
            payload=payload,
            foto_url=None,
            tipo="entrada",
            nf_original_id=None,
        )
        session.commit()
    finally:
        session.close()

    assert nfe_log_id is not None
    assert resultado["status"] == "VERDE"

    # Gravado com o tenant certo — conferido pela role dona, sem RLS.
    with sql_owner.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT n.tenant_id AS log_tenant, i.tenant_id AS item_tenant "
                "FROM nfe_logs n LEFT JOIN nfe_itens i ON i.nfe_log_id = n.id "
                "WHERE n.id = :id"
            ),
            {"id": str(nfe_log_id)},
        ).one()
    assert linha.log_tenant == cenario["tenant_a"]
    assert linha.item_tenant == cenario["tenant_a"]

    # E o tenant B continua sem enxergá-lo.
    with abrir_como(cenario["tenant_b"]) as conn:
        achou = conn.execute(
            text("SELECT count(*) FROM nfe_logs WHERE id = :id"), {"id": str(nfe_log_id)}
        ).scalar_one()
    assert achou == 0


# ---------------------------------------------------------------------------
# Mutação: a policy de nfe_logs é o que segura o dado de negócio
# ---------------------------------------------------------------------------


def test_mutacao_remover_policy_de_nfe_logs_faz_o_isolamento_falhar(
    sql_owner: Any, abrir_como: Any, cenario: dict[str, Any]
) -> None:
    with abrir_como(cenario["tenant_a"]) as conn:
        antes = conn.execute(
            text("SELECT count(*) FROM nfe_logs WHERE id = :id"), {"id": cenario["nfe_b"]}
        ).scalar_one()
    assert antes == 0, "pré-condição: o log de B não deveria estar visível para A"

    try:
        with sql_owner.begin() as conn:
            conn.execute(text("DROP POLICY p_nfe_logs_tenant ON nfe_logs"))
            conn.execute(
                text("CREATE POLICY p_nfe_logs_mutacao ON nfe_logs USING (true) WITH CHECK (true)")
            )

        with abrir_como(cenario["tenant_a"]) as conn:
            depois = conn.execute(
                text("SELECT count(*) FROM nfe_logs WHERE id = :id"), {"id": cenario["nfe_b"]}
            ).scalar_one()
        assert depois == 1, "com a policy removida o vazamento DEVERIA acontecer"
    finally:
        with sql_owner.begin() as conn:
            conn.execute(text("DROP POLICY IF EXISTS p_nfe_logs_mutacao ON nfe_logs"))
            conn.execute(
                text(
                    "CREATE POLICY p_nfe_logs_tenant ON nfe_logs "
                    "USING (tenant_id = tenant_atual()) "
                    "WITH CHECK (tenant_id = tenant_atual())"
                )
            )

    with abrir_como(cenario["tenant_a"]) as conn:
        restaurado = conn.execute(
            text("SELECT count(*) FROM nfe_logs WHERE id = :id"), {"id": cenario["nfe_b"]}
        ).scalar_one()
    assert restaurado == 0, "a policy restaurada precisa voltar a bloquear"
