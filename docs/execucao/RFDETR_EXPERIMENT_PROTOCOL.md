# PROTOCOLO DO EXPERIMENTO RF-DETR

> **Status de verificação:** protocolo escrito, **nenhum modelo treinado, nenhuma imagem coletada,
> nenhuma conta criada**. Shell indisponível na sessão. Os números de referência estão marcados como
> *pré-registrados* — ou seja, foram definidos **antes** de ver qualquer resultado, e não podem ser
> ajustados depois.

---

## 1. Escopo e regra de licenciamento

| Item | Decisão |
|------|---------|
| Arquitetura | **RF-DETR** (detecção e, como braço alternativo, keypoint) |
| Tamanhos permitidos | **Nano, Small, Medium, Large** — Apache-2.0 (fonte: [licenciamento Roboflow](https://roboflow.com/licensing), 2026-10-27) |
| Tamanhos proibidos | Atto, Femto, Pico, XL, 2XL (Platform Model License 1.0 — exige plano em dia) |
| YOLO / Ultralytics | **PROIBIDO** neste experimento (ver `LICENSING_GATE.md`) |
| Benchmark genérico (COCO) | **não é evidência** de precisão em obra — serve só para escolher tamanho inicial |

> **Regra explícita da diretriz, adotada como norma:** *benchmarks genéricos não constituem evidência
> de precisão em obra.* Nenhum número de COCO/mAP entra no relatório de decisão. Só entram as métricas
> de §6, medidas no **nosso** conjunto, no **nosso** canteiro.

---

## 2. Dataset autorizado

### 2.1 O que é "autorizado"

| Fonte | Autorizada? | Condição |
|-------|-------------|----------|
| Fotos tiradas pela equipe stellSPY, em obra própria ou de parceiro | ✅ | termo de uso de imagem assinado |
| Fotos de obra de cliente | ⚠️ | **somente** com autorização escrita e base legal registrada; padrão = não usar |
| Imagens de banco público | ⚠️ | verificar licença; **BY-NC proibido** (uso comercial) |
| Datasets da Roboflow Universe | ⚠️ | licença por projeto; BY-NC e "sem licença" proibidos |
| Imagem de terceiro baixada de rede social | ❌ | sem base legal |

**Sanitização obrigatória antes de subir:** remover/blur de rostos, placas de veículo, documentos
legíveis, crachás e qualquer dado de terceiro. Registro em planilha: `arquivo → sanitizado_por → data`.

### 2.2 Composição mínima

| Categoria | Imagens | Entregas distintas | Obras distintas |
|-----------|---------|--------------------|-----------------|
| Vergalhão (primária) | 600 | ≥ 60 | ≥ 3 |
| Sacos de cimento (secundária) | 600 | ≥ 60 | ≥ 3 |
| Conjunto de condições controladas (§7 e §8) | 160 | — | 1 (laboratório/pátio) |

**Por que ≥ 60 entregas:** o split é por entrega (§4). Com 60 entregas, o teste fica com ≥ 18 entregas
— número mínimo para o intervalo de confiança do MAPE não ser inútil.

### 2.3 O que **não** pode entrar no dataset

- Foto com material de outra categoria no centro do enquadramento (contamina a classe).
- Foto com marca d'água de app de terceiro.
- Duplicata visual (mesmo ângulo, segundos de diferença) — infla artificialmente o resultado.
- Foto noturna sem condição de contagem (não é caso de uso).

---

## 3. Protocolo de anotação

### 3.1 Classes (vergalhão)

| Classe | Definição operacional | Conta? |
|--------|----------------------|--------|
| `barra_6_3` | seção circular, bitola 6,3 mm | sim |
| `barra_8` | 8 mm | sim |
| `barra_10` | 10 mm | sim |
| `barra_12_5` | 12,5 mm | sim |
| `barra_16` | 16 mm | sim |
| `barra_20` | 20 mm | sim |
| `barra_25` | 25 mm | sim |
| `barra_indefinida` | seção visível, bitola não determinável | sim, contada à parte |

Anotar **as 3 bitolas presentes na obra** na primeira rodada (economiza retrabalho); as demais entram
como `barra_indefinida`.

**Regra de bbox:** retângulo envolvente mínimo da **seção visível** da barra, não da barra inteira.
Vergalhão é contado por seção, não por comprimento.

### 3.2 Classes (sacos)

| Classe | Definição operacional |
|--------|----------------------|
| `saco_inteiro` | ≥ 70% da face visível |
| `saco_parcial` | 15%–70% da face visível |
| `saco_ocluido` | < 15% visível — **anotado, mas excluído da contagem de referência** |

`saco_ocluido` existe para medir o erro de oclusão, não para ser contado. Se o modelo "adivinhar" esses
sacos, ele acerta por sorte e o número de teste mente.

### 3.3 Regras de decisão (o que separa dois anotadores)

| Situação | Regra |
|----------|-------|
| Duas barras encostadas | duas bboxes, mesmo que se toquem |
| Barra parcialmente fora do quadro | anotar se ≥ 50% da seção visível |
| Saco amassado | anotar pela área aparente |
| Saco atrás de saco (só uma faixa) | `saco_ocluido` se < 15% |
| Reflexo/brilho na seção | anotar normalmente; registrar flag `brilho` |
| Dúvida genuína | anotar + flag `duvida` + revisão obrigatória |

### 3.4 Controle de qualidade da anotação

| Item | Regra |
|------|-------|
| Dupla anotação | 10% das imagens, por anotador diferente, às cegas |
| Concordância mínima | IoU médio ≥ 0,85 **e** diferença de contagem ≤ 2% |
| Divergência acima disso | adjudicação por terceiro + revisão das regras |
| Flags | `brilho`, `oclusao`, `sujeira`, `duvida` obrigatórias quando aplicável |
| Versionamento | exportar manifest com hash; congelar antes do treino |

> **Guia de anotação é documento vivo até o congelamento.** Depois de congelado (aqui e no
> `LICENSING_GATE`), só muda com nova versão de dataset — nunca retroativamente.

---

## 4. Separação treino / validação / teste **por entrega**

### 4.1 Definição de entrega

Uma **entrega** = um evento de descarregamento (mesmo caminhão, mesma NF-e, mesmo horário, mesmo
local). Metadado obrigatório por imagem:

`entrega_id`, `obra_id`, `fornecedor`, `data`, `nf_chave`, `condicao_luz`, `angulo`, `dispositivo`.

### 4.2 Split

| Conjunto | Proporção | Regra |
|----------|-----------|-------|
| Treino | 70% das **entregas** | — |
| Validação | 15% das **entregas** | usada para escolher hiperparâmetro |
| Teste | 15% das **entregas** | **intocado até a avaliação final** |

**Proibições explícitas:**

- ❌ split aleatório por imagem (vazamento: mesma pilha em treino e teste);
- ❌ mesma obra em treino e teste (**o teste precisa de obra inédita**);
- ❌ usar o teste para escolher época, tamanho de modelo ou limiar;
- ❌ reavaliar no teste após ajuste — se ajustar, o teste vira validação e um novo teste é necessário.

### 4.3 Estratificação mínima do teste

| Dimensão | Exigência no teste |
|----------|--------------------|
| Obras | ≥ 3, sendo ≥ 1 com fornecedor diferente |
| Entregas | ≥ 18 por categoria |
| Faixa de contagem | ≥ 3 imagens em cada faixa: 1–10, 11–30, 31–60, > 60 |
| Luz | ≥ 3 imagens por condição de §8 |
| Sobreposição | ≥ 3 imagens por faixa de §7 |

---

## 5. Ground truth (verdade de referência)

### 5.1 Como se estabelece a contagem verdadeira

1. **Contagem manual dupla e independente** (2 pessoas, sem ver a saída do modelo, sem ver a contagem
   um do outro).
2. Divergência ≤ 1% → média arredondada é a verdade.
3. Divergência > 1% → terceiro conta; decide-se por maioria; registra-se a divergência no relatório.
4. Fotos impossíveis de contar com certeza (oclusão extrema) → **excluídas do teste** e listadas como
   "não avaliáveis". Nunca inventar número.

### 5.2 O que **não** é ground truth

| Fonte | Por que não |
|-------|-------------|
| Quantidade da NF-e | É o que queremos auditar — não pode ser a referência |
| Contagem do almoxarife no dia | Pode ser exatamente o erro que buscamos detectar |
| Predição de outro modelo | Circular |
| "Parece certo" na inspeção visual | Não é medição |

> **Consequência metodológica:** como a NF-e não é verdade, o experimento mede **acurácia de contagem
> contra a realidade física**, não "concordância com a nota". São coisas diferentes — e a segunda
> esconderia justamente o erro que o produto precisa pegar.

---

## 6. Métricas (definições formais)

Seja `ĉᵢ` a contagem predita e `cᵢ` a verdade, para as `n` imagens do conjunto de teste.

| Métrica | Fórmula | O que revela |
|---------|---------|--------------|
| **MAE** | `(1/n) Σ \|ĉᵢ − cᵢ\|` | Erro médio em unidades (fácil de explicar ao cliente) |
| **MAPE** | `(100/n) Σ \|ĉᵢ − cᵢ\| / cᵢ` | Erro relativo; comparável entre tamanhos de pilha |
| **Contagem exata** | `(1/n) Σ 1[ĉᵢ = cᵢ]` | Quantas vezes acertou em cheio — a métrica que o fiscal sente |
| **Viés** | `(1/n) Σ (ĉᵢ − cᵢ)` | Sinal: negativo = subconta sistematicamente |
| **P90 do erro absoluto** | percentil 90 de `\|ĉᵢ − cᵢ\|` | O caso ruim que estraga a confiança |
| **FP de contagem** | `max(0, ĉᵢ − cᵢ)` somado | Quanto o sistema "inventou" |
| **FN de contagem** | `max(0, cᵢ − ĉᵢ)` somado | Quanto o sistema "deixou passar" |

### 6.1 Métricas de detecção (diagnóstico, não decisão)

| Métrica | Definição |
|---------|-----------|
| Precisão | TP / (TP + FP) com casamento por centroide a ≤ 50% do diâmetro médio |
| Recall | TP / (TP + FN) |
| F1 | harmônica |
| FP de detecção | bbox sem objeto correspondente |
| FN de detecção | objeto sem bbox correspondente |

**Por que não usar IoU padrão:** em barras densamente sobrepostas, IoU 0,5 entre duas seções
adjacentes é fácil de obter por acidente. Casamento por **centroide** é mais fiel ao que importa
(contar seções).

### 6.2 Agregação por entrega

Além de por imagem, calcular **por entrega** (soma das fotos da entrega vs. verdade da entrega). É a
unidade comercial: o cliente recebe uma entrega, não uma foto.

| Métrica por entrega | Uso |
|--------------------|-----|
| Erro absoluto da entrega | Decide se dá para liberar sem revisão |
| MAPE por entrega | Alimenta o painel de qualidade |

---

## 7. Testes de sobreposição

### 7.1 Série controlada (obrigatória)

Fotografar o **mesmo** feixe/pilha em 4 níveis de oclusão, com material próprio:

| Nível | Como produzir | Fotos |
|-------|---------------|-------|
| 0% | feixe inteiro visível, frontal | 20 |
| 25% | cobrir um canto com lona | 20 |
| 50% | cobrir metade com lona | 20 |
| 75% | cobrir 3/4 | 20 |

Mesma câmera, mesma luz, mesmo enquadramento → isola a variável.

**Métrica específica:** queda de MAPE de 0% para 75%. Aceitável: degradação ≤ 25 pontos percentuais.
Acima disso, o produto precisa proibir captura com oclusão acima de 50%.

### 7.2 Sobreposição natural

Estratificar o teste por **fração de área ocluída**, estimada pela anotação:

| Faixa | Como medir | Meta |
|-------|-----------|------|
| Leve (< 25%) | soma das áreas de `saco_parcial` / área total | MAPE ≤ 3% |
| Média (25–50%) | idem | MAPE ≤ 6% |
| Pesada (> 50%) | idem | MAPE ≤ 12% **ou** revisão obrigatória |

### 7.3 Varredura de NMS/IoU

Treinar uma vez; avaliar em `iou_threshold ∈ {0,3, 0,45, 0,6, 0,7, 0,8}`. Registrar a curva
**contagem × IoU** — não mAP. Para barras densas, o ótimo de contagem costuma estar acima do padrão 0,5.

---

## 8. Testes de iluminação

### 8.1 Matriz mínima (8 condições × 20 fotos = 160)

| # | Condição | Como reproduzir |
|---|----------|-----------------|
| L1 | Sol direto, sombra dura | meio-dia, sem nuvem |
| L2 | Sombra de galpão | sob cobertura |
| L3 | Nublado (luz difusa) | dia encoberto |
| L4 | Contraluz | sol atrás do material |
| L5 | Galpão com luz mista (fluorescente + natural) | interior |
| L6 | Entardecer (baixa intensidade) | 17h–18h |
| L7 | Reflexo em barra nova oleada | flash direto |
| L8 | Superfície molhada | após chuva / aspersão |

### 8.2 Análise

Para cada condição: MAPE, contagem exata e P90 do erro. O relatório deve trazer a **pior condição**
explicitamente — é ela que define a mensagem ao fiscal ("evite fotografar contra o sol").

| Critério | GO | NO-GO |
|----------|-----|-------|
| MAPE na pior condição | ≤ 8% | > 15% |
| Degradação relativa vs. melhor condição | ≤ 50% | > 100% |

---

## 9. Critérios de revisão humana

A revisão **não é opcional** — é transição de estado obrigatória quando qualquer condição ocorrer:

| # | Condição | Origem |
|---|----------|--------|
| H1 | Confiança agregada (p10) < 0,75 | `contagem.py` |
| H2 | Divergência vs. NF-e > 10% | regra de negócio |
| H3 | Oclusão estimada > 50% | metadado da anotação/inferência |
| H4 | Iluminação classificada como L4/L6/L7 | análise da imagem |
| H5 | `barras_indefinidas > 0` | bitola mista |
| H6 | Contagem > 100 unidades | limite operacional de confiança |
| H7 | Primeira entrega do fornecedor na obra | política de onboarding |

**Confiança agregada** = percentil 10 das confianças das detecções, **nunca a média**
(um outlier a 0,30 se esconde em média 0,98).

| Métrica do modo assistido | GO |
|---------------------------|-----|
| Tempo de revisão por imagem | ≤ 15 s |
| Taxa de revisão | ≤ 40% das imagens |
| Correção média quando há revisão | ≤ 2 unidades |

---

## 10. Critérios pré-registrados (autoritativos)

> Idênticos a `docs/roboflow/ROBOFLOW_MODEL_EVALUATION.md` §6. **Reproduzidos aqui como fonte única de
> decisão do experimento e não podem ser alterados após o início da avaliação.**

### 10.1 Vergalhão (primário)

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| R1 | MAPE em feixes ≤ 50 barras | ≤ 3% | > 6% |
| R2 | Contagem exata | ≥ 75% | < 55% |
| R3 | Viés | \|viés\| ≤ 1% | > 3% |
| R4 | F1 de bitola (3 classes) | ≥ 0,90 | < 0,75 |
| R5 | Robustez a ângulo ±20° (degradação) | ≤ 20% | > 40% |
| R6 | Latência p95 | ≤ 3 s | > 6 s |

### 10.2 Sacos (secundário, assistido)

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| S1 | MAE em pilhas ≤ 50 sacos | ≤ 1,0 | > 2,0 |
| S2 | Contagem exata | ≥ 70% | < 50% |
| S3 | MAPE global | ≤ 4% | > 8% |
| S4 | Imagens com erro > 10% | ≤ 8% | > 20% |
| S5 | Latência p95 | ≤ 3 s | > 6 s |
| S6 | Tempo de revisão | ≤ 15 s | > 30 s |

### 10.3 Regra composta

```
GO       = todos na faixa GO  E licença Apache-2.0  E custo ≤ R$ 0,05/recebimento
PIVOT    = 1–2 critérios intermediários → modo assistido obrigatório
NO-GO    = qualquer critério na faixa NO-GO
```

---

## 11. Configuração experimental (braços)

| Braço | Modelo | Objetivo | Custo (créditos) |
|-------|--------|----------|------------------|
| B0 | Baseline OpenCV (Hough/contorno) | Piso sem aprendizado | 0 |
| B1 | RF-DETR **Nano** bbox, 1 classe | Piso aprendido | ~1 |
| B2 | RF-DETR **Small** bbox, 3 bitolas | Ganho de tamanho + bitola | ~1,5 |
| B3 | RF-DETR **Keypoint** (centro da seção) | Densidade alta | ~2 |
| B4 | RF-DETR **Nano/Small** saco (bbox) | Categoria 2 | ~1,5 |
| B5 | RF-DETR **Seg** saco (se B4 no limiar) | Oclusão | ~2 |

**Orçamento total:** ≤ 8 dos 10 créditos/mês do Free Tier. Registrar o consumo real.

### 11.1 Registro de execução (obrigatório por run)

| Campo | Exemplo |
|-------|---------|
| `run_id` | `rfdetr-small-vergalhao-v1-2026-11-20` |
| `modelo_id` / `versao` | `steelspy-vergalhao/2` |
| `dataset_hash` | sha256 do manifest |
| `split_ref` | `split-v1.json` |
| `hiperparâmetros` | JSON completo |
| `iou_threshold` | 0,6 |
| `licenca_verificada_em` | data + link |
| `metricas` | todas as de §6 |
| `observações` | o que mudou e por quê |

Sem esse registro, o resultado não é reproduzível e **não vale** para GO/NO-GO.

---

## 12. Esforço e cronograma

| Fase | Atividade | Semanas |
|------|-----------|---------|
| P1 | Coleta (3–5 obras) + sanitização | 2 |
| P2 | Anotação (600 × 2 categorias) + QA 10% | 2 (paralelo) |
| P3 | Série controlada (§7.1) e matriz de luz (§8.1) | 1 |
| P4 | Baseline OpenCV (B0) | 0,5 |
| P5 | Treinos B1–B5 | 1,5 |
| P6 | Avaliação cega + relatório | 1 |
| | **Total** | **6 semanas** |

Esforço: **≈ 70–90 h** (sendo 20–30 h de anotação). Custo monetário: **R$ 0**.

---

## 13. O que este protocolo proíbe

| Proibição | Motivo |
|-----------|--------|
| Citar mAP de COCO como evidência de obra | Benchmarks genéricos não medem o nosso domínio |
| Split aleatório por imagem | Vazamento; resultado otimista falso |
| Ajustar critério depois de ver o número | Destrói a validade do experimento |
| Usar `ultralytics`/YOLO | Licença AGPL + dependência de Enterprise |
| Contar saco `ocluido` como acerto | O modelo acertaria por sorte |
| Ground truth = quantidade da NF-e | Circular: é exatamente o que se quer auditar |
| Reportar só a média | Esconde o caso ruim que quebra a confiança |
| Publicar dataset em Universe | Irreversível na prática + privacidade |
