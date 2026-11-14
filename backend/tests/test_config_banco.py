"""P1: DATABASE_URL não pode cair silenciosamente em localhost em produção."""

import pytest

from app.config_banco import URL_DEV_PADRAO, resolver_database_url


def test_producao_sem_database_url_recusa_subir():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        resolver_database_url({"STELLSPY_AMBIENTE": "producao"})


def test_producao_com_database_url_base_usa_a_informada():
    url = "postgresql+psycopg2://app:x@db.interno:5432/stellspy"
    assert resolver_database_url({"STELLSPY_AMBIENTE": "producao", "DATABASE_URL": url}) == url


def test_database_url_em_branco_conta_como_ausente_em_producao():
    with pytest.raises(RuntimeError):
        resolver_database_url({"STELLSPY_AMBIENTE": "producao", "DATABASE_URL": "   "})


def test_desenvolvimento_sem_database_url_usa_localhost():
    assert resolver_database_url({"STELLSPY_AMBIENTE": "desenvolvimento"}) == URL_DEV_PADRAO


def test_sem_ambiente_definido_trata_como_desenvolvimento():
    assert resolver_database_url({}) == URL_DEV_PADRAO
