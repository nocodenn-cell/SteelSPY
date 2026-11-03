import pytest

from app.utils.chave_nfe import ChaveNFeInvalidaError, _digito_verificador_chave, validar_chave_acesso_nfe


def test_dv_e_chave_consistente():
    base_43 = "1234567890123456789012345678901234567890123"
    assert len(base_43) == 43
    dv = _digito_verificador_chave(base_43)
    chave = base_43 + str(dv)
    assert validar_chave_acesso_nfe(chave) == chave


def test_rejeita_tamanho():
    with pytest.raises(ChaveNFeInvalidaError):
        validar_chave_acesso_nfe("123")


def test_rejeita_dv_errado():
    base_43 = "35210428737670000190550010000000011012345678"[:43]
    dv_errado = (_digito_verificador_chave(base_43) + 1) % 10
    with pytest.raises(ChaveNFeInvalidaError):
        validar_chave_acesso_nfe(base_43 + str(dv_errado))
