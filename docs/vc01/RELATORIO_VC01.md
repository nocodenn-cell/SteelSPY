# STEELSPY — SPRINT VC-01: PROTÓTIPO DE CONTAGEM VISUAL DE VERGALHÕES

> **Status do experimento:** concluído · **Decisão:** **NO-GO** para contagem automática
> (pipeline entregue e validado; coleta própria é pré-requisito) · **Data:** 2026-11-03
> **Natureza:** experimento isolado em `backend/exp_vc01/`. Nenhuma rota o importa, nenhuma
> migração, nenhum deploy, nenhum push. Custo adicional: **R$ 0**.

---

## 1. Resumo executivo

O protótipo existe, roda ponta a ponta sobre fotografias reais e produz laudo auditável com
marcações numeradas, contagem, confiança, limitações, recusa explícita e correção humana.
O que ele **não** faz é contar certo: nenhum dos detectores avaliados chegou perto do critério
de aceite pré-registrado em `docs/roboflow/ROBOFLOW_MODEL_EVALUATION.md` §6.2.

| Pergunta | Resposta medida |
|----------|-----------------|
| O pipeline funciona de ponta a ponta? | Sim — 146 fotografias processadas, laudo + foto marcada por imagem |
| A contagem é confiável? | **Não** — 0,68% de contagens exatas no melhor detector clássico; MAPE 349% |
| O protótipo erra calado? | Não, quando a política calibrada está ativa: **0 erros não sinalizados**, ao custo de **100% de recusa** |
| RF-DETR zero-shot resolve? | **Não** — as classes COCO não incluem ponta de vergalhão; subcontagem total |
| Dá para integrar ao recebimento? | **Não** — decisão automática de contagem fica NO-GO |
| O que falta? | Fotografias do cenário real de recebimento e fine-tune do RF-DETR com GPU |

O achado mais importante do experimento não é o erro do detector — é que a **recusa funciona**.
O protótipo preferiu não afirmar nada em 146 de 146 fotos em vez de afirmar errado. É o
comportamento seguro, e é o que permite evoluir sem risco de a contagem errada chegar ao dossiê.

---

## 2. Etapa 1 — Estado atual e reuso

### 2.1 Onde o experimento foi construído

| Item | Valor |
|------|-------|
| Worktree | `C:\Users\aoliv\.qoder\worktrees\app\db1a92\stellSPY` |
| Branch | `feat/sprint3-operacional` @ `bce0155` |
| HEAD mais avançado do repositório | `origin/main` @ `7e76713` (Sprint 3 já integrada) |
| Merge feito nesta sprint | **Nenhum** — a worktree de trabalho não é `origin/main` |

A branch de trabalho já continha a Sprint 3 (PWA operacional, dossiê PDF, recebimento parcial,
hardening). O experimento foi escrito **em cima dela**, sem tocar nos arquivos de produto.

### 2.2 O que foi reutilizado (e o que não foi duplicado)

Único ponto de reuso, e de propósito: `app/services/evidencias.py`.

| Reuso | Onde | Por quê |
|-------|------|---------|
| `normalizar_imagem` ([evidencias.py:92](../../backend/app/services/evidencias.py#L92)) | `exp_vc01/foto.py` | A imagem que o protótipo conta é normalizada pelas mesmas regras do upload real (limite de bytes, lado máximo, reencode) |
| `sha256` ([evidencias.py:77](../../backend/app/services/evidencias.py#L77)) | `exp_vc01/foto.py` | Hash do original **e** da normalizada no laudo |
| `ErroEvidencia` ([evidencias.py:54](../../backend/app/services/evidencias.py#L54)) | `exp_vc01/pipeline.py` | Foto inválida vira `RECUSADO` com o mesmo motivo que a API daria |

Não foram duplicados: upload, storage, autenticação, auditoria, dossiê. O módulo **não escreve**
em banco nem em storage — o laudo é um JSON local e a foto marcada é um JPEG local.

Prova de isolamento: `grep -rn exp_vc01 backend/app` não retorna nada.

### 2.3 Testes

| Conjunto | Resultado |
|----------|-----------|
| Suíte completa (venv de produto, sem `cv2`/`torch`) | **446 passed** em 33,53 s |
| Testes exclusivos do VC-01 (`tests/test_vc01_*.py`) | **28 passed** |

Os testes do VC-01 rodam na suíte de produto porque os módulos puros (`tipos`, `decisao`,
`laudo`, `avaliacao`, `filtro_linhas`) só usam biblioteca padrão e Pillow; `cv2`, `numpy` e
`torch` são importados **dentro** das funções de inferência.

---

## 3. Etapa 2 — Viabilidade

### 3.1 Modelo candidato: RF-DETR

| Item | Verificado |
|------|-----------|
| Pacote `rfdetr` | Apache 2.0 |
| Pesos Nano/Small/Medium/Large | Apache 2.0 — uso comercial livre |
| Pesos Atto/Femto/Pico/XL/2XL | Platform Model License 1.0 — exigem plano pago → **excluídos** (orçamento R$ 0) |
| Execução local | Sim, `pip install rfdetr`; inferência in-process, sem rede |
| Envio de fotografia para fora | **Nenhum** — os pesos são baixados uma vez; a imagem nunca sai da máquina |

Conclusão: existe caminho legal e gratuito com RF-DETR. O que faltou foi **peso treinado para
a classe certa**, não licença.

### 3.2 Hardware — a RTX 4070 não existe nesta máquina

| Verificação | Resultado |
|-------------|-----------|
| `nvidia-smi` | falha (comando não encontrado / driver ausente) |
| Adaptadores de vídeo | Intel UHD Graphics + "Microsoft Basic Display Adapter" (com erro) |
| Driver NVIDIA no DriverStore | ausente |
| Chassi | Acer Predator PHN16-72 · i9-14900HX · 32 GB |

Portanto **toda a medição deste relatório é em CPU**. Fine-tune de RF-DETR não é viável em CPU
neste prazo; a inferência é.

Latência CPU medida (nesta máquina, uma imagem 1500×900 já normalizada):

| Modelo | Carregamento | Inferência p50 | p95 |
|--------|--------------|----------------|-----|
| RF-DETR Nano (zero-shot) | ~4,2 s (uma vez) | 211 ms | 1.886 ms |
| Detector geométrico `hastes` | instantâneo | 82 ms | 139 ms |
| Detector de cor `cv` | instantâneo | 11 ms | 15 ms |

### 3.3 Datasets avaliados

| Dataset | Licença | Veredito |
|---------|---------|----------|
| **Wang (2024), figshare 23633703 v4** | **CC BY 4.0** | **Escolhido** |
| `rangerhkai/ranger-rebar-count-detection-model` | não comercial | Rejeitado |
| `bugwei/synthetic_on-site_rebar_data` | CC BY-NC | Rejeitado |
| ConRebSeg | sem licença declarada, 22 GB | Rejeitado |
| Espelhos do ROI-1555 | sem licença | Rejeitado |

Dataset escolhido — ficha lida na API do figshare em 2026-11-03:

| Campo | Valor |
|-------|-------|
| Título | *Rebar counting detection using object detection based on deep learning* |
| Autor | Seunghyeon Wang |
| DOI | 10.6084/m9.figshare.23633703.v4 |
| Licença | CC BY 4.0 |
| Publicação | 2024-06-08 |
| Aquisição | DJI Phantom 4 Pro, cinco obras na Coreia do Sul, voo vertical sobre cada pilar, 1–2 m de altura |
| Volume oficial | 728 imagens, 1.500×900, anotação Pascal VOC |
| Classe | `rebar` (uma só) |

**Geometria — o detalhe que decide tudo:** as caixas do dataset são quase quadradas
(mediana 19×20 px, razão 0,90). Elas marcam as **pontas das barras vistas de cima**, num pilar
com a gaiola de armadura — não o feixe amarrado visto de lado, que é o cenário de recebimento
da stellSPY. O dataset é um **proxy bem definido**, não o cenário do produto.

### 3.4 Privacidade

Nenhuma fotografia privada saiu da máquina. O dataset público foi baixado por requisições
HTTP *range* sobre o ZIP de 3,8 GB (só as entradas necessárias — 192 MB em disco). As
fotografias processadas são do dataset e de imagens locais de teste.

---

## 4. Etapa 3 — Arquitetura do protótipo

### 4.1 Módulos

```
backend/exp_vc01/
  tipos.py       Marca, ResultadoDetector, Limites, Decisao (dataclasses puras)
  foto.py        Fotografia: normaliza via app.services.evidencias, guarda os dois hashes
  detectores.py  cv (cor HSV) · hastes (top-hat direcional) · rfdetr (zero-shot COCO)
  decisao.py     política de recusa: CONTADO / INCONCLUSIVO / RECUSADO
  laudo.py       marcações numeradas na foto + JSON do laudo + correção humana
  pipeline.py    foto → detector → decisão → laudo; grava laudo.json + foto_marcada.jpg
  avaliacao.py   ground truth do XML, métricas da Etapa 4, guarda de vazamento
  cli.py         contar · calibrar · avaliar · corrigir
```

### 4.2 Fluxo

```
fotografia ──► normalizar_imagem (evidências) ──► detector ──► ResultadoDetector
                    │                                              │
            sha256 original + normalizada                          ▼
                                                        decidir(resultado, Limites)
                                                                   │
                              CONTADO ◄──────── sim ──── dentro dos limites?
                                  │                                │ não
                                  ▼                                ▼
                    foto_marcada.jpg + laudo.json          INCONCLUSIVO (com motivos)
                                  │
                                  └── correção humana (aplicar_correcao) mantém o número
                                      da máquina ao lado do humano e registra o delta
```

### 4.3 Política de recusa (o coração de segurança)

`decidir()` só devolve `CONTADO` quando **todas** as condições valem:

| Condição | Padrão (`Limites`) |
|----------|--------------------|
| contagem ≥ mínimo | 1 |
| contagem ≤ máximo | 120 |
| confiança ≥ mínimo | 0,55 |
| instabilidade ≤ máximo | 0,35 |

Fora disso → `INCONCLUSIVO`, com a lista de motivos. Falha de leitura, detector desconhecido ou
exceção → `RECUSADO`. **Recusa não é erro do sistema, é a resposta correta.**

A confiança é **heurística de consistência interna**: o detector roda em duas escalas e a
concordância entre elas entra na conta
(`confianca = (1 − instabilidade) × (0,35 + 0,65 × força_média)`). Ela **não** é probabilidade
calibrada de acerto — o laudo diz isso explicitamente em `limitacoes`.

### 4.4 Laudo — o entregável auditável

Campos: `protocolo` (`vc01-contagem/1`), `criado_em`, `fotografia` (origem, mime, bytes e
**sha256 do original e da normalizada**, dimensões), `veredito`, `contagem_maquina`, `motivos`,
`limitacoes`, `politica`, `correcao_humana`, `detector` (nome, alvo, nota, confiança,
instabilidade, latência), `marcas[]` (número, x, y, família, força).

Exemplo real (detector `cv`, `eb21_DJI_0290.jpg` do teste): 187 marcas numeradas, veredito
`CONTADO`, confiança 0,398, latência 13 ms — e ground truth humano **24**. Ou seja: o laudo
registra o erro sem escondê-lo, e a política calibrada existe justamente para não assinar esse
número.

### 4.5 Como usar

```bash
# contar uma foto
python -m exp_vc01.cli contar --detector hastes --imagem foto.jpg --saida .devtmp/vc01/saida

# calibrar parâmetros e política (só em Validation/Training)
python -m exp_vc01.cli calibrar --dados .devtmp/vc01/dados --split Validation --detector hastes

# avaliar no teste, excluindo as imagens contaminadas
python -m exp_vc01.cli avaliar --dados .devtmp/vc01/dados --split Test --detector hastes \
  --parametros .devtmp/vc01/saida/calib/parametros_detector.json \
  --politica .devtmp/vc01/saida/calib/politica.json \
  --excluir-contaminadas --saida .devtmp/vc01/saida/aval/teste_hastes_politica

# registrar correção humana ao lado da contagem da máquina
python -m exp_vc01.cli corrigir --laudo laudo.json --contagem 18 --quem "fiscal" \
  --motivo "barra sob a chapa não aparece na foto"
```

---

## 5. Etapa 4 — Avaliação

### 5.1 Ground truth e separação de divisões

- Ground truth = número de `<object>` no XML Pascal VOC do dataset (anotação humana).
- `calibrar` **recusa** a divisão `Test`; `avaliar` **só aceita** `Test`. É código, não intenção.

### 5.2 Vazamento encontrado — e corrigido antes de medir

O ZIP publicado declara **728 imagens**, mas a pasta traz **874 arquivos**. A diferença é
redundância:

| Situação | Quantidade |
|----------|-----------|
| Imagens únicas (hash SHA-256) | 728 |
| Imagens duplicadas entre `Training` e `Test` | 29 (16,6% do teste publicado) |
| Imagens duplicadas entre `Training` e `Validation` | 29 |
| Duplicatas internas ao `Training` | 88 hashes |

O artigo original declara teste com **146 imagens** — exatamente 175 − 29. Ou seja: a
contaminação é do empacotamento, não do experimento. A avaliação **exclui** as 58 imagens
contaminadas e mede sobre as **146 limpas**.

| Divisão | Publicado | Excluídas | Usado para |
|---------|-----------|-----------|------------|
| Training | 524 | 58 | (não usado: sem GPU para treinar) |
| Validation | 175 | 29 | calibração de parâmetros e política |
| **Test** | 175 | **29** | **métricas deste relatório** |

### 5.3 Resultados no teste limpo (146 fotografias, GT médio 25,34)

**Política permissiva** (aceita qualquer contagem ≥ 0 e qualquer confiança) — mede o detector cru:

| Detector | Assumidas | Exatas | Erro abs. médio | Erro abs. máx | MAPE | Sub / Super | Erros não sinalizados | p50 / p95 |
|----------|-----------|--------|-----------------|---------------|------|-------------|-----------------------|-----------|
| `cv` (cor/área) | 146 | 0 (0%) | 45,3 | 163 | 174,8% | 20 / 126 | **146 (100%)** | 11 / 15 ms |
| `hastes` (top-hat) | 146 | 1 (0,68%) | 78,2 | 203 | 349,4% | 1 / 144 | **145 (99,3%)** | 82 / 139 ms |
| `rfdetr nano` zero-shot (20 imagens) | 20 | 0 (0%) | 29,0 | 48 | 99,1% | 20 / 0 | **20 (100%)** | 211 / 1.886 ms |

Leitura: os detectores clássicos **supercontam** (mediana 99,5 contras contra GT mediano 24 —
cerca de 4×); o RF-DETR zero-shot **subconta quase tudo** (15 de 20 fotos com zero detecções e uma
falsa detecção de `car` a 0,58). Nenhum dos três é utilizável.

**Política calibrada** (`min 3`, `max 120`, confiança ≥ 0,65, instabilidade ≤ 0,25 — escolhida na
validação, não no teste):

| Métrica | Valor |
|---------|-------|
| Assumidas | **0** |
| Recusadas/inconclusivas | **146** |
| Taxa de recusa | **100%** |
| Erros não sinalizados | **0** |
| Latência p50 / p95 | 81 / 147 ms |

O mecanismo de segurança funciona exatamente como projetado: o protótipo reconhece que não sabe.
Mas cobertura zero não é produto.

### 5.4 A supercontagem tem fator estável? Não

Diagnóstico na divisão de validação (40 imagens, nunca o teste), razão máquina/GT:

| Estatística | Valor |
|-------------|-------|
| Mediana | 3,16× |
| p10 | 1,68× |
| p90 | 7,17× |
| Mín / Máx | 1,33× / 7,39× |
| Fotografias exatas após aplicar o fator mediano | **7,5%** |

A razão varia de 1,3× a 7,4× entre fotos. Um fator de escala fixo **não** corrige o detector —
o erro não é de calibração, é de segmentação: o detector mede traço fino (fios, ripas, cabos,
bordas de chapa), não "extremidade de vergalhão".

### 5.5 Contra os critérios pré-registrados (ROBOFLOW_MODEL_EVALUATION §6.2)

| # | Critério | GO | Medido | Veredito |
|---|----------|----|--------|----------|
| R1 | MAPE ≤ 50 barras | ≤ 3% | 174,8% (`cv`) · 349,4% (`hastes`) | **NO-GO** (> 6%) |
| R2 | Imagens com erro zero | ≥ 75% | 0% · 0,68% | **NO-GO** (< 55%) |
| R3 | Viés sistemático | \|viés\| ≤ 1% | viés médio **+308%** do total de barras (`hastes`) · +171% (`cv`) | **NO-GO** (> 3%) |
| R4 | Separação de bitola (3 classes) | F1 ≥ 0,90 | não medido (dataset tem 1 classe) | **Não avaliado** |
| R5 | Robustez a ângulo ±20° | degradação ≤ 20% | não medido (dataset é nadir de drone) | **Não avaliado** |
| R6 | Latência p95 | ≤ 3 s | 139 ms (CPU) | **GO** |

Pela regra composta daquele documento (*qualquer critério NO-GO ⇒ não entra em produto*):
**NO-GO**.

---

## 6. Evidências de inferência real

Nada neste relatório é simulado. Artefatos ficam em `.devtmp/vc01/` (fora do controle de versão):

| Artefato | Caminho |
|----------|---------|
| Avaliação `hastes` permissiva (146 fotos) | `.devtmp/vc01/saida/aval/teste_hastes_bruto/avaliacao_Test.json` |
| Avaliação `hastes` com política calibrada | `.devtmp/vc01/saida/aval/teste_hastes_politica/avaliacao_Test.json` |
| Avaliação `cv` permissiva | `.devtmp/vc01/saida/aval/teste_cv_bruto/avaliacao_Test.json` |
| Avaliação RF-DETR zero-shot (20 fotos) | `.devtmp/vc01/saida/aval/teste_rfdetr_amostra/avaliacao_Test.json` |
| Varredura de calibração (12 combos × 5 políticas) | `.devtmp/vc01/saida/calib/calibracao_hastes.json` |
| Diagnóstico de escala (validação) | `.devtmp/vc01/saida/diagnostico_escala.json` |
| Laudo + foto marcada por foto | `.devtmp/vc01/saida/*/laudo.json`, `foto_marcada.jpg` |
| Inferência RF-DETR com laudo | `.devtmp/vc01/saida/rfdetr_DJI_0357/laudo.json` |

Exemplos concretos lidos do disco:

- `samsung_ebb_eq3_DJI_0446.jpg` — máquina 95, GT 18, `CONTADO` (permissiva) → erro de +77.
- `DJI_0357.jpg` — RF-DETR detectou a classe `car` com confiança 0,577 → falso positivo real.
- Falha de driver do RF-DETR durante o desenvolvimento (array de strings no `predict`) virou
  `RECUSADO` com a mensagem da exceção no laudo — o caminho de recusa também foi exercitado
  por um erro real, não por teste sintético.

---

## 7. Limitações (ditas sem enfeite)

1. **Cenário diferente.** O dataset é drone sobre pilar (vista de cima das pontas). O recebimento
   da stellSPY é feixe amarrado no caminhão/pátio, visto de lado. Métrica boa aqui **não**
   transfere para lá.
2. **Sem GPU.** Toda medição é CPU. Fine-tune de RF-DETR não foi tentado — não haveria tempo
   hábil em CPU, e não há GPU nesta máquina.
3. **Zero-shot não é baseline de fine-tune.** RF-DETR com pesos COCO não detecta vergalhão por
   construção; o resultado dele mede custo e comportamento de recusa, não o teto do modelo.
4. **Confiança não é probabilidade.** É consistência entre duas escalas. Não serve para decidir
   sozinha em produto.
5. **Dataset com empacotamento defeituoso.** 146 cópias redundantes exigem exclusão manual
   (implementada em `avaliar --excluir-contaminadas`).
6. **Nenhum teste com fotografia real de obra da stellSPY.** Não há, hoje, dataset próprio —
   e o brief proíbe inventar métricas. Por isso não há número de campo neste relatório.
7. **Bitola (R4) e ângulo (R5) não foram medidos.** O dataset tem uma classe e uma geometria.

---

## 8. Decisão GO/NO-GO

**NO-GO** para:

- integrar contagem automática ao recebimento, ao dossiê ou a qualquer decisão de conferência;
- usar `cv`, `hastes` ou RF-DETR zero-shot como sugestão de quantidade — a sugestão seria
  grosseiramente errada e treinaria o fiscal a desconfiar do recurso;
- promover dependências de inferência (`torch`, `rfdetr`, `opencv`) a `backend/requirements.txt`.

**GO** para:

- manter `backend/exp_vc01/` como **harness de avaliação** (pipeline, laudo, recusa, métricas,
  guarda de vazamento) — ele é reutilizável quando houver modelo treinado;
- executar o plano de coleta da §9 e, com GPU disponível, fazer fine-tune de RF-DETR
  (pesos Apache 2.0, custo R$ 0);
- reavaliar com os critérios R1–R6 já pré-registrados — a régua já está escrita, não precisa ser
  inventada depois de ver o resultado.

A decisão de produto também se beneficia do resultado negativo: o risco de "IA que conta errado
e o fiscal assina" está quantificado. Com a política de recusa, esse risco é zero — ao custo de
o recurso não responder nada enquanto não existir modelo adequado.

---

## 9. Plano de coleta (pré-requisito do próximo experimento)

### 9.1 O que fotografar

O objeto de interesse é a **face do feixe onde as pontas das barras aparecem**, com o maior
número possível de pontas visíveis e sem oclusão entre feixes.

| Situação | Quantas fotos | Observação |
|----------|---------------|------------|
| Feixe no caminhão, antes do descarregamento | ≥ 120 | Inclui o cenário mais comum |
| Feixe no pátio, amarrado | ≥ 120 | Distância e ângulo controlados |
| Maço solto / barra a granel | ≥ 60 | Caso mais difícil (sem alinhamento) |

### 9.2 Protocolo de captura

- Câmera **perpendicular** ao plano das pontas, a 1,5–2,0 m; uma foto frontal e uma a ±20°.
- Variação deliberada: sol direto, sombra, luz artificial, piso claro e escuro.
- Enquadrar o feixe inteiro com 10% de margem; **não** usar zoom digital.
- Para cada foto, registrar: bitola, quantidade da NF, quantidade contada por **dois** humanos
  independentes (divergência → terceiro conta), obra, fornecedor, data/hora.
- Mínimo de **300 fotografias**, ≥ 5 obras e ≥ 10 fornecedores.

### 9.3 Split e anotação

- Split **por obra**, nunca por imagem: 60% treino / 20% validação / 20% teste, com teste
  contendo obras nunca vistas.
- Anotação em caixa e, nas 50 imagens mais difíceis, keypoint no centro de cada ponta — serve
  para medir o ganho marginal antes de investir em anotação densa.
- Verificação de duplicatas por SHA-256 **antes** de qualquer treino (o `avaliacao.py` já faz).

### 9.4 Critérios de aceite (os mesmos R1–R6)

Além deles: **zero** erros não sinalizados no teste e taxa de recusa ≤ 20%. Um modelo que
acerta 80% e recusa 20% é mais útil que um que afirma 100% e erra 30%.

---

## 10. O que não foi feito (e por quê)

| Restrição do brief | Situação |
|--------------------|----------|
| Push / deploy | não feitos |
| Migração remota / alteração em produção | não feitas |
| Alteração em outros projetos | não feitas |
| Dependências novas em `backend/requirements.txt` | não adicionadas — a stack de inferência vive num venv de experimento (`backend/.devtmp/vc01/.venv`, ignorado pelo Git) |
| Integração ao recebimento | não feita, por decisão de produto |
| Números simulados | nenhum — toda métrica vem de inferência real sobre arquivos reais |

O único commit é local e contém apenas `backend/exp_vc01/`, os cinco arquivos
`backend/tests/test_vc01_*.py` e este relatório.

---

## 11. Reprodutibilidade

```bash
# 1) venv do experimento (não entra no Git)
python -m venv .devtmp/vc01/.venv
.devtmp/vc01/.venv/Scripts/python.exe -m pip install -q pillow numpy opencv-python-headless sqlalchemy
.devtmp/vc01/.venv/Scripts/python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
.devtmp/vc01/.venv/Scripts/python.exe -m pip install -q rfdetr

# 2) suite de produto (sem cv2/torch) — 446 passed
backend/.venv/Scripts/python.exe -m pytest -q          # a partir de backend/

# 3) avaliação limpa no teste
cd backend
PYTHONIOENCODING=utf-8 ../.devtmp/vc01/.venv/Scripts/python.exe -m exp_vc01.cli avaliar \
  --dados ../.devtmp/vc01/dados --split Test --detector hastes \
  --parametros ../.devtmp/vc01/saida/calib/parametros_detector.json \
  --politica ../.devtmp/vc01/saida/calib/politica.json \
  --excluir-contaminadas --saida ../.devtmp/vc01/saida/aval/teste_hastes_politica
```

Dataset: `Dataset.zip` (3,8 GB) de `https://figshare.com/articles/dataset/23633703`, DOI
`10.6084/m9.figshare.23633703.v4`, CC BY 4.0. O download foi feito por requisições HTTP *range*
(`.devtmp/vc01/vc01_zip.py`), extraindo só `Training/`, `Validation/` e `Test/`.

---

## 12. Conclusão em uma frase

O experimento entregou **o que era possível entregar com R$ 0, sem GPU e sem dataset do cenário
real**: um pipeline auditável que conta, se recusa a afirmar quando não sabe, e mede o próprio
erro — e a medição diz, com números, que nenhum dos modelos disponíveis hoje conta vergalhão o
suficiente para tocar o recebimento. O próximo passo não é ajustar o detector; é fotografar o
recebimento de verdade.
