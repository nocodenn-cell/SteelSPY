"""Banco de demonstração do PWA (usado pelo teste E2E no navegador).

Por que existe: provar o fluxo real no celular exige um PostgreSQL com dados
de verdade — duas construtoras, uma obra, um pedido com duas linhas de 10 mm
(é o caso que contava o mesmo ferro duas vezes) e duas NF-e faturando esse
pedido. Fazer isso no banco da suíte de testes apagaria o schema que todos os
370 testes usam.

O script é destrutivo por desenho, mas só com o banco que ele cria
(`stellspy_demo`). Ele nunca abre o banco `stellspy`.

    python scripts/seed_demo.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg2

RAIZ_REPO = Path(__file__).resolve().parents[2]
DIR_MIGRACOES = RAIZ_REPO / "supabase" / "migrations"
sys.path.insert(0, str(RAIZ_REPO / "backend"))

HOST = os.getenv("STELLSPY_DEMO_HOST", "localhost:55432")
OWNER = os.getenv("STELLSPY_DEMO_OWNER", "stellspy_owner")
SENHA = os.getenv("STELLSPY_DEMO_PASSWORD", "stellspy_dev")
BANCO = os.getenv("STELLSPY_DEMO_DB", "stellspy_demo")

# Senha única de demonstração. Em produção o segredo vem do secret manager e
# o banco tem outro dono; nada disto é credencial de ambiente real.
SENHA_DEMO = os.getenv("STELLSPY_DEMO_SENHA", "SenhaForte#123")


def _url(banco: str) -> str:
    return f"postgresql://{OWNER}:{SENHA}@{HOST}/{banco}"


def criar_banco() -> None:
    con = psycopg2.connect(_url("postgres"))
    con.autocommit = True
    try:
        with con.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{BANCO}" WITH (FORCE)')
            cur.execute(f'CREATE DATABASE "{BANCO}"')
    finally:
        con.close()


def migrar() -> None:
    spec = importlib.util.spec_from_file_location(
        "_apply_migrations", RAIZ_REPO / "backend" / "scripts" / "apply_migrations.py"
    )
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    if modulo.main(["--url", _url(BANCO), "--dir", str(DIR_MIGRACOES)]) != 0:
        raise SystemExit("as migrações falharam no banco de demonstração")


def _cnpj(serie: int) -> str:
    return f"{serie:012d}{uuid.uuid4().int % 100:02d}"[:14]


def semear() -> dict[str, str]:
    from app.seguranca import hash_senha

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    obra_a, obra_b = uuid.uuid4(), uuid.uuid4()
    fornecedor, pedido = uuid.uuid4(), uuid.uuid4()
    nota_cheia, nota_parcial = uuid.uuid4(), uuid.uuid4()
    chave_1 = f"{uuid.uuid4().int % 10**44:044d}"
    chave_2 = f"{uuid.uuid4().int % 10**44:044d}"
    cnpj_fornecedor = _cnpj(11)

    usuarios = {
        "eng@alfa.demo": ("Engenheira Marta", "admin_tenant", "engenheiro", tenant_a, obra_a),
        "almox@alfa.demo": ("Almoxarife Jonas", "fiscal", "fiscal", tenant_a, obra_a),
        "auditor@alfa.demo": ("Auditor Paulo", "auditor", "auditor", tenant_a, obra_a),
        "outra@beta.demo": ("Admin Beta", "admin_tenant", "engenheiro", tenant_b, obra_b),
    }

    # Duas linhas de 10 mm no mesmo pedido: a associação por bitola, sozinha,
    # não decide a qual linha pertencem os 1.000 m e os 500 m faturados.
    linhas = [
        (1, "CA-50", 10.0, "GERDAU", 1000.0, "M", "AB-10-01"),
        (2, "CA-50", 10.0, "GERDAU", 500.0, "M", "AB-10-01"),
        (3, "CA-60", 12.5, "GERDAU", 300.0, "M", "AB-125-01"),
    ]

    itens_nota_1 = [
        (1, "VERGALHAO CA-50 10MM", 10.0, "GERDAU", 1000.0, "M", "VERDE"),
        (2, "VERGALHAO CA-50 10MM", 10.0, "GERDAU", 500.0, "M", "VERDE"),
        (3, "ARAME RECOZIDO 18BWG", None, None, 40.0, "KG", "VERMELHO"),
    ]
    itens_nota_2 = [(1, "VERGALHAO CA-60 12,5MM", 12.5, "GERDAU", 120.0, "M", "VERMELHO")]

    senha_hash = hash_senha(SENHA_DEMO)
    con = psycopg2.connect(_url(BANCO))
    try:
        with con, con.cursor() as cur:
            cur.execute(
                "INSERT INTO construtoras (id, nome, cnpj, slug) VALUES "
                "(%s, 'Construtora Alfa Engenharia', %s, 'alfa'), "
                "(%s, 'Construtora Beta Ltda', %s, 'beta')",
                (str(tenant_a), _cnpj(22), str(tenant_b), _cnpj(33)),
            )
            cur.execute(
                "INSERT INTO obras (id, tenant_id, nome, cnpj_destinatario, api_key, modo_aprendizado) VALUES "
                "(%s, %s, 'Residencial Aurora — Torre Norte', %s, %s, false), "
                "(%s, %s, 'Obra Beta 1', %s, %s, false)",
                (
                    str(obra_a), str(tenant_a), _cnpj(22), f"demo-{uuid.uuid4().hex[:12]}",
                    str(obra_b), str(tenant_b), _cnpj(33), f"demo-{uuid.uuid4().hex[:12]}",
                ),
            )
            for email, (nome, papel_global, papel_obra, tenant, obra) in usuarios.items():
                uid = uuid.uuid4()
                cur.execute(
                    "INSERT INTO usuarios (id, tenant_id, nome, email, senha_hash, papel_global) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(uid), str(tenant), nome, email, senha_hash, papel_global),
                )
                cur.execute(
                    "INSERT INTO obra_usuarios (tenant_id, obra_id, usuario_id, papel) VALUES (%s, %s, %s, %s)",
                    (str(tenant), str(obra), str(uid), papel_obra),
                )
            cur.execute(
                "INSERT INTO fornecedores (id, tenant_id, cnpj, razao_social, nome_fantasia) "
                "VALUES (%s, %s, %s, 'Aço Brasil S/A', 'AcoBrasil')",
                (str(fornecedor), str(tenant_a), cnpj_fornecedor),
            )
            cur.execute(
                "INSERT INTO pedidos_compra (id, tenant_id, obra_id, fornecedor_id, numero, status, "
                "valor_total, emitido_em, previsao_entrega) VALUES "
                "(%s, %s, %s, %s, 'PC-2026-0117', 'aberto', 482500.00, CURRENT_DATE - 6, CURRENT_DATE + 1)",
                (str(pedido), str(tenant_a), str(obra_a), str(fornecedor)),
            )
            for linha, material, bitola, marca, qtd, unidade, codigo in linhas:
                cur.execute(
                    "INSERT INTO pedido_itens (id, tenant_id, pedido_id, linha, material_tipo, "
                    "categoria_material, bitola_mm, marca_exigida, quantidade, unidade, "
                    "codigo_produto_fornecedor) VALUES (%s, %s, %s, %s, %s, 'aco', %s, %s, %s, %s, %s)",
                    (
                        str(uuid.uuid4()), str(tenant_a), str(pedido), linha, material,
                        bitola, marca, qtd, unidade, codigo,
                    ),
                )
            for nfe_id, chave, status, resumo, horas, itens in (
                (nota_cheia, chave_1, "AMARELO", "3 itens · conferência parcial", 3, itens_nota_1),
                (nota_parcial, chave_2, "VERMELHO", "1 item · quantidade abaixo do pedido", 1, itens_nota_2),
            ):
                # xml_data.itens é o payload como a NF-e chegou — é dele que o motor
                # de correlação lê o lado faturado. nfe_itens é o mesmo item depois
                # da conferência (unidade normalizada, status). Os dois existem.
                cur.execute(
                    "INSERT INTO nfe_logs (id, tenant_id, chave_acesso, obra_id, pedido_id, "
                    "status_conferencia, resumo_global, xml_data, tipo, processado_em) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'entrada', NOW() - INTERVAL '1 hour' * %s)",
                    (
                        str(nfe_id), str(tenant_a), chave, str(obra_a), str(pedido),
                        status, resumo,
                        json.dumps({
                            "emitente_cnpj": cnpj_fornecedor,
                            "chave": chave,
                            "itens": [
                                {
                                    "n_item": numero,
                                    "descricao": material,
                                    "bitola_mm": bitola,
                                    "marca": marca,
                                    "quantidade": qtd,
                                    "unidade": unidade,
                                }
                                for numero, material, bitola, marca, qtd, unidade, _ in itens
                            ],
                        }),
                        horas,
                    ),
                )
            for nfe_id, itens in ((nota_cheia, itens_nota_1), (nota_parcial, itens_nota_2)):
                for numero, material, bitola, marca, qtd, unidade, status in itens:
                    cur.execute(
                        "INSERT INTO nfe_itens (id, tenant_id, nfe_log_id, item_numero, "
                        "material_recebido, bitola_recebida, marca_recebida, quantidade_recebida, "
                        "unidade_recebida, status_item) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            str(uuid.uuid4()), str(tenant_a), str(nfe_id), numero, material,
                            bitola, marca, qtd, unidade, status,
                        ),
                    )
    finally:
        con.close()

    return {
        "banco": BANCO,
        "url": f"postgresql+psycopg2://{OWNER}:***@{HOST}/{BANCO}",
        "construtora": "Construtora Alfa Engenharia",
        "obra": str(obra_a),
        "pedido": str(pedido),
        "nota_cheia": str(nota_cheia),
        "nota_parcial": str(nota_parcial),
        "logins": ", ".join(usuarios),
        "senha": SENHA_DEMO,
    }


def main() -> int:
    # O script cria e apaga um banco. Rodar contra um servidor que não é a
    # máquina local cairia sobre dados de outra pessoa.
    if not HOST.startswith(("localhost", "127.0.0.1", "::1")):
        raise SystemExit(f"seed_demo só roda contra PostgreSQL local (HOST={HOST!r}).")
    criar_banco()
    migrar()
    print(json.dumps(semear(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
