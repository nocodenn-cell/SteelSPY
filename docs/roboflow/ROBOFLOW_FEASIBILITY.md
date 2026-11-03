# ROBOFLOW — Estudo de Viabilidade

> **Status:** spike concluído · **Decisão:** GO condicionado (ver §9) · **Data:** 2026-11-03
> **Natureza:** análise documental. Nenhuma conta criada, nenhuma dependência instalada,
> nenhum código alterado, nenhum deploy.

## 1. Método e fontes

Todas as afirmações de preço, licença e privacidade vêm de páginas públicas oficiais consultadas
nesta data. Onde a fonte não permitiu confirmar algo, o texto está marcado como **[a verificar]**.

| Fonte | Versão declarada na página |
|-------|---------------------------|
| [Roboflow Pricing](https://roboflow.com/pricing) | corrente em 2026-11-03 |
| [Roboflow Credits](https://roboflow.com/credits) | "Last updated November 3, 2026" |
| [Roboflow Licensing](https://roboflow.com/licensing) | "Last modified: October 27, 2026" |
| [YOLO26 Model License](https://roboflow.com/model-licenses/yolo26) | — |
| [RF-DETR Model License](https://roboflow.com/model-licenses/rf-detr) | — |
| [Plans (docs)](https://docs.roboflow.com/platform/billing-and-plans/plans) | — |
| [Self-Hosted Deployment (docs)](https://docs.roboflow.com/deployment/self-hosted/self-hosted) | — |
| [Model Pricing — Serverless (docs)](https://docs.roboflow.com/deployment/roboflow-cloud/serverless-api/model-pricing) | — |
| [Privacy Policy](https://roboflow.com/privacy) | "Last modified: June 1, 2025" |
| [Roboflow Inference (GitHub)](https://github.com/roboflow/inference) | — |

## 2. O que a Roboflow é (e o que cada peça resolve)

| Peça | O que faz | Nossa necessidade correspondente |
|------|-----------|----------------------------------|
| **Annotate** | Rotulagem de imagens no browser, com assistência de IA (auto-label, interactive labeling) | Criar o dataset proprietário de materiais de obra |
| **Datasets** | Versionamento de dataset, augmentação, splits, geração de "versions" | Congelar snapshots treino/validação auditáveis |
| **Train** | Treino gerenciado (RF-DETR, YOLO26, etc.) | Primeiros modelos sem infra de GPU própria |
| **Workflows** | Pipeline visual: detecção → crop → classificação → OCR → lógica → resposta | Encadear contagem + OCR de marca + regras |
| **Inference** | Servidor/library open source (Apache 2.0) para rodar modelos e workflows | Self-hosted, edge, offline |
| **Serverless Cloud API** | Inferência gerenciada, por crédito | Piloto rápido, sem hardware |
| **Dedicated Deployments** | GPU dedicada | Só em escala; fora do escopo do piloto |
| **Universe** | Datasets e modelos públicos da comunidade | *Warm start* e benchmark, com cautela |

## 3. Encaixe na arquitetura atual da stellSPY

### 3.1 O que já existe e serve

| Capacidade existente | Como a Roboflow se acopla |
|----------------------|---------------------------|
| API FastAPI stateless com `services/` isolados | Adapter novo em `backend/app/services/`, sem tocar no domínio |
| `nfe_logs` com `xml_data` (snapshot) e `override_info` (auditoria) | Padrão a replicar para inferência: snapshot + auditoria |
| Persistência de PDF em object storage (`laudo_storage.py`) | Mesmo bucket/cliente servirá para imagens e recortes anotados |
| Fila com `FOR UPDATE SKIP LOCKED` (`fila_retentativa.py`) | Padrão reutilizável para uma fila de inferência assíncrona |
| Retry com backoff e classificação de erro (`whatsapp_evolution.py`) | Padrão a reutilizar no cliente Roboflow |
| `url_seguras.py` (anti-SSRF) | Precisa ser endurecido: hoje aceita redirect (`ANALISE_PROJETO.md` A1) |

### 3.2 O que **não** existe — e é pré-requisito

> **Achroma decisivo do spike:** a stellSPY **não tem upload de imagem**.

Verificado por busca textual em todo o repositório: não há `UploadFile`, não há `File(...)`,
não há `python-multipart`, não há endpoint de upload, não há tabela de imagens, não há
processamento de arquivo.

O que existe é apenas um **campo de texto** `foto_url` (`conferencia.py:47`): o cliente envia uma URL,
a API a valida superficialmente e o servidor a **baixa na hora de gerar o laudo**
(`laudo_pdf.py:133-144`). Consequências para o projeto de visão computacional:

1. Não há onde armazenar a foto do recebimento — nem bucket, nem tabela, nem retenção.
2. O "pipeline de evidência" precisa ser construído **antes** de qualquer modelo.
3. `foto_url` é hoje um vetor de SSRF; um endpoint de upload reduz essa superfície (a imagem passa a
   ser nossa, não uma URL de terceiro).

**Conclusão:** o caminho crítico do 2.0 não é o modelo — é o `upload → storage → hash → fila →
inferência → revisão`. A Roboflow entra depois desse cano, não antes.

## 4. Restrição dura nº 1 — Licenciamento

Esta é a informação que mais muda a decisão técnica do spike.

### 4.1 Matriz oficial (roboflow.com/licensing, 2026-10-27)

| Modelo | Licença padrão | Cloud (qualquer plano) | **Self-hosted comercial** |
|--------|---------------|------------------------|---------------------------|
| **RF-DETR Nano, Small, Medium, Large** | **Apache-2.0** | Livre | **Livre, sem taxa** |
| **RF-DETR Seg (todos os tamanhos)** | **Apache-2.0** | Livre | **Livre, sem taxa** |
| RF-DETR Atto/Femto/Pico/XL/2XL | PML 1.0 | Incluída | **Enterprise add-on** |
| YOLO26 / YOLO11 / YOLOv8 / YOLOv12 | AGPL-3.0 | Incluída | **Enterprise add-on** |
| Roboflow 3.0 (derivado de YOLOv8) | AGPL-3.0 | Incluída | **Enterprise add-on** |
| YOLO-NAS | Apache-2.0 (código) | Incluída | Pesos Deci têm licença própria |
| DocTR / TrOCR / PP-OCR | Apache-2.0 / MIT | Livre | Livre |
| YOLOv7 / YOLOv9 | — | Incluída | **Não licenciável pela Roboflow** |

Tabela de planos declarada explicitamente pela Roboflow:

| Plano | Uso comercial na nuvem | Uso comercial self-hosted |
|-------|------------------------|---------------------------|
| Free Tier | Incluído | **Não incluído** |
| Core | Incluído | **Não incluído** |
| Enterprise | Incluído | Add-on |

### 4.2 O que isso significa para a stellSPY

O requisito de produto "operação offline" e "processamento local" **implica self-hosting**. Se
escolhermos YOLO agora:

- no piloto (cloud) funciona e é gratuito;
- no momento em que rodarmos na obra (self-hosted), **passamos a precisar de contrato Enterprise** —
  uma dependência comercial criada por uma escolha técnica evitável.

Se escolhermos **RF-DETR Nano→Large (Apache-2.0)**:

- treina na plataforma Roboflow (nuvem, qualquer plano);
- exporta/roda em qualquer hardware, comercialmente, **sem taxa e sem contrato**;
- não há risco de AGPL contaminar o código da stellSPY.

> **Decisão do spike:** padronizar em **RF-DETR (tamanhos Apache-2.0)** e tratar YOLO como
> alternativa de *benchmark*, nunca como base de produto. Nenhuma linha de código proprietária da
> stellSPY deve derivar de YOLO AGPL sem parecer jurídico.

Risco residual: se no futuro o melhor modelo para uma categoria específica for YOLO, isso é uma
decisão comercial (Enterprise), não técnica — e deve ser tomada com contrato, não com `pip install`.

## 5. Restrição dura nº 2 — Privacidade e LGPD

### 5.1 O padrão vem **ligado**

A documentação de planos afirma, textualmente:

> "Core has a workspace setting for data licensing and model training. **It is on by default for new
> workspaces.** (...) The setting applies only to private projects: opting out does not apply to
> public projects."

Ou seja: ao criar a conta e subir imagens de obra, **por padrão a Roboflow pode usar esses dados
para licenciamento e treino**, mesmo em projeto privado — até que o administrador desligue a opção
(Project Settings → "Data Licensing and Model Training" → off → confirmar).

Isso não é um detalhe de configuração; é a diferença entre "processador de dados" e "controlador
secundário" sob a LGPD. Para uma construtora cliente, imagens de canteiro podem conter pessoas,
placas, documentos e endereços.

### 5.2 Transfronteiriço

A política de privacidade declara que os dados **podem ser armazenados e processados fora do país de
origem**, inclusive nos EUA, com SCCs como mecanismo. Retenção: enquanto houver "Active Use"
(login em 30 dias ou dados hospedados). SOC 2 Type 2, criptografia em trânsito e em repouso.

### 5.3 Ações obrigatórias antes do primeiro cliente pagante

| # | Ação | Bloqueante? |
|---|------|-------------|
| P1 | Desligar "Data Licensing and Model Training" no workspace, e documentar com print | **Sim** |
| P2 | Nunca publicar projeto/dataset em Universe (publicar = irreversível na prática) | **Sim** |
| P3 | Rotular dados de treino removendo rostos/placas (ou treinar com recortes de material) | **Sim** |
| P4 | Cláusula de subprocessador (Roboflow) no contrato com a construtora + base legal | **Sim** |
| P5 | Preferir self-hosted para imagens de clientes a partir da Fase 3 | Não (recomendado) |
| P6 | Avaliar DPA/ SCC assinados com a Roboflow | **Sim** antes de escala |
| P7 | Retenção própria: imagens só no nosso storage; enviar à Roboflow apenas derivados quando possível | Recomendado |

**Alternativa que elimina o problema:** rodar **RF-DETR self-hosted desde o início** (`pip install
inference` ou container Docker) usando apenas os pesos exportados. Nesse arranjo, a imagem do cliente
**nunca sai da nossa infraestrutura** — só os pesos vieram da plataforma. É mais trabalho de infra e
mais fricção para rotular/treinar, mas resolve P1–P6 de uma vez.

## 6. Restrição dura nº 3 — Offline

A diretriz pede explicitamente para não afirmar que o Roboflow resolve o offline. Confirmo: **não
resolve**.

| Camada | O que Roboflow oferece | O que falta na stellSPY |
|--------|------------------------|-------------------------|
| Captura offline no celular | Nada (é problema de PWA) | Fila local (IndexedDB), retomada de upload, resolução de conflito |
| Inferência em servidor na obra | `inference server start` (Docker) roda offline com pesos locais | Máquina na obra, rede local, operação/atualização de modelo |
| Inferência no dispositivo | SDKs mobile/browser citados pela Roboflow | O PWA atual **não** tem bridge nativa; exigiria app nativo ou WebAssembly |
| Sincronização | Nada | Idempotência de upload, dedupe por hash, reconciliação |

O service worker atual (`pwa/sw.js`) **não** faz cache de assets e não implementa fila offline —
apenas deixa requisições de navegação passarem. Ou seja: mesmo a camada 1 está por construir.

## 7. O que a Roboflow **não** entrega

Para evitar expectativa errada no time comercial:

- **Não conta sozinha.** Detecção de objetos não resolve contagem de itens sobrepostos; é preciso
  pós-processamento geométrico ou segmentação + regra de negócio (ver `ROBOFLOW_MODEL_EVALUATION.md`).
- **Não faz a conciliação** com pedido de compra, NF-e ou divergência. Isso é o nosso domínio.
- **Não resolve OCR de marca em condições de obra** por si só (ver avaliação de OCR).
- **Não garante precisão genérica.** Um modelo público de saco de cimento treinado em outro país,
  outro cimento, outra iluminação, **não** deve ser assumido como suficiente.
- **Não substitui revisão humana** — e a diretriz de produto exige que a revisão exista.

## 8. Viabilidade por capacidade

| Capacidade | Viabilidade | Observação |
|-----------|-------------|------------|
| Gestão de dataset proprietário | **Alta** | Annotate + versions; free tier cobre ~5.000 imagens armazenadas por crédito |
| Treino inicial | **Alta** | 1 crédito = 30 min de GPU; free tier = até 5 h/mês |
| Inferência cloud no piloto | **Alta** | 0,125–0,1875 crédito/1.000 imagens; free tier ≈ 53k–80k imagens/mês |
| Inferência self-hosted | **Alta tecnicamente / Média operacionalmente** | Apache-2.0 core; sem crédito; exige hardware e DevOps |
| Workflows (detecção → crop → OCR) | **Média-alta** | Reduz código, mas cria acoplamento visual difícil de versionar |
| Contagem de vergalhão | **Média** | Caso com *use case* oficial na Roboflow; perspectiva/sobreposição são o risco |
| Contagem de sacos | **Média-baixa** | Sem use case oficial; oclusão em pilha é ambígua por natureza |
| OCR de marca/lote | **Média** | PP-OCR/DocTR disponíveis; qualidade em foto de canteiro é a incógnita |
| Offline ponta a ponta | **Baixa** | Depende de PWA + hardware na obra, não da Roboflow |

## 9. Decisão de viabilidade

**GO condicionado** para um experimento controlado, com quatro condições não negociáveis:

1. **Modelo base:** RF-DETR em tamanho Apache-2.0 (Nano→Large). YOLO apenas como benchmark interno,
   nunca como dependência de produto.
2. **Privacidade:** "Data Licensing and Model Training" desligado **antes** do primeiro upload;
   projetos privados; nada publicado em Universe.
3. **Evidência:** nenhuma imagem de cliente sai da nossa infraestrutura sem base legal documentada.
   Para o experimento, usar imagens próprias/laboratório.
4. **Expectativa:** o experimento valida **viabilidade de contagem**, não entrega produto. A saída é
   uma decisão GO/NO-GO por categoria, com números (ver `ROBOFLOW_MODEL_EVALUATION.md` §6).

Onde a viabilidade é **NO-GO** hoje:

- Contagem de sacos como **fonte de verdade automática** (sem revisão humana) — NO-GO.
- Substituir a conferência NF-e × especificação por visão computacional — NO-GO por definição de
  produto.
- Rodar YOLO self-hosted comercialmente sem contrato — NO-GO jurídico.
