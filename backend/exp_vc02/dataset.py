"""Contrato do dataset de visão da Sprint 5.

O manifesto descreve cada imagem (arquivo, hash, dimensões, divisão, obra) e os
rótulos COCO de cada divisão descrevem as caixas. A validação é o portão de
entrada: sem ela, um vazamento entre treino e teste faria a métrica do modelo
medir memorização em vez de generalização.

Regra central: **uma obra pertence a uma única divisão**. Fotos da mesma obra
compartilham fundo, iluminação e lote — separar por imagem infla o resultado.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from PIL import Image

DIVISOES = ("treino", "validacao", "teste")

_CAMPOS_IMAGEM = ("arquivo", "sha256", "divisao", "obra_ref")


class ErroDataset(ValueError):
    """O dataset não cumpre o contrato; nada deve treinar com ele."""


def sha256(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _carregar_json(caminho: Path) -> dict[str, Any]:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ErroDataset(f"arquivo ausente: {caminho}") from exc
    except json.JSONDecodeError as exc:
        raise ErroDataset(f"JSON inválido em {caminho}: {exc}") from exc
    if not isinstance(dados, dict):
        raise ErroDataset(f"{caminho} precisa conter um objeto JSON")
    return dados


def _caminho_relativo(valor: Any) -> bool:
    if not isinstance(valor, str) or not valor.strip():
        return False
    caminho = Path(valor)
    return not caminho.is_absolute() and ".." not in caminho.parts


def _validar_manifesto(manifesto: dict[str, Any], raiz: Path, *, verificar_imagens: bool) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    erros: list[str] = []
    avisos: list[str] = []

    if manifesto.get("versao") != 1:
        erros.append("manifesto.versao deve ser 1")
    if not str(manifesto.get("projeto") or "").strip():
        erros.append("manifesto.projeto é obrigatório")
    if not str(manifesto.get("licenca") or "").strip():
        erros.append("manifesto.licenca é obrigatório")

    privacidade = manifesto.get("privacidade") or {}
    if privacidade.get("anonimizado") is not True:
        erros.append("manifesto.privacidade.anonimizado precisa ser true: sem isso, dados de obra não entram")

    imagens = manifesto.get("imagens")
    if not isinstance(imagens, list) or not imagens:
        erros.append("manifesto.imagens precisa ser uma lista não vazia")
        return erros, avisos, []

    vistas_arquivo: set[str] = set()
    vistas_sha: dict[str, str] = {}
    normalizadas: list[dict[str, Any]] = []

    for indice, item in enumerate(imagens):
        rotulo = f"manifesto.imagens[{indice}]"
        if not isinstance(item, dict):
            erros.append(f"{rotulo} precisa ser um objeto")
            continue
        faltando = [campo for campo in _CAMPOS_IMAGEM if not item.get(campo)]
        if faltando:
            erros.append(f"{rotulo} sem {', '.join(faltando)}")
            continue

        arquivo = str(item["arquivo"])
        if not _caminho_relativo(arquivo):
            erros.append(f"{rotulo}.arquivo precisa ser relativo e sem '..': {arquivo!r}")
            continue
        if arquivo in vistas_arquivo:
            erros.append(f"{arquivo!r} aparece mais de uma vez no manifesto")
            continue
        vistas_arquivo.add(arquivo)

        divisao = str(item["divisao"])
        if divisao not in DIVISOES:
            erros.append(f"{rotulo}.divisao inválida: {divisao!r} (use {', '.join(DIVISOES)})")

        digest = str(item["sha256"]).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            erros.append(f"{rotulo}.sha256 inválido")
        if digest in vistas_sha:
            if vistas_sha[digest] == divisao:
                avisos.append(f"{arquivo!r} é idêntica a outra imagem já listada em {divisao!r}")
            else:
                erros.append(
                    f"vazamento: {arquivo!r} ({divisao}) é idêntica a uma imagem de {vistas_sha[digest]!r}"
                )
        else:
            vistas_sha[digest] = divisao

        caminho = raiz / arquivo
        if not caminho.is_file():
            if verificar_imagens:
                erros.append(f"imagem ausente: {caminho}")
            normalizadas.append({**item, "arquivo": arquivo, "divisao": divisao, "sha256": digest})
            continue

        if verificar_imagens:
            real = sha256(caminho)
            if real != digest:
                erros.append(f"hash de {arquivo!r} não confere (manifesto {digest[:12]}…, arquivo {real[:12]}…)")
            try:
                with Image.open(caminho) as imagem:
                    largura, altura = imagem.size
            except Exception as exc:  # noqa: BLE001 - imagem ilegível é erro de dataset
                erros.append(f"imagem ilegível {arquivo!r}: {type(exc).__name__}")
            else:
                if item.get("largura") is not None and int(item["largura"]) != largura:
                    erros.append(f"{arquivo!r}: largura declarada {item['largura']} != {largura}")
                if item.get("altura") is not None and int(item["altura"]) != altura:
                    erros.append(f"{arquivo!r}: altura declarada {item['altura']} != {altura}")
                normalizadas.append({**item, "arquivo": arquivo, "divisao": divisao, "sha256": digest, "largura": largura, "altura": altura})
                continue

        normalizadas.append({**item, "arquivo": arquivo, "divisao": divisao, "sha256": digest})

    return erros, avisos, normalizadas


def _validar_rotulos(
    caminho: Path, esperadas: set[str], divisao: str, erros: list[str], avisos: list[str]
) -> dict[str, Any]:
    dados = _carregar_json(caminho)
    categorias = dados.get("categories")
    imagens = dados.get("images")
    anotacoes = dados.get("annotations")
    if not isinstance(categorias, list) or not categorias:
        erros.append(f"{caminho.name}: categories ausente ou vazia")
        return {"imagens": 0, "anotacoes": 0, "categorias": {}}
    if not isinstance(imagens, list):
        erros.append(f"{caminho.name}: images precisa ser uma lista")
        return {"imagens": 0, "anotacoes": 0, "categorias": {}}
    if not isinstance(anotacoes, list):
        erros.append(f"{caminho.name}: annotations precisa ser uma lista")
        anotacoes = []

    nomes_por_id: dict[int, str] = {}
    for categoria in categorias:
        if not isinstance(categoria, dict) or not isinstance(categoria.get("id"), int) or not str(categoria.get("name") or "").strip():
            erros.append(f"{caminho.name}: categoria inválida em {categoria!r}")
            continue
        if categoria["id"] in nomes_por_id:
            erros.append(f"{caminho.name}: category_id duplicado {categoria['id']}")
        nomes_por_id[categoria["id"]] = str(categoria["name"])

    ids_por_arquivo: dict[str, int] = {}
    dimensoes_por_id: dict[int, tuple[int, int] | None] = {}
    for imagem in imagens:
        if not isinstance(imagem, dict) or not isinstance(imagem.get("id"), int):
            erros.append(f"{caminho.name}: imagem sem id inteiro em {imagem!r}")
            continue
        nome = str(imagem.get("file_name") or "")
        if nome in ids_por_arquivo:
            erros.append(f"{caminho.name}: file_name duplicado {nome!r}")
        ids_por_arquivo[nome] = imagem["id"]
        dimensoes_por_id[imagem["id"]] = (
            (int(imagem["width"]), int(imagem["height"]))
            if isinstance(imagem.get("width"), int) and isinstance(imagem.get("height"), int)
            else None
        )

    faltando = sorted(esperadas - set(ids_por_arquivo))
    sobrando = sorted(set(ids_por_arquivo) - esperadas)
    if faltando:
        erros.append(f"{caminho.name}: {len(faltando)} imagem(ns) do manifesto sem rótulo, ex.: {faltando[:3]}")
    if sobrando:
        erros.append(f"{caminho.name}: {len(sobrando)} imagem(ns) rotulada(s) fora do manifesto, ex.: {sobrando[:3]}")
    if not ids_por_arquivo:
        erros.append(f"{caminho.name}: nenhuma imagem na divisão {divisao!r}")

    contagem_categoria: Counter[str] = Counter()
    ids_anotacao: set[int] = set()
    for indice, anotacao in enumerate(anotacoes):
        rotulo = f"{caminho.name}.annotations[{indice}]"
        if not isinstance(anotacao, dict):
            erros.append(f"{rotulo} precisa ser um objeto")
            continue
        if "score" in anotacao:
            erros.append(f"{rotulo}: verdade não leva score")
        identificador = anotacao.get("id")
        if not isinstance(identificador, int):
            erros.append(f"{rotulo} sem id inteiro")
        elif identificador in ids_anotacao:
            erros.append(f"{rotulo}: id duplicado {identificador}")
        else:
            ids_anotacao.add(identificador)

        imagem_id = anotacao.get("image_id")
        if imagem_id not in dimensoes_por_id:
            erros.append(f"{rotulo} referencia image_id desconhecido {imagem_id!r}")
            continue

        categoria_id = anotacao.get("category_id")
        if categoria_id not in nomes_por_id:
            erros.append(f"{rotulo} referencia category_id desconhecido {categoria_id!r}")
        else:
            contagem_categoria[nomes_por_id[categoria_id]] += 1

        caixa = anotacao.get("bbox")
        if not isinstance(caixa, list) or len(caixa) != 4 or not all(isinstance(v, (int, float)) for v in caixa):
            erros.append(f"{rotulo}.bbox precisa ser [x, y, largura, altura] numérico")
            continue
        x, y, largura, altura = (float(v) for v in caixa)
        if x < 0 or y < 0 or largura <= 0 or altura <= 0:
            erros.append(f"{rotulo}.bbox inválida: {caixa}")
            continue
        dimensoes = dimensoes_por_id[imagem_id]
        if dimensoes is not None:
            largura_img, altura_img = dimensoes
            if x + largura > largura_img + 0.5 or y + altura > altura_img + 0.5:
                erros.append(f"{rotulo}.bbox {caixa} ultrapassa a imagem {largura_img}x{altura_img}")

    if not anotacoes:
        avisos.append(f"{caminho.name}: divisão {divisao!r} sem anotações")

    return {
        "imagens": len(ids_por_arquivo),
        "anotacoes": len(anotacoes),
        "categorias": dict(sorted(contagem_categoria.items())),
    }


def validar(manifesto_path: str | Path, rotulos_dir: str | Path, *, verificar_imagens: bool = True) -> dict[str, Any]:
    """Valida manifesto + rótulos. Não treina, não lê rede, não altera nada."""
    manifesto_path = Path(manifesto_path)
    raiz = manifesto_path.parent
    manifesto = _carregar_json(manifesto_path)

    erros, avisos, imagens = _validar_manifesto(manifesto, raiz, verificar_imagens=verificar_imagens)

    por_divisao: dict[str, set[str]] = defaultdict(set)
    obras_por_divisao: dict[str, set[str]] = defaultdict(set)
    for item in imagens:
        por_divisao[item["divisao"]].add(item["arquivo"])
        obras_por_divisao[item["divisao"]].add(str(item["obra_ref"]))

    for obra in {obra for obras in obras_por_divisao.values() for obra in obras}:
        divisoes = sorted(div for div, obras in obras_por_divisao.items() if obra in obras)
        if len(divisoes) > 1:
            erros.append(f"vazamento por obra: {obra!r} aparece em {', '.join(divisoes)}")

    pasta = Path(rotulos_dir)
    resumo_divisoes: dict[str, Any] = {}
    for divisao in DIVISOES:
        caminho = pasta / f"{divisao}.json"
        if not caminho.is_file():
            erros.append(f"rótulos ausentes para {divisao!r}: {caminho}")
            continue
        resumo_divisoes[divisao] = _validar_rotulos(
            caminho, por_divisao.get(divisao, set()), divisao, erros, avisos
        )

    total_anotacoes = sum(item["anotacoes"] for item in resumo_divisoes.values())
    return {
        "ok": not erros,
        "projeto": manifesto.get("projeto"),
        "erros": erros,
        "avisos": avisos,
        "divisoes": resumo_divisoes,
        "total_imagens": len(imagens),
        "total_anotacoes": total_anotacoes,
        "obras_por_divisao": {divisao: sorted(obras) for divisao, obras in sorted(obras_por_divisao.items())},
    }


def exigir_valido(manifesto_path: str | Path, rotulos_dir: str | Path, *, verificar_imagens: bool = True) -> dict[str, Any]:
    """Como `validar`, mas levanta `ErroDataset` no primeiro conjunto de erros."""
    resultado = validar(manifesto_path, rotulos_dir, verificar_imagens=verificar_imagens)
    if not resultado["ok"]:
        raise ErroDataset("; ".join(resultado["erros"]))
    return resultado
