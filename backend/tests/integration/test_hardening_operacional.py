"""Sprint 3 / P4: hardening operacional.

Estes testes não exercitam funcionalidade nova — exercitam o que acontece quando a
infraestrutura falha no meio de uma operação. O produto roda no portão, com celular
e rede ruim, então uma falha mal traduzida vira "o sistema está quebrado" para quem
precisa registrar a entrega. Os três compromissos protegidos aqui:

- banco fora do ar é 503 com `Retry-After`, nunca 500, e nunca leva a string do
  driver (host, porta, usuário, SQL) para o corpo da resposta;
- dois uploads simultâneos da mesma operação não produzem duas provas: o índice
  único decide e o perdedor devolve a evidência do vencedor;
- se o banco falha depois de os arquivos já estarem no disco, não sobra linha
  apontando para um arquivo que ninguém consegue ler.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from test_evidencias import (  # fixtures e helpers já usados na suíte de evidências
    _login,
    _upload,
    cliente,  # noqa: F401  (fixture)
    imagem_png,  # noqa: F401  (helper)
    storage,  # noqa: F401  (fixture)
    usuarios,  # noqa: F401  (fixture)
)

from app.services import armazenamento as arm

# Porta sem nada escutando: a recusa vem do sistema operacional, não de um mock.
PORTA_FECHADA = 59432
URL_FORA_DO_AR = (
    f"postgresql+psycopg2://stellspy_app:descartavel@127.0.0.1:{PORTA_FECHADA}/stellspy"
)


def _override_de_sessao(cliente: Any, fabrica: Any) -> Any:
    """
    Troca a fábrica de sessões da aplicação pela do teste, devolvendo o reset.

    `app` é singleton de módulo, então a substituição precisa ser desfeita — os
    testes deste diretório compartilham o mesmo `TestClient`.
    """
    from app.db import get_db
    from app.main import app

    def _get_db():
        session = fabrica()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    return _get_db


# ---------------------------------------------------------------------------
# 1. Banco indisponível de verdade
# ---------------------------------------------------------------------------


def test_banco_realmente_indisponivel_responde_503(cliente: Any) -> None:
    """
    Conexão recusada pelo servidor, não exceção montada em objeto falso.

    A diferença importa: é a mensagem do driver psycopg2 que carrega host, porta
    e usuário — e é ela que não pode aparecer na tela do portão.
    """
    engine = create_engine(URL_FORA_DO_AR, pool_pre_ping=True)
    fabrica = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    _override_de_sessao(cliente, fabrica)
    try:
        r = cliente.post("/auth/login", json={"email": "ninguem@alfa.test", "senha": "x"})
    finally:
        from app.db import get_db
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        engine.dispose()

    assert r.status_code == 503, r.text
    assert int(r.headers["retry-after"]) > 0
    texto = r.text.lower()
    for proibido in (
        "psycopg2",
        "operationalerror",
        "connection refused",
        str(PORTA_FECHADA),
        "127.0.0.1",
        "stellspy",
        "descartavel",
        "select",
    ):
        assert proibido not in texto, f"a resposta vazou `{proibido}`: {r.text}"


def test_pool_esgotado_responde_503(cliente: Any, sql_app: Any) -> None:
    """
    Banco lento é pior que banco fora: as requisições param de receber conexão.

    O sintoma que a fila vê é `sqlalchemy.exc.TimeoutError`, um tipo que não é
    `OperationalError`. Sem tratá-lo, o celular receberia 500 em cascata enquanto
    o banco está apenas congestionado — e 500 não tem `Retry-After`.
    """
    apertado = create_engine(
        sql_app.url.render_as_string(hide_password=False),
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    preso = apertado.connect()  # consome a única conexão do pool
    fabrica = sessionmaker(bind=apertado, autocommit=False, autoflush=False, class_=Session)
    _override_de_sessao(cliente, fabrica)
    try:
        r = cliente.post("/auth/login", json={"email": "ninguem@alfa.test", "senha": "x"})
    finally:
        from app.db import get_db
        from app.main import app

        app.dependency_overrides.pop(get_db, None)
        preso.close()
        apertado.dispose()

    assert r.status_code == 503, r.text
    assert int(r.headers["retry-after"]) > 0
    assert "queuepool" not in r.text.lower()
    assert "timeout" not in r.text.lower()


# ---------------------------------------------------------------------------
# 2. Corrida de idempotency_key
# ---------------------------------------------------------------------------


class _BackendComBarreira:
    """
    Sincroniza as threads logo antes do INSERT de cada evidência.

    Sem isto a corrida dependia de sorte: com a barreira dentro da gravação, todas
    as requisições passam pelo `SELECT` de idempotência ainda vazio e disputam o
    índice único — que é exatamente o caminho que se quer provar, não o reenvio
    sequencial que já tem teste.
    """

    def __init__(self, real: Any, barreira: threading.Barrier) -> None:
        self.real = real
        self.barreira = barreira

    def gravar(self, chave: str, dados: bytes) -> None:
        self.real.gravar(chave, dados)
        self.barreira.wait(timeout=30)

    def ler(self, chave: str) -> bytes:
        return self.real.ler(chave)

    def existe(self, chave: str) -> bool:
        return self.real.existe(chave)

    def remover(self, chave: str) -> None:
        self.real.remover(chave)


def test_idempotency_key_em_corrida_grava_uma_unica_evidencia(
    cliente: Any, usuarios: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    obra = str(usuarios["obra_a"])
    chave_operacao = f"cam-{uuid.uuid4().hex}"
    imagem = imagem_png()
    paralelas = 4

    arm.definir_backend(_BackendComBarreira(storage, threading.Barrier(paralelas)))
    with ThreadPoolExecutor(max_workers=paralelas) as pool:
        respostas = list(
            pool.map(
                lambda _: _upload(
                    cliente, obra, imagem, csrf=csrf,
                    dados_extra={"idempotency_key": chave_operacao},
                ),
                range(paralelas),
            )
        )

    assert all(r.status_code in (200, 201) for r in respostas), [r.text for r in respostas]
    ids = {r.json()["id"] for r in respostas}
    assert len(ids) == 1, f"corrida produziu evidências diferentes: {ids}"

    vencedoras = [r for r in respostas if r.json()["criada"]]
    assert len(vencedoras) == 1, "só uma requisição pode criar; as outras são retry"
    assert vencedoras[0].status_code == 201
    assert all(r.status_code == 200 for r in respostas if r not in vencedoras)

    with sql_owner.connect() as conn:
        linhas = conn.execute(
            text("SELECT id FROM evidencias WHERE idempotency_key = :k"),
            {"k": chave_operacao},
        ).mappings().all()
        eventos = conn.execute(
            text("SELECT count(*) FROM evidencia_eventos WHERE evidencia_id = :e"),
            {"e": str(ids.pop())},
        ).scalar_one()
    assert len(linhas) == 1
    assert eventos == 2, "a trilha é da criação; perdedores da corrida não duplicam eventos"

    # Cada upload grava dois objetos (original + normalizada). Os perdedores têm de
    # limpar os seus — se sobrar arquivo sem linha, a prova some do dossiê sem aviso.
    arquivos = sorted(p.name for p in storage.raiz.rglob("*") if p.is_file())
    assert len(arquivos) == 2, f"objetos órfãos da corrida: {arquivos}"


# ---------------------------------------------------------------------------
# 3. Banco falha depois de o arquivo já ter sido gravado
# ---------------------------------------------------------------------------


class _SessaoQuePerdeODaoNoInsert:
    """Sessão real até o `INSERT INTO evidencias`; nesse ponto o banco cai."""

    def __init__(self, real: Session) -> None:
        self.real = real

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if "INSERT INTO evidencias" in str(statement):
            raise OperationalError(
                str(statement), {}, Exception("server closed the connection unexpectedly")
            )
        return self.real.execute(statement, *args, **kwargs)

    def __getattr__(self, nome: str) -> Any:
        return getattr(self.real, nome)


def test_banco_que_falha_depois_de_gravar_o_arquivo_nao_deixa_linha_quebrada(
    cliente: Any,
    usuarios: dict[str, Any],
    storage: Any,
    sql_owner: Any,
    sessao_app_factory: Any,
) -> None:
    """
    A ordem gravar-arquivos → gravar-linha é o que torna a operação recuperável.

    Se o banco cai no INSERT, a linha não existe: nada aponta para arquivo
    inexistente, e o celular vê 503 com retry em vez de 500 com stack trace. Os
    dois objetos ficam no disco de propósito (documentado em `services/evidencias.py`):
    órfão detectável é preferível a destruir a prova sem certeza de que a
    transação falhou — um commit pode ter sido aplicado mesmo com a conexão perdida.
    """
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    obra = str(usuarios["obra_a"])

    def _fabrica() -> Any:
        return _SessaoQuePerdeODaoNoInsert(sessao_app_factory())

    _override_de_sessao(cliente, _fabrica)
    try:
        r = _upload(
            cliente, obra, imagem_png(), csrf=csrf,
            dados_extra={"idempotency_key": f"cam-{uuid.uuid4().hex}"},
        )
    finally:
        from app.db import get_db
        from app.main import app

        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 503, r.text
    assert "insert" not in r.text.lower() and "evidencias" not in r.text.lower()

    with sql_owner.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM evidencias WHERE obra_id = :o"), {"o": obra}
        ).scalar_one()
        oarfas = conn.execute(
            text("""
                SELECT count(*) FROM evidencia_eventos ee
                WHERE NOT EXISTS (SELECT 1 FROM evidencias e WHERE e.id = ee.evidencia_id)
            """),
        ).scalar_one()
    assert total == 0, "linha sem arquivo é a prova corrompida; não pode existir"
    assert oarfas == 0, "a trilha é gravada na mesma transação: não sobra evento órfão"

    arquivos = [p for p in storage.raiz.rglob("*") if p.is_file()]
    assert len(arquivos) == 2, (
        "os objetos sobrevivem à falha do banco por decisão documentada — "
        "mudar isto exige justificar o risco de apagar prova de um commit aplicado"
    )


# ---------------------------------------------------------------------------
# 4. Armazenamento falhando no lado da leitura
# ---------------------------------------------------------------------------


def test_objeto_sumido_do_disco_responde_503_sem_revelar_caminho(
    cliente: Any, usuarios: dict[str, Any], storage: Any
) -> None:
    """
    A linha existe e o arquivo não: falha de storage, não 404 e não stack trace.

    É o cenário do volume que voltou offline. O auditor precisa saber que a prova
    está indisponível — e a chave interna do objeto (tenant/obra/evidência) não
    pode aparecer na resposta, porque é caminho de disco.
    """
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    for p in list(storage.raiz.rglob("*")):
        if p.is_file():
            p.unlink()

    for variante in ("normalizada", "original"):
        r = cliente.get(f"/evidencias/{criada['id']}/conteudo", params={"variante": variante})
        assert r.status_code == 503, r.text
        assert "indisponível" in r.json()["detail"].lower()
        assert "armazenamento" in r.json()["detail"].lower()
        assert str(storage.raiz) not in r.text
        assert "\\" not in r.text, f"caminho de disco vazou na variante {variante}"

    # O metadado continua consultável: o dossiê precisa mostrar que a prova existe
    # e está indisponível, não que a evidência nunca existiu.
    assert cliente.get(f"/evidencias/{criada['id']}").status_code == 200


def test_objeto_adulterado_nao_e_servido_nem_registrado_como_download(
    cliente: Any, usuarios: dict[str, Any], storage: Any, sql_owner: Any
) -> None:
    """
    Se o conteúdo não bate com o hash gravado, o sistema recusa em vez de servir.

    Servir o arquivo corrompido seria emitir prova falsa com carimbo de origina.
    E a recusa não pode entrar na trilha como download: ninguém baixou nada.
    """
    csrf = _login(cliente, usuarios["emails"]["fiscal"])
    criada = _upload(cliente, str(usuarios["obra_a"]), imagem_png(), csrf=csrf).json()

    original = next(p for p in storage.raiz.rglob("*") if p.is_file() and "original" in p.name)
    adulterado = original.read_bytes() + b"\x00corrompido"
    original.write_bytes(adulterado)

    r = cliente.get(f"/evidencias/{criada['id']}/conteudo", params={"variante": "original"})
    assert r.status_code == 500, r.text
    assert "Integridade" in r.json()["detail"]
    assert r.content != adulterado, "o bytes adulterados não podem sair pela API"

    with sql_owner.connect() as conn:
        baixadas = conn.execute(
            text("SELECT count(*) FROM evidencia_eventos WHERE evidencia_id = :e AND tipo = 'baixada'"),
            {"e": criada["id"]},
        ).scalar_one()
    assert baixadas == 0, "recusa por integridade não é download"

    # A variante íntegra continua servível: a falha é de um objeto, não da evidência.
    ok = cliente.get(f"/evidencias/{criada['id']}/conteudo")
    assert ok.status_code == 200, ok.text
