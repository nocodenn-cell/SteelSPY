"""Interface de linha de comando do protótipo VC-01.

Quatro comandos, todos locais e sem rede: `contar`, `calibrar`, `avaliar`,
`corrigir`. Nada aqui sobe servidor, abre banco ou fala com serviço externo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from exp_vc01 import avaliacao, pipeline
from exp_vc01.decisao import decidir
from exp_vc01.detectores import construir
from exp_vc01.foto import de_bytes
from exp_vc01.laudo import aplicar_correcao
from exp_vc01.tipos import Limites

_GRELHA: dict[str, list[dict[str, Any]]] = {
    "cv": [
        {"saturacao_min": s, "valor_min": v, "area_min": a}
        for s in (60, 90, 120)
        for v in (40, 80)
        for a in (40, 80)
    ],
    "hastes": [
        {"minimo_por_linha": m, "tolerancia_px": t, "area_min": a}
        for m in (4, 6, 8)
        for t in (6.0, 10.0)
        for a in (30, 60)
    ],
}

# A varredura de política é de graça (roda sobre o mesmo resultado do detector) e
# responde a pergunta que importa: com qual limiar o protótipo **se cala** em vez
# de afirmar errado? Segurança primeiro, cobertura depois.
_POLITICAS = [
    Limites(minimo=1, maximo=120, confianca_minima=0.0, instabilidade_maxima=1.0),
    Limites(minimo=2, maximo=120, confianca_minima=0.45, instabilidade_maxima=0.50),
    Limites(minimo=3, maximo=120, confianca_minima=0.55, instabilidade_maxima=0.35),
    Limites(minimo=3, maximo=120, confianca_minima=0.65, instabilidade_maxima=0.25),
    Limites(minimo=4, maximo=80, confianca_minima=0.70, instabilidade_maxima=0.20),
]


def _politica(caminho: str | None) -> Limites:
    if not caminho:
        return Limites()
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return Limites(**dados)


def _cmd_contar(args: argparse.Namespace) -> int:
    opcoes: dict[str, Any] = {}
    if args.detector == "rfdetr":
        opcoes = {"tamanho": args.tamanho, "threshold": args.threshold}
    elif args.parametros:
        opcoes = json.loads(Path(args.parametros).read_text(encoding="utf-8"))
    laudo = pipeline.contar(args.imagem, detector=args.detector, limites=_politica(args.politica), opcoes_detector=opcoes)
    saida = pipeline.gravar_saida(laudo, args.saida)
    print(json.dumps({k: v for k, v in saida.items()}, ensure_ascii=False, indent=2))
    resumo = {
        "veredito": laudo["veredito"],
        "contagem": laudo.get("contagem_maquina"),
        "confianca": (laudo.get("detector") or {}).get("confianca"),
        "motivos": laudo.get("motivos"),
    }
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


def _run_divisao(
    pasta_divisao: Path,
    args: argparse.Namespace,
    limite: int | None,
    excluir: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    opcoes: dict[str, Any] = {}
    if args.detector == "rfdetr":
        opcoes = {"tamanho": args.tamanho, "threshold": args.threshold}
    elif getattr(args, "parametros", None):
        opcoes = json.loads(Path(args.parametros).read_text(encoding="utf-8"))

    registros: list[dict[str, Any]] = []
    laudos: list[dict[str, Any]] = []
    pares = avaliacao.amostra_da_divisao(pasta_divisao, limite, excluir)
    motor = construir(args.detector, **opcoes)
    for i, (jpg, xml) in enumerate(pares, start=1):
        laudo = pipeline.contar(jpg, detector=args.detector, limites=_politica(args.politica), detector_obj=motor)
        gt = avaliacao.contar_ground_truth(xml)
        registros.append(avaliacao.registrar(laudo, jpg.name, gt))
        laudos.append(laudo)
        print(
            f"[{i}/{len(pares)}] {jpg.name}: maquina={laudo.get('contagem_maquina')} gt={gt} "
            f"{laudo['veredito']}",
            file=sys.stderr,
            flush=True,
        )
    return registros, laudos


def _cmd_avaliar(args: argparse.Namespace) -> int:
    avaliacao.validar_uso(args.split, para="avaliacao")
    contamina: dict[str, list[str]] = {}
    if args.excluir_contaminadas:
        contamina = {d: sorted(n) for d, n in avaliacao.mapear_duplicatas(args.dados).items()}
    totais = avaliacao.garantir_disjuntas(args.dados, excluir={d: set(n) for d, n in contamina.items()})
    registros, _ = _run_divisao(
        Path(args.dados) / args.split, args, args.limite, set(contamina.get(args.split, []))
    )
    resultado = {
        "divisao": args.split,
        "imagens_por_divisao": totais,
        "contaminadas_excluidas": contamina,
        "detector": args.detector,
        "politica": _politica(args.politica).a_dicionario(),
        "metricas": avaliacao.metricas(registros),
        "registros": registros,
    }
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"avaliacao_{args.split}.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resultado["metricas"], ensure_ascii=False, indent=2))
    return 0


def _cmd_calibrar(args: argparse.Namespace) -> int:
    """Escolhe parâmetros e política na validação — nunca na divisão de teste.

    A pontuação é segurança primeiro: só interessa configuração que **não afirme
    contagem errada**; entre as que passam, vence a que responde mais.
    """
    avaliacao.validar_uso(args.split, para="calibracao")
    pares = avaliacao.amostra_da_divisao(Path(args.dados) / args.split, args.limite)
    melhores: list[dict[str, Any]] = []
    for opcoes in _GRELHA[args.detector]:
        detector = construir(args.detector, **opcoes)
        medidas: list[tuple[Any, int]] = []
        for jpg, xml in pares:
            foto = de_bytes(jpg.read_bytes(), origem=str(jpg))
            medidas.append((detector.detectar(foto), avaliacao.contar_ground_truth(xml)))
        for politica in _POLITICAS:
            registros = []
            for resultado, gt in medidas:
                decisao = decidir(resultado, politica)
                registros.append(
                    {
                        "nome": ".",
                        "veredito": decisao.veredito,
                        "contagem": decisao.contagem,
                        "ground_truth": gt,
                        "latencia_ms": resultado.latencia_ms.get("total"),
                    }
                )
            m = avaliacao.metricas(registros)
            melhores.append(
                {
                    "opcoes": opcoes,
                    "politica": politica.a_dicionario(),
                    "metricas": m,
                    "chave": (
                        m["erros_nao_sinalizados"],
                        -(m["assumidas"] / max(1, m["fotografias"])),
                        -(m["erro_absoluto_medio"] or 999),
                    ),
                }
            )
        print(f"  {opcoes} avaliado em {len(pares)} imagens", file=sys.stderr, flush=True)

    melhores.sort(key=lambda x: x["chave"])
    escolhido = melhores[0]
    assert escolhido
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"calibracao_{args.detector}.json").write_text(
        json.dumps([{k: v for k, v in m.items() if k != "chave"} for m in melhores], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (destino / "parametros_detector.json").write_text(json.dumps(escolhido["opcoes"], indent=2), encoding="utf-8")
    (destino / "politica.json").write_text(json.dumps(escolhido["politica"], indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "divisao_usada": args.split,
                "opcoes": escolhido["opcoes"],
                "politica": escolhido["politica"],
                "metricas_validacao": escolhido["metricas"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_corrigir(args: argparse.Namespace) -> int:
    caminho = Path(args.laudo)
    laudo = json.loads(caminho.read_text(encoding="utf-8"))
    corrigido = aplicar_correcao(laudo, contagem_humana=args.contagem, quem=args.quem, motivo=args.motivo)
    caminho.write_text(json.dumps(corrigido, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(corrigido["correcao_humana"], ensure_ascii=False, indent=2))
    return 0


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="exp_vc01", description="Protótipo de contagem visual de vergalhões")
    sub = p.add_subparsers(dest="comando", required=True)

    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--detector", choices=["cv", "hastes", "rfdetr"], default="cv")
    comum.add_argument("--politica", help="JSON com os limites de recusa")
    comum.add_argument("--tamanho", default="nano", choices=["nano", "small", "medium", "large"])
    comum.add_argument("--threshold", type=float, default=0.35)

    c = sub.add_parser("contar", parents=[comum], help="conta uma fotografia")
    c.add_argument("--imagem", required=True)
    c.add_argument("--saida", default=".devtmp/vc01/saida")
    c.add_argument("--parametros", help="JSON de parâmetros do detector (gerado por calibrar)")
    c.set_defaults(func=_cmd_contar)

    a = sub.add_parser("avaliar", parents=[comum], help="métricas contra contagem humana")
    a.add_argument("--dados", required=True, type=Path)
    a.add_argument("--split", default="Test")
    a.add_argument("--limite", type=int)
    a.add_argument("--saida", default=".devtmp/vc01/saida")
    a.add_argument("--parametros")
    a.add_argument(
        "--excluir-contaminadas",
        action="store_true",
        help="descarta imagens byte-idênticas a outra divisão antes de medir",
    )
    a.set_defaults(func=_cmd_avaliar)

    k = sub.add_parser("calibrar", parents=[comum], help="ajusta parâmetros sem tocar na divisão de teste")
    k.add_argument("--dados", required=True, type=Path)
    k.add_argument("--split", default="Validation")
    k.add_argument("--limite", type=int, default=40)
    k.add_argument("--saida", default=".devtmp/vc01/saida")
    k.set_defaults(func=_cmd_calibrar)

    r = sub.add_parser("corrigir", help="registra a contagem humana ao lado da da máquina")
    r.add_argument("--laudo", required=True)
    r.add_argument("--contagem", required=True, type=int)
    r.add_argument("--quem", required=True)
    r.add_argument("--motivo", required=True)
    r.set_defaults(func=_cmd_corrigir)
    return p


def main(argv: list[str] | None = None) -> int:
    args = montar_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
