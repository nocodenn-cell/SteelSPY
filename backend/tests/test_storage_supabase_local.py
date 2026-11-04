"""Storage real do Supabase local — sem mock.

Só roda quando `SUPABASE_TEST_URL` e `SUPABASE_TEST_SECRET` estão definidos,
porque exige um Supabase local ativo (`supabase start`). O CI exclui este
marcador explicitamente (`-m "not supabase_local"`); localmente, rode
`pytest -m supabase_local`. Sem o stack, o teste é pulado — nunca falsificado.

Prova o que o mock não prova: o bucket existe, aceita o upload autenticado,
recusa sobrescrita, devolve os mesmos bytes e não expõe o objeto publicamente.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from app.services.armazenamento import ArmazenamentoSupabase, ChaveJaExiste

URL = (os.getenv("SUPABASE_TEST_URL") or "").strip()
CHAVE = (os.getenv("SUPABASE_TEST_SECRET") or "").strip()
BUCKET = (os.getenv("SUPABASE_TEST_BUCKET") or "evidencias").strip()

pytestmark = [
    pytest.mark.supabase_local,
    pytest.mark.skipif(
        not (URL and CHAVE),
        reason="defina SUPABASE_TEST_URL e SUPABASE_TEST_SECRET (Supabase local ativo)",
    ),
]


def test_ciclo_real_no_bucket_privado():
    backend = ArmazenamentoSupabase(URL, CHAVE, BUCKET)
    chave = f"teste-{uuid.uuid4().hex}/prova.jpg"
    dados = b"\xff\xd8\xff" + b"steelspy-storage-integration"
    try:
        backend.gravar(chave, dados)
        assert backend.existe(chave) is True
        assert backend.ler(chave) == dados

        with pytest.raises(ChaveJaExiste):
            backend.gravar(chave, b"\xff\xd8\xffoutro")

        # Bucket privado: a rota pública não entrega o objeto.
        publica = httpx.get(
            f"{URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{chave}", timeout=15.0
        )
        assert publica.status_code in (400, 401, 403, 404)
        assert dados not in publica.content
    finally:
        backend.remover(chave)
        backend.fechar()

    # Cliente próprio para conferir a remoção.
    verificador = ArmazenamentoSupabase(URL, CHAVE, BUCKET)
    try:
        assert verificador.existe(chave) is False
    finally:
        verificador.fechar()
