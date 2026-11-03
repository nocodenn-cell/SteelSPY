# ROBOFLOW — Avaliação dos Primeiros Modelos

> Avaliação **conceitual e metodológica**. Nenhum modelo foi treinado ou executado neste spike.
> O objetivo é definir o que medir, como medir e qual número autoriza seguir.

## 1. Premissa que precisa ser dita em voz alta

> **Não assumimos que um modelo genérico terá precisão suficiente.**

Três razões concretas:

1. **Domínio visual específico.** Saco de cimento brasileiro (Votorantim, CSN, InterCement, Apodi,
   Nacional) tem impressão, cor e empilhamento próprios. Um dataset indiano ou chinês de "cement bag"
   não transfere automaticamente.
2. **Contagem ≠ detecção.** mAP alto não implica contagem correta: um modelo pode achar 27 de 28 sacos
   com mAP 0,92 e errar a contagem em 3,6% — exatamente a faixa que gera disputa comercial.
3. **Custo do erro é assimétrico.** Subcontar material recebido gera passivo (a construtora paga por
   algo que não recebeu); supercontar gera glosa indevida e atrito com o fornecedor.

Portanto: **modelo público serve como baseline e como bootstrap de anotação, nunca como produto.**

## 2. Arcabouço de avaliação (igual para as duas categorias)

### 2.1 Métricas em três níveis

| Nível | Métrica | Para que serve |
|-------|---------|----------------|
| Detecção | mAP@50, mAP@50-95, precision/recall @ conf 0,5 | Comparar arquiteturas e tamanhos |
| **Contagem** | MAE, MAPE, % de imagens com erro zero, distribuição do erro absoluto | **É o que o cliente sente** |
| Operação | taxa de revisão humana, tempo médio de revisão, latência p95 | Decide se o produto economiza tempo |

A métrica de decisão é **contagem**, não mAP. Um relatório que só traz mAP está respondendo a pergunta
errada.

### 2.2 Splits obrigatórios

Não basta `train/val/test` aleatório. O split precisa ser **por obra e por lote**, não por imagem:

- imagens do mesmo pallet/feixe em treino e teste = vazamento (o modelo "reconhece" a foto);
- o teste tem de conter **obras que o modelo nunca viu**.

Mínimo: 3 obras distintas no teste, 1 delas com fornecedor diferente.

### 2.3 Matriz de condições (o teste difícil é o de campo)

| Dimensão | Variações mínimas |
|----------|-------------------|
| Iluminação | sol direto, sombra dura, nublado, galpão com luz mista, contraluz |
| Ângulo | frontal, 30°, 45°, zenital (drone), rasante |
| Distância | 1 m (detalhe), 3 m (pilha), 10 m (pátio) |
| Oclusão | 0%, 30%, 60% da pilha |
| Sujeira | saco limpo, saco com pó/argamassa, saco molhado |
| Dispositivo | Android intermediário, iPhone, câmera de ação |
| Contexto | piso de terra, pallet de madeira, caminhão, interior de galpão |

Cada célula precisa de ≥ 20 imagens para o teste ter poder estatístico. 7 dimensões completas é
inviável no início — priorize **iluminação × ângulo × oclusão** (3×4×3 = 36 células, ~700 imagens).

## 3. A. Sacos de cimento

### 3.1 O problema real

Uma pilha de sacos é um **empilhamento 3D visto em 2D**. Três dificuldades se somam:

1. **Oclusão por empilhamento**: sacos do fundo aparecem como uma faixa de 1–2 cm.
2. **Ambiguidade de profundidade**: 10 sacos visíveis podem ser 10 (uma camada) ou 30 (três camadas).
3. **Sacos deformados**: o saco de cimento não é rígido; amassa, inclina e assume geometria irregular.

Nenhum detector resolve (2) sozinho. Isso é decisão de produto, não de modelo.

### 3.2 Três enquadramentos possíveis

| Enquadramento | Como funciona | Precisão esperada | Complexidade |
|---------------|---------------|-------------------|--------------|
| **Contagem de frentes visíveis** | Detecta cada saco com face visível e conta | Boa em camada única; **subconta** em pilha | Baixa |
| **Contagem por camada** | Detecta camadas/linhas e multiplica pela profundidade declarada | Melhor em pilha organizada; depende de disciplina no canteiro | Média |
| **Segmentação + área** | Segmenta a região de sacos e divide pela área média do saco | Tolerante a oclusão parcial; erro cresce com a irregularidade | Média-alta |

**Recomendação:** começar por **contagem de frentes** (é o que gera valor imediato: "recebi 28, o
sistema viu 26"), evoluir para segmentação. Contagem por camada só se o cliente padronizar o
empilhamento — decisão comercial, não técnica.

### 3.3 Sobreposição — o núcleo técnico

- Detectores com **NMS agressivo subcontam** sacos encostados. Testar `iou_threshold` mais alto
  (0,7–0,8) e comparar com **soft-NMS**.
- **Instance segmentation** (RF-DETR Seg, Apache-2.0) separa melhor instâncias encostadas que
  bounding boxes — é a evolução natural do modelo de frentes.
- Sacos com < 15% da área visível devem ser **excluídos da contagem** e sinalizados, não adivinhados.

### 3.4 Confiança por detecção

- Guardar `confianca` por instância (não só a média).
- Limiar de contagem: começar em **0,35** para *propor* e **0,60** para *confirmar sem revisão*.
- Reportar quantas detecções caíram entre 0,35 e 0,60 — é o "grau de incerteza" que o fiscal precisa ver.

## 4. B. Vergalhões

### 4.1 O problema real

Um feixe de vergalhão visto de frente é um **empacotamento denso de círculos**. Aqui a detecção por
bbox falha por um motivo estrutural: as caixas se sobrepõem quase 100%, e o NMS descarta vizinhos
verdadeiros → **subcontagem sistemática**.

### 4.2 Estratégias, da mais simples à mais robusta

| Estratégia | Licença | Quando funciona | Risco |
|-----------|---------|-----------------|-------|
| **Baseline geométrico** (OpenCV Hough Circles/Ellipses) | BSD (OpenCV) | Feixe limpo, frontal, escala conhecida | Quebra com oclusão e iluminação |
| **Detecção de "bar end"** (RF-DETR, 1 classe) | Apache-2.0 | Feixe organizado | Subconta em densidade alta |
| **Keypoint de centro de barra** (RF-DETR Keypoint) | Apache-2.0 | **Melhor para densidade alta** — evita NMS | Anotação mais cara (ponto por barra) |
| **Segmentação de instâncias** (RF-DETR Seg) | Apache-2.0 | Sobreposição moderada | Pesado; instâncias muito próximas fundem |
| Estimativa por peso/área | — | Sempre (sanity check) | Não é contagem |

> **Insight relevante do spike:** para vergalhão, **keypoint de centro** é conceitualmente superior a
> bounding box, porque o alvo é o *centro da seção circular*, não a extensão da barra. E RF-DETR
> Keypoint é Apache-2.0. Vale entrar no experimento como braço alternativo.

### 4.3 Limitações por perspectiva e iluminação (explicitamente pedidas)

| Fatores | Efeito | Mitigação |
|---------|--------|-----------|
| **Ângulo oblíquo** | Seções viram elipses; barras do fundo ficam escondidas | Exigir captura frontal (±20°) no guia do PWA |
| **Contraluz** | Barras escuras contra céu claro | Flash guiado / captura em sombra |
| **Reflexo em barra nova (oleada)** | Brilho satura a seção | Foto com flash difuso; anel de luz |
| **Ferrugem** | Textura quebra borda; confunde com sujidade | Treinar com exemplares enferrujados |
| **Barras tortas/desalinhadas** | Oclusão assimétrica | Tolerância + revisão |
| **Escala desconhecida** | Não se sabe se são 12 m ou 6 m | Objeto de referência ou bitola declarada na NF |
| **Bitola mista no mesmo feixe** | Contagem agregada esconde divergência | Detecção com classe por bitola (6.3, 8, 10, 12.5, 16, 20, 25 mm) |

**Bitola mista é um risco de negócio, não só técnico:** contar 100 barras "no total" pode esconder
50 de 10 mm e 50 de 12,5 mm — e a NF-e frequentemente discrimina por bitola. O modelo deve, no
mínimo, separar as 3 bitolas mais comuns.

### 4.4 Sobreposição — o que fazer na prática

1. Contar **seções visíveis** (o que dá para ver).
2. Reportar `barras_estimadas` e `barras_visiveis` separadamente.
3. Cruzar com o esperado: `qtd_nf` convertida para número de barras (`metros_por_barra` já existe em
   `nfe_io.py`). Divergência > 5% → revisão.
4. Nunca apresentar um número único sem o intervalo.

## 5. C. OCR (marca, lote, validade) — escopo adjacente

A diretriz fala em PaddleOCR. Na Roboflow o caminho equivalente é **PP-OCR** (0,375 cr/1.000 com
detecção, 0,125 só reconhecimento) ou **DocTR** (Apache-2.0).

| Alvo | Dificuldade | Expectativa |
|------|-------------|-------------|
| Marca do saco (impressão grande) | Baixa-média | Alta precisão; útil para `marca_exigida` |
| Tipo CP-II/CP-III/CP-V | Média (fonte pequena) | Média; **já temos regex** em `nfe_item_campos.py` |
| Peso (50 kg) | Baixa | Alta |
| Lote e validade | Alta (carimbo, baixo contraste, saco curvo) | **Baixa** — exige revisão humana |
| Etiqueta de feixe de vergalhão | Média | Boa, se a etiqueta estiver legível |

**Recomendação:** OCR é **Fase 4**, não piloto. O valor imediato está em marca e tipo; validade/lote
devem entrar como "captura assistida + digitação", não como extração automática confiável.

**Não usar VLM generativo para ler validade.** Alucinação em data é o pior erro possível num
documento de conformidade.

## 6. Critérios objetivos de GO/NO-GO por modelo

Avaliação em **≥ 150 imagens de teste nunca vistas**, por categoria, com revisão cega (anotador não
vê a predição).

### 6.1 Sacos de cimento

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| S1 | MAE em pilhas ≤ 50 sacos | **≤ 1,0 saco** | > 2,0 |
| S2 | Imagens com erro zero | **≥ 70%** | < 50% |
| S3 | MAPE global | **≤ 4%** | > 8% |
| S4 | Imagens com erro > 10% | **≤ 8%** | > 20% |
| S5 | Latência p95 (cloud) | ≤ 3 s | > 6 s |
| S6 | Tempo de revisão humana (quando acionada) | ≤ 15 s | > 30 s |

### 6.2 Vergalhão

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| R1 | MAPE em feixes ≤ 50 barras | **≤ 3%** | > 6% |
| R2 | Imagens com erro zero | **≥ 75%** | < 55% |
| R3 | Subcontagem sistemática (viés) | \|viés\| ≤ 1% | > 3% |
| R4 | Separação correta de bitola (3 classes) | F1 ≥ 0,90 | < 0,75 |
| R5 | Robustez a ângulo ±20° | degradação ≤ 20% relativa | > 40% |
| R6 | Latência p95 | ≤ 3 s | > 6 s |

### 6.3 Regra de decisão composta

```
GO     : todos os critérios "GO" da categoria E licença Apache-2.0 E custo ≤ R$ 0,05/recebimento
PIVOT  : 1–2 critérios na faixa intermediária → modo assistido obrigatório (sem contagem autônoma)
NO-GO  : qualquer critério "NO-GO" → não entra em produto; reconsiderar abordagem (não o fornecedor)
```

**Modo assistido não é fracasso.** Para o piloto pago, "o sistema propõe 26, o fiscal confirma 28 em
8 segundos" já é valor: documenta, padroniza e gera evidência datada. A contagem autônoma é Fase 3.

## 7. Referências públicas — usar com cautela

| Referência | O que é | Como usar |
|-----------|---------|-----------|
| [Roboflow — Rebar counting (use case)](https://universe.roboflow.com/use-cases/rebar-counting) | Caso de uso oficial com classes `rebar end`, `rebar bundle`, `steel bar cross-section`, `rebar stack`; recomenda RF-DETR | Prova que o caso é tratado pela plataforma; **não** que funciona no nosso canteiro |
| [Cement bag detection (modelo)](https://universe.roboflow.com/machine-a8twz/cement-bag-detection-ncncb/model/2) | Modelo comunitário, 1 classe | Baseline de comparação |
| [cement-bag dataset](https://universe.roboflow.com/nabeeha/cement-bag-apwfa) | Dataset comunitário | Bootstrap de anotação |
| [Cement bags API](https://universe.roboflow.com/detection-avpq7/cement-bags-bsm9u-c7fbj/model/1/documentation) | Modelo comunitário | Baseline |
| [cementbagscount](https://universe.roboflow.com/dinchakpuja/cementbagscount) | Dataset de contagem | Baseline |
| [ConveyorVision-Bag-Counter](https://github.com/jagennath-hari/ConveyorVision-Bag-Counter) | YOLOv8 + ByteTrack para sacos em esteira | **Referência de arquitetura** (tracking ≠ contagem estática); atenção à AGPL |

> ⚠️ **Licença dos datasets da Universe varia**: CC BY 4.0, MIT, Public Domain **ou CC BY-NC 4.0**.
> **BY-NC proíbe uso comercial.** Verificar o campo de licença de cada projeto antes de usar em
> treino de produto. Não é opcional: contamina o modelo.

> ⚠️ Datasets comunitários típicos têm 100–500 imagens, 1 classe, um único canteiro. Servem para
> **pré-treino e bootstrap**, não para atestar desempenho no Brasil.

## 8. Recomendação final desta etapa

| Categoria | Recomendação | Ordem |
|-----------|--------------|-------|
| **Vergalhão** | **GO** — começar por aqui. Cenário geométrico melhor definido, caso oficial na plataforma, keypoint é alternativa forte | 1º |
| **Sacos de cimento** | **GO condicional** — depende de aceitar contagem assistida no piloto | 2º |
| **OCR marca/tipo** | **GO** com escopo restrito (marca e tipo; não validade) | 3º |
| **OCR lote/validade** | **NO-GO** automático neste estágio | — |
| **VLM/Agente para contagem** | **NO-GO** por decisão de produto | — |

**Por que vergalhão primeiro:** é o material núcleo atual da stellSPY (o `conferente` já normaliza
kg → metros por bitola), o erro de bitola é o mais caro (estrutural), e o objeto é rígido e regular —
o que torna a validação científica mais rápida. Sacos são o teste mais difícil; começar por eles é
apostar o cronograma na categoria com maior risco de NO-GO.

## 9. Custo de anotação por abordagem (decide o formato do dataset)

| Formato | Tempo por imagem | 600 imagens | Observação |
|---------|------------------|-------------|------------|
| Bounding box (1 classe) | 20–40 s | 3,3–6,7 h | Mais rápido |
| Bounding box (3 classes de bitola) | 40–70 s | 6,7–11,7 h | Necessário para R4 |
| Keypoint (centro de barra) | 60–120 s | 10–20 h | Melhor resultado em densidade |
| Máscara de segmentação | 120–300 s | 20–50 h | Só se segmentação for à produção |

Recomendação: anotar **bbox 1 classe primeiro** (baseline), e em paralelo keypoint apenas nas
50 imagens mais difíceis — para medir o ganho marginal antes de investir 20 h.
