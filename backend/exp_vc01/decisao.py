"""Política de decisão: quando o protótipo se cala e quando ele responde.

A regra que manda aqui é a do brief: **contagem inconclusiva tem que ser
recusada**, não arredondada para uma resposta plausível. Um "27" dito com
convicção errada é pior que um "não sei", porque vira número de recebimento.
"""

from __future__ import annotations

from exp_vc01.tipos import INCONCLUSIVO, RECUSADO, Decisao, Limites, ResultadoDetector


def decidir(resultado: ResultadoDetector, limites: Limites) -> Decisao:
    motivos: list[str] = []
    contagem = resultado.contagem

    if contagem < limites.minimo:
        motivos.append(f"contagem {contagem} abaixo do mínimo plausível ({limites.minimo})")
    if contagem > limites.maximo:
        motivos.append(
            f"contagem {contagem} acima do teto calibrado ({limites.maximo}); "
            "a cena provavelmente não é um feixe conto"
        )
    if resultado.confianca < limites.confianca_minima:
        motivos.append(
            f"confiança {resultado.confianca:.2f} abaixo de {limites.confianca_minima:.2f}"
        )
    if resultado.instabilidade > limites.instabilidade_maxima:
        motivos.append(
            f"varreduras independentes divergem ({resultado.instabilidade:.2f} "
            f"> {limites.instabilidade_maxima:.2f})"
        )

    veredito = INCONCLUSIVO if motivos else "CONTADO"
    return Decisao(veredito=veredito, motivos=tuple(motivos), contagem=contagem)


def recusar(motivo: str) -> Decisao:
    """Recusa antes da detecção: fotografia inválida, detector ausente, erro."""
    return Decisao(veredito=RECUSADO, motivos=(motivo,), contagem=0)
