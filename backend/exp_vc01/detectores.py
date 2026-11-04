"""Detectores de extremidades visíveis.

Dois candidatos, com propósitos diferentes e nenhum número inventado:

* `BlobHsv` — visão computacional clássica, roda em CPU, é determinística e
  serve de linha de base honesta: se ela já erra feio, o experimento tem que
  dizer isso, não esconder atrás de um modelo.
* `RfDetrZeroShot` — RF-DETR com pesos Apache 2.0 pré-treinados em COCO, sem
  ajuste. Ele **não conhece** a classe "extremidade de vergalhão"; rodá-lo é
  justamente a evidência de que zero-shot não basta e de que é preciso fine-tune.

A confiança aqui é heurística de consistência interna (a mesma imagem contada
em duas escalas concorda?), e não probabilidade calibrada. Nada no protótipo
autoriza tratar `confianca` como probabilidade de acerto.

`cv2` e `numpy` são importados dentro das funções: o pacote precisa ser
importável no venv da aplicação, onde eles não existem.
"""

from __future__ import annotations

import time
from typing import Any

from exp_vc01.tipos import Marca, ResultadoDetector


def _decodificar(conteudo: bytes) -> Any:
    import cv2
    import numpy as np

    buf = np.frombuffer(conteudo, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("não foi possível decodificar a imagem normalizada")
    return img


def _numerar(pontos: list[tuple[int, int, float]]) -> tuple[Marca, ...]:
    """Numera de cima para baixo, da esquerda para a direita — ordem legível."""
    return tuple(
        Marca(numero=i + 1, x=int(x), y=int(y), familia="a", forca=float(f))
        for i, (x, y, f) in enumerate(sorted(pontos, key=lambda p: (p[1] // 40, p[0])))
    )


def _linha_regular(grupo: list[tuple[float, float, int]], vao_min: float, vao_max: float, dispersao_max: float) -> bool:
    """O grupo forma fila com espaçamento parecido? (grupo já ordenado pela normal)"""
    ts = sorted(item[1] for item in grupo)
    vaos = [b - a for a, b in zip(ts, ts[1:]) if b - a > 0]
    if len(vaos) < 2:
        return False
    vaos.sort()
    mediana = vaos[len(vaos) // 2]
    if not (vao_min <= mediana <= vao_max):
        return False
    desvios = sorted(abs(v - mediana) for v in vaos)
    return desvios[len(desvios) // 2] / mediana <= dispersao_max


def filtrar_regulares(
    pontos: list[tuple[int, int, float]],
    *,
    tolerancia_px: float = 8.0,
    vao_min: float = 8.0,
    vao_max: float = 60.0,
    minimo_por_linha: int = 4,
    bins: int = 36,
    dispersao_max: float = 0.35,
    max_iteracoes: int = 12,
) -> list[tuple[int, int, float]]:
    """Guarda só o que se alinha em fila com espaçamento regular.

    Ponta de vergalhão em gaiola ou malha aparece em fila: mesma direção, mesmo
    vão. Prego solto, ripa e cabo não. É um prior geométrico — não aprendizado —
    e por isso precisa ser dito como tal no laudo.
    """
    import math

    restantes = list(pontos)
    aceitos: list[tuple[int, int, float]] = []
    for _ in range(max_iteracoes):
        melhor: list[tuple[float, float, int]] = []
        for bi in range(bins):
            ang = math.pi * bi / bins
            nx, ny = -math.sin(ang), math.cos(ang)
            dx, dy = math.cos(ang), math.sin(ang)
            proj = sorted(
                (p[0] * nx + p[1] * ny, p[0] * dx + p[1] * dy, i) for i, p in enumerate(restantes)
            )
            grupo = [proj[0]]
            for item in proj[1:]:
                if item[0] - grupo[-1][0] <= tolerancia_px:
                    grupo.append(item)
                else:
                    if len(grupo) > len(melhor) and _linha_regular(grupo, vao_min, vao_max, dispersao_max):
                        melhor = grupo
                    grupo = [item]
            if len(grupo) > len(melhor) and _linha_regular(grupo, vao_min, vao_max, dispersao_max):
                melhor = grupo
        if len(melhor) < minimo_por_linha:
            break
        escolhidos = {item[2] for item in melhor}
        aceitos.extend(restantes[i] for i in sorted(escolhidos))
        restantes = [p for i, p in enumerate(restantes) if i not in escolhidos]
        if not restantes:
            break
    return aceitos


class BlobHsv:
    """Linha de base clássica: segmenta a cor da ponta oxidada e conta componentes.

    Parâmetros calibrados na divisão de validação. `escala_secundaria` gera a
    segunda contagem usada para medir a instabilidade interna.
    """

    nome = "cv-blob-hsv"
    alvo = "extremidade de vergalhão (cor + forma)"

    def __init__(
        self,
        *,
        matiz_min: int = 5,
        matiz_max: int = 28,
        saturacao_min: int = 90,
        valor_min: int = 60,
        area_min: int = 40,
        area_max: int = 900,
        escala_secundaria: float = 0.75,
    ) -> None:
        self.p = {
            "matiz_min": matiz_min,
            "matiz_max": matiz_max,
            "saturacao_min": saturacao_min,
            "valor_min": valor_min,
            "area_min": area_min,
            "area_max": area_max,
        }
        self.escala_secundaria = escala_secundaria

    def _mascara(self, img: Any) -> Any:
        import cv2

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        return cv2.inRange(
            hsv,
            (self.p["matiz_min"], self.p["saturacao_min"], self.p["valor_min"]),
            (self.p["matiz_max"], 255, 255),
        )

    def _pontos(self, img: Any) -> list[tuple[int, int, float]]:
        import cv2
        import numpy as np

        mascara = self._mascara(img)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        pontos: list[tuple[int, int, float]] = []
        for c in contornos:
            area = float(cv2.contourArea(c))
            if not (self.p["area_min"] <= area <= self.p["area_max"]):
                continue
            x, y, w, h = cv2.boundingRect(c)
            if w <= 0 or h <= 0:
                continue
            alongado = max(w, h) / min(w, h)
            if alongado > 4.0:
                continue
            mx, my = x + w / 2.0, y + h / 2.0
            forca = min(1.0, area / self.p["area_max"]) * (1.0 / max(1.0, alongado - 1.0))
            pontos.append((int(mx), int(my), float(forca)))
        return pontos

    def detectar(self, fotografia: Any) -> ResultadoDetector:
        import cv2

        t0 = time.perf_counter()
        img = _decodificar(fotografia.normalizada)
        t_decod = int((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        pontos = self._pontos(img)
        t_detect = int((time.perf_counter() - t1) * 1000)

        # Segunda leitura em outra escala: discordar de si mesmo é sinal fraco.
        pequeno = cv2.resize(img, None, fx=self.escala_secundaria, fy=self.escala_secundaria)
        pontos2 = self._pontos(pequeno)
        n2 = int(round(len(pontos2) / (self.escala_secundaria**2)))
        maior = max(len(pontos), n2, 1)
        instabilidade = abs(len(pontos) - n2) / maior
        forca_media = sum(p[2] for p in pontos) / len(pontos) if pontos else 0.0
        confianca = max(0.0, (1.0 - instabilidade) * (0.35 + 0.65 * forca_media))

        return ResultadoDetector(
            detector=self.nome,
            alvo=self.alvo,
            marcas=_numerar(pontos),
            confianca=confianca,
            instabilidade=instabilidade,
            nota=(
                f"componentes de cor oxidada entre {self.p['area_min']} e {self.p['area_max']} px; "
                f"segunda leitura em escala {self.escala_secundaria} deu {n2}"
            ),
            latencia_ms={"decodificar": t_decod, "detectar": t_detect, "total": t_decod + t_detect},
            dimensoes=(img.shape[1], img.shape[0]),
        )


class HastesFinas:
    """Linha de base geométrica: procura hastes finas e claras em qualquer ângulo.

    A ponta de vergalhão é um traço fino (poucos pixels de largura) com dezenas
    de pixels de comprimento. `top-hat` com kernel linear, repetido em várias
    orientações e combinado pelo máximo, realça exatamente esse formato — sem
    aprender nada e sem depender de cor, que é o que a primeira linha de base
    errou (madeira e fôrma também são laranja).
    """

    nome = "cv-hastes"
    alvo = "hastes finas e claras (ponta de barra)"

    def __init__(
        self,
        *,
        comprimento_kernel: int = 15,
        orientacoes: int = 6,
        largura_max: int = 14,
        comprimento_min: int = 18,
        area_min: int = 50,
        area_max: int = 2500,
        escala_secundaria: float = 0.75,
        linhas_regulares: bool = True,
        minimo_por_linha: int = 4,
        tolerancia_px: float = 8.0,
    ) -> None:
        self.p = {
            "comprimento_kernel": comprimento_kernel,
            "orientacoes": orientacoes,
            "largura_max": largura_max,
            "comprimento_min": comprimento_min,
            "area_min": area_min,
            "area_max": area_max,
        }
        self.linhas_regulares = linhas_regulares
        self.minimo_por_linha = minimo_por_linha
        self.tolerancia_px = tolerancia_px
        self.escala_secundaria = escala_secundaria

    def _kernel(self, angulo_graus: float) -> Any:
        import cv2
        import numpy as np

        n = self.p["comprimento_kernel"] | 1
        k = np.zeros((n, n), np.uint8)
        rad = np.deg2rad(angulo_graus)
        meio = n // 2
        dx, dy = int(round(meio * np.cos(rad))), int(round(meio * np.sin(rad)))
        cv2.line(k, (meio - dx, meio - dy), (meio + dx, meio + dy), 1, 1)
        return k

    def _resposta(self, cinza: Any) -> Any:
        import cv2
        import numpy as np

        passos = max(2, self.p["orientacoes"])
        acumulado = np.zeros_like(cinza)
        for i in range(passos):
            angulo = 180.0 * i / passos
            topo = cv2.morphologyEx(cinza, cv2.MORPH_TOPHAT, self._kernel(angulo))
            acumulado = np.maximum(acumulado, topo)
        return acumulado

    def _pontos(self, img: Any) -> list[tuple[int, int, float]]:
        import cv2
        import numpy as np

        cinza = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cinza = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
        resposta = self._resposta(cinza)
        _, binario = cv2.threshold(resposta, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binario = cv2.morphologyEx(binario, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        n, _rotulos, stats, cent = cv2.connectedComponentsWithStats(binario, connectivity=8)
        pontos: list[tuple[int, int, float]] = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if not (self.p["area_min"] <= area <= self.p["area_max"]):
                continue
            fino, comprido = min(w, h), max(w, h)
            if fino > self.p["largura_max"] or comprido < self.p["comprimento_min"]:
                continue
            forca = min(1.0, comprido / 40.0) * (1.0 - fino / (self.p["largura_max"] + 1))
            pontos.append((int(cent[i][0]), int(cent[i][1]), float(forca)))
        if self.linhas_regulares:
            pontos = filtrar_regulares(
                pontos, tolerancia_px=self.tolerancia_px, minimo_por_linha=self.minimo_por_linha
            )
        return pontos

    def detectar(self, fotografia: Any) -> ResultadoDetector:
        import cv2

        t0 = time.perf_counter()
        img = _decodificar(fotografia.normalizada)
        t_decod = int((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        pontos = self._pontos(img)
        t_detect = int((time.perf_counter() - t1) * 1000)

        pequeno = cv2.resize(img, None, fx=self.escala_secundaria, fy=self.escala_secundaria)
        n2 = int(round(len(self._pontos(pequeno)) / (self.escala_secundaria**2)))
        maior = max(len(pontos), n2, 1)
        instabilidade = abs(len(pontos) - n2) / maior
        forca_media = sum(p[2] for p in pontos) / len(pontos) if pontos else 0.0
        confianca = max(0.0, (1.0 - instabilidade) * (0.35 + 0.65 * forca_media))

        return ResultadoDetector(
            detector=self.nome,
            alvo=self.alvo,
            marcas=_numerar(pontos),
            confianca=confianca,
            instabilidade=instabilidade,
            nota=(
                f"top-hat linear em {self.p['orientacoes']} orientações; aceita largura <= "
                f"{self.p['largura_max']} px, comprimento >= {self.p['comprimento_min']} px, "
                f"área {self.p['area_min']}-{self.p['area_max']} px; "
                f"fila regular (>= {self.minimo_por_linha} itens, tolerância {self.tolerancia_px} px): "
                f"{'sim' if self.linhas_regulares else 'não'}; segunda leitura deu {n2}"
            ),
            latencia_ms={"decodificar": t_decod, "detectar": t_detect, "total": t_decod + t_detect},
            dimensoes=(img.shape[1], img.shape[0]),
        )


class RfDetrZeroShot:
    """RF-DETR pré-treinado em COCO, sem fine-tune — import tardio, pesos Apache 2.0.

    `trust_checkpoint` é exigido pela biblioteca a partir da 1.11; o checkpoint
    vem da organização oficial do Roboflow no Hugging Face. Rodar isto é a
    medição de latência real em CPU, não uma promessa.
    """

    nome = "rf-detr-zero-shot"
    alvo = "classes COCO (nenhuma é extremidade de vergalhão)"

    def __init__(self, tamanho: str = "nano", threshold: float = 0.35) -> None:
        self.tamanho = tamanho
        self.threshold = threshold
        self._modelo: Any = None

    def _carregar(self) -> Any:
        if self._modelo is None:
            from rfdetr import RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall

            escolha = {
                "nano": RFDETRNano,
                "small": RFDETRSmall,
                "medium": RFDETRMedium,
                "large": RFDETRLarge,
            }
            classe = escolha[self.tamanho]
            self._modelo = classe(trust_checkpoint=True)
        return self._modelo

    def detectar(self, fotografia: Any) -> ResultadoDetector:
        t0 = time.perf_counter()
        modelo = self._carregar()
        t_carga = int((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        # `predict` aceita caminho, imagem PIL ou array — bytes crus viram array de
        # string e estouram `bytes * 255` dentro da biblioteca. Caminho também não
        # serve: o laudo tem que descrever exatamente o JPEG normalizado.
        import io

        from PIL import Image

        with Image.open(io.BytesIO(fotografia.normalizada)) as img:
            det = modelo.predict(img.convert("RGB"), threshold=self.threshold, shape=None)
        t_detect = int((time.perf_counter() - t1) * 1000)

        caixas = det.xyxy if hasattr(det, "xyxy") else det[0]
        scores = det.confidence if hasattr(det, "confidence") else det[1]
        rotulos = (getattr(det, "data", None) or {}).get("class_name")

        pontos: list[tuple[int, int, float]] = []
        for i in range(len(scores)):
            x0, y0, x1, y1 = (float(v) for v in caixas[i])
            pontos.append((int((x0 + x1) / 2), int((y0 + y1) / 2), float(scores[i])))

        nomes = sorted({str(r) for r in (rotulos if rotulos is not None else [])})
        confianca = sum(p[2] for p in pontos) / len(pontos) if pontos else 0.0
        return ResultadoDetector(
            detector=f"{self.nome}:{self.tamanho}",
            alvo=self.alvo,
            marcas=_numerar(pontos),
            confianca=confianca,
            instabilidade=0.0,
            nota=(
                f"zero-shot COCO, threshold {self.threshold}; classes vistas: "
                f"{', '.join(nomes) if nomes else 'nenhuma'}"
            ),
            latencia_ms={"carga_modelo": t_carga, "inferencia": t_detect, "total": t_carga + t_detect},
            dimensoes=(fotografia.largura, fotografia.altura),
        )


DETECTORES = {"cv": BlobHsv, "hastes": HastesFinas, "rfdetr": RfDetrZeroShot}


def construir(nome: str, **kwargs: Any) -> Any:
    try:
        classe = DETECTORES[nome]
    except KeyError as exc:
        raise ValueError(f"detector desconhecido: {nome!r} (opções: {', '.join(DETECTORES)})") from exc
    return classe(**kwargs)
