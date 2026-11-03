from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.email_smtp import enviar_email_com_anexo
from app.services.relatorio_semanal import (
    LinhaRelatorio,
    compor_chave_idempotencia,
    corpo_email_pt,
    montar_csv_bytes,
    nome_arquivo_csv,
    periodo_rolling_dias,
)


def test_periodo_rolling_7_dias():
    ini, fim = periodo_rolling_dias(7)
    assert fim > ini
    assert (fim - ini).total_seconds() == 7 * 24 * 3600


def test_montar_csv_bytes_vazio_tem_apenas_header():
    raw = montar_csv_bytes([])
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").strip()
    lines = text.split("\r\n") if "\r\n" in text else text.split("\n")
    assert len(lines) == 1
    assert "chave_acesso" in lines[0]


def test_montar_csv_bytes_uma_linha():
    oid = "00000000-0000-0000-0000-000000000001"
    ln = LinhaRelatorio(
        obra_id=oid,
        obra_nome="Obra Teste",
        nfe_log_id="11111111-1111-1111-1111-111111111111",
        chave_acesso="3" * 44,
        processado_em=datetime(2026, 4, 1, 15, 30, 0, tzinfo=timezone.utc),
        status_conferencia="VERDE",
        tipo="entrada",
        emitente_nome="Fornecedor",
        nfe_numero="123",
        nfe_serie="1",
        resumo_global="OK",
        itens_total=2,
        itens_verdes=2,
        itens_amarelos=0,
        itens_vermelhos=0,
    )
    raw = montar_csv_bytes([ln])
    text = raw.decode("utf-8-sig")
    assert "Fornecedor" in text
    assert "3" * 44 in text
    assert "VERDE" in text


def test_corpo_email_inclui_etiqueta_tz():
    ini = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    fim = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t = corpo_email_pt("Obra X", ini, fim, 5, etiqueta_tz="UTC (rolling)")
    assert "Obra X" in t
    assert "5" in t
    assert "UTC (rolling)" in t


def test_compor_chave_idempotencia_formato():
    c = compor_chave_idempotencia(dias=7, modo="UTC")
    assert c.startswith("steelspy:v1:7d:UTC:")


def test_nome_arquivo_csv():
    from uuid import UUID

    u = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    ini = datetime(2026, 4, 1, tzinfo=timezone.utc)
    fim = datetime(2026, 4, 8, tzinfo=timezone.utc)
    n = nome_arquivo_csv(u, ini, fim)
    assert n.startswith("steelspy_nfe_")
    assert "20260401" in n and "20260408" in n


@patch("app.services.email_smtp.smtplib.SMTP")
def test_enviar_email_inclui_bcc_no_envelope(mock_smtp_cls, monkeypatch):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("RELATORIO_EMAIL_FROM", "from@test")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("SMTP_USE_TLS", "0")

    enviar_email_com_anexo(
        destinatarios=["a@test"],
        assunto="x",
        corpo_texto="y",
        anexo_nome="f.csv",
        anexo_bytes=b"a,b",
        copia_oculta=["bcc@test"],
    )

    mock_smtp.sendmail.assert_called_once()
    args = mock_smtp.sendmail.call_args[0]
    envelope = args[1]
    assert "a@test" in envelope
    assert "bcc@test" in envelope
