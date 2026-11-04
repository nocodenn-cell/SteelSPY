"""CLI da preparação da Sprint 5 — local, sem rede e sem modelo.

    python -m exp_vc02.cli validar --manifesto dados/manifesto.json --rotulos dados/rotulos
    python -m exp_vc02.cli avaliar --verdade dados/teste.json --predicoes saida/predicoes.json \
        --min-map50 0.85 --min-precisao 0.95 --min-recall 0.90 --exigir-validacao-humana
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exp_vc02 import dataset, metricas


def _imprimir(dados: dict, saida: str | None) -> None:
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    print(texto)
    if saida:
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        Path(saida).write_text(texto + "\n", encoding="utf-8")


def _cmd_validar(args: argparse.Namespace) -> int:
    resultado = dataset.validar(
        args.manifesto, args.rotulos, verificar_imagens=not args.sem_verificar_imagens
    )
    _imprimir(resultado, args.saida)
    return 0 if resultado["ok"] else 1


def _cmd_avaliar(args: argparse.Namespace) -> int:
    resultado = metricas.avaliar_arquivos(
        args.verdade,
        args.predicoes,
        confianca_minima=args.confianca,
        min_map50=args.min_map50,
        min_precisao=args.min_precisao,
        min_recall=args.min_recall,
        exigir_validacao_humana=args.exigir_validacao_humana,
        min_amostras_humanas=args.min_amostras_humanas,
    )
    _imprimir(resultado, args.saida)
    return 0 if resultado["aprovado"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preparação da Sprint 5 (visão): dataset e métricas.")
    sub = parser.add_subparsers(dest="comando", required=True)

    validar = sub.add_parser("validar", help="valida manifesto e rótulos COCO")
    validar.add_argument("--manifesto", required=True)
    validar.add_argument("--rotulos", required=True, help="diretório com treino.json, validacao.json, teste.json")
    validar.add_argument("--sem-verificar-imagens", action="store_true", help="confia no manifesto; não abre as imagens")
    validar.add_argument("--saida")
    validar.set_defaults(func=_cmd_validar)

    avaliar = sub.add_parser("avaliar", help="mede predições COCO contra a verdade de teste")
    avaliar.add_argument("--verdade", required=True)
    avaliar.add_argument("--predicoes", required=True)
    avaliar.add_argument("--confianca", type=float, default=0.5)
    avaliar.add_argument("--min-map50", type=float)
    avaliar.add_argument("--min-precisao", type=float)
    avaliar.add_argument("--min-recall", type=float)
    avaliar.add_argument("--exigir-validacao-humana", action="store_true")
    avaliar.add_argument("--min-amostras-humanas", type=int, default=100)
    avaliar.add_argument("--saida")
    avaliar.set_defaults(func=_cmd_avaliar)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (dataset.ErroDataset, metricas.ErroAvaliacao) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
