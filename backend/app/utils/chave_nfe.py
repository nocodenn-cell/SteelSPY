"""
Validação da chave de acesso da NF-e (44 dígitos + dígito verificador módulo 11).
Evita consumo de APIs pagas quando a chave é inválida.
"""

from __future__ import annotations


class ChaveNFeInvalidaError(ValueError):
    """Chave com formato incorreto ou DV inválido."""


def _digito_verificador_chave(base_43: str) -> int:
    """Calcula o DV dos 43 primeiros dígitos (pesos 2-9 da direita para a esquerda)."""
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    p = 0
    for i in range(42, -1, -1):
        soma += int(base_43[i]) * pesos[p % 8]
        p += 1
    resto = soma % 11
    dv = 11 - resto
    if dv >= 10:
        return 0
    return dv


def validar_chave_acesso_nfe(chave: str) -> str:
    """
    Valida chave de 44 dígitos numéricos e o dígito verificador (módulo 11).

    Returns:
        A própria chave normalizada (somente dígitos).

    Raises:
        ChaveNFeInvalidaError: se tamanho, caracteres ou DV forem inválidos.
    """
    if chave is None:
        raise ChaveNFeInvalidaError("Chave ausente.")

    apenas_digitos = "".join(c for c in str(chave) if c.isdigit())
    if len(apenas_digitos) != 44:
        raise ChaveNFeInvalidaError(
            f"A chave deve ter exatamente 44 dígitos (recebido: {len(apenas_digitos)})."
        )

    base_43 = apenas_digitos[:43]
    dv_informado = int(apenas_digitos[43])
    dv_calculado = _digito_verificador_chave(base_43)

    if dv_informado != dv_calculado:
        raise ChaveNFeInvalidaError(
            "Dígito verificador inválido (módulo 11). Verifique a chave digitada."
        )

    return apenas_digitos
