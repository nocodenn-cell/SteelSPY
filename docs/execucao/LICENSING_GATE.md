# LICENSING GATE — Política e Mecanismo de Bloqueio

> **Status de verificação:** política definida. O *script* de verificação **não existe ainda**
> (será criado na F0.3). O estado atual das dependências foi verificado **por leitura de
> `requirements.txt`** — não por `pip freeze`, porque o shell da sessão está indisponível.
> `pip install --dry-run` e inspeção de árvore de dependências **não foram executados**.

---

## 1. Por que este documento existe

A decisão central do spike foi: **RF-DETR Apache-2.0, nunca YOLO/Ultralytics sem aprovação explícita**.

Essa decisão morre silenciosamente de três formas:

1. alguém adiciona `ultralytics` ao `requirements.txt` "só para testar";
2. uma dependência **transitiva** traz YOLO junto;
3. um dataset com licença **BY-NC** entra no treino e contamina o modelo.

O gate existe para transformar a decisão em **barreira mecânica**, não em disciplina.

---

## 2. Regra

> **Nenhuma dependência com licença AGPL, GPL, SSPL ou licença de dataset não comercial pode entrar
> no repositório, no ambiente de execução ou no conjunto de treino sem aprovação registrada conforme §6.**

Aplicável a: `requirements*.txt`, `package.json`, `pyproject.toml`, pesos de modelo, datasets e
qualquer binário embarcado.

---

## 3. Listas

### 3.1 Proibidos (AGPL/GPL — bloqueio automático)

| Pacote | Licença | Risco |
|--------|---------|-------|
| `ultralytics` | AGPL-3.0 | Cobre YOLOv5, v8, v11, v12, v26. É o principal vetor |
| `yolov5` | GPL-3.0 (originalmente) / AGPL | idem |
| `yolov8` / `yolo` | AGPL | wrappers da comunidade |
| `darknet` bindings | variado | evitar |
| `torch-yolo*` | variado | inspecionar caso a caso |
| `super-gradients` | Apache no código, **pesos Deci com licença própria** | YOLO-NAS: bloqueado sem revisão |
| Qualquer `*-yolo`, `yolo-*` | presumir AGPL | inspeção obrigatória antes |

### 3.2 Permitidos (licenças permissivas) — lista de referência

| Pacote | Licença |
|--------|---------|
| `fastapi`, `starlette`, `uvicorn`, `pydantic`, `httpx`, `sqlalchemy` | MIT / BSD / Apache-2.0 |
| `pytest`, `ruff` | MIT |
| `torch`, `torchvision` | BSD-3-Clause |
| `numpy`, `opencv-python` | BSD |
| `inference` (Roboflow, núcleo) | Apache-2.0 — **com ressalva em §5** |
| `rfdetr` | Apache-2.0 |
| `supervision` | MIT |
| `Pillow` | MIT-CMU |
| `fpdf2` | LGPL-3.0 — ver §4 |
| `psycopg2-binary` | LGPL-3.0 — ver §4 |

### 3.3 Atenção — LGPL (não bloqueia, mas exige consciência)

`fpdf2` e `psycopg2` são **LGPL**. Para SaaS e para software próprio rodando na nossa infraestrutura,
LGPL não cria obrigação de abrir código. **Mas** se um dia distribuirmos um pacote/binário ao cliente
(ex.: servidor de inferência *instalado na obra do cliente*), a LGPL passa a exigir que o cliente possa
substituir a biblioteca — o que é atendível, mas **não é automático**.

| Cenário | LGPL é problema? |
|---------|------------------|
| API nossa, rodando na nossa nuvem | Não |
| Servidor de inferência na obra, operado por nós | Não |
| Pacote do servidor de inferência **entregue** ao cliente | **Sim** — exige cumprimento da LGPL |
| App desktop distribuído | Sim |

> Registro: hoje os dois pacotes LGPL são aceitos. A decisão muda no dia em que houver distribuição
> de binário. Anotar no `ADR de licenciamento`.

---

## 4. Como o gate verifica (três camadas)

### Camada 1 — estática, no repositório (precisa de CI)

Varredura por nome proibido em arquivos de dependência:

```bash
# ESPECIFICAÇÃO — a ser criada em F0.3 como scripts/check_licenses.sh
grep -RniE '^\s*(ultralytics|yolov5|yolov8|yolov9|yolov10|yolov11|yolov12|yolov26|darknet|super-gradients)\b' \
     --include='requirements*.txt' --include='pyproject.toml' --include='package.json' .
```

Saída esperada: **zero linhas**. Qualquer linha → falha o build.

Também varrer `package.json` do PWA por pacotes JS problemáticos (GPL/AGPL) — hoje não há nenhum.

### Camada 2 — dinâmica, no ambiente (precisa de execução)

**Esta é a camada que pega dependência transitiva** — e é a mais importante, porque a Camada 1 é
trivialmente burlável.

```bash
# ESPECIFICAÇÃO — a ser executada no CI depois do install
python -m piptools compile --dry-run 2>/dev/null || true
pip freeze > /tmp/freeze.txt
grep -iE 'ultralytics|yolo|super-gradients|darknet' /tmp/freeze.txt && exit 1 || exit 0
```

E inspeção de metadados de licença por pacote:

```bash
# ESPECIFICAÇÃO
python - <<'PY'
import importlib.metadata as md, re
suspeitos = re.compile(r'AGPL|GPL-3|SSPL', re.I)
for d in md.distributions():
    meta = d.metadata
    lic = (meta.get('License') or '') + ' ' + ' '.join(meta.get_all('Classifier') or [])
    nome = meta.get('Name','?')
    if suspeitos.search(lic):
        print(f"{nome} {d.version}: {lic[:120]}")
PY
```

Saída esperada: nenhum pacote com AGPL. GPL-3 aparece listado para revisão humana (pode ser ferramenta
de dev, não de produção).

### Camada 3 — humana, antes de qualquer comando de instalação "exploratória"

Regra de processo, não de máquina:

> **Nenhum `pip install` de biblioteca de visão computacional sem antes rodar
> `pip install --dry-run <pacote>` e ler a árvore de dependências.**

---

## 5. Risco específico e prioritário: `inference` (Roboflow)

O núcleo do `inference` é Apache-2.0, mas ele é um **hub de backends** — e backends de YOLO podem
declarar `ultralytics` como dependência.

| Item | Estado |
|------|--------|
| Licença do núcleo `inference` | Apache-2.0 (declarado oficialmente) |
| Dependências transitivas | **NÃO VERIFICADO** — shell indisponível |
| Risco | **ALTO** if `ultralytics` vier na árvore |

**Verificação obrigatória antes de instalar (primeira tarefa da Trilha B):**

```bash
# ESPECIFICAÇÃO — executar antes de qualquer instalação real
pip download inference --no-deps -d /tmp/inf   # baixa só o wheel, sem instalar
unzip -p /tmp/inf/*.whl '*/METADATA' | grep -iE '^Requires-Dist'
```

Se `ultralytics` aparecer:

| Opção | Veredito |
|-------|----------|
| Instalar mesmo assim | ❌ contamina o produto com AGPL |
| Instalar com extra mínimo sem o backend YOLO | ✅ **preferido** — verificar se existe extra |
| Rodar `inference` em container isolado, fora do processo Python da API | ✅ aceitável (processo separado, sem link) |
| Usar `rfdetr` puro (sem `inference`) | ✅ **mais seguro** — só o pacote Apache-2.0 |

> **Recomendação:** para o experimento, usar **`rfdetr` diretamente** (Apache-2.0) em vez de
> `inference`. Reduz superfície de licença, de dependências e de peso. O `inference` só entra se
> houver ganho concreto (Workflows, serving HTTP) — e nesse caso, isolado em container.

---

## 6. Processo de aprovação de exceção

Uma exceção só existe se **as quatro etapas** abaixo forem cumpridas e registradas.

| Etapa | O que é exigido | Quem assina |
|-------|-----------------|-------------|
| 1. Justificativa técnica | Alternativa Apache-2.0 avaliada e descartada, com números | Responsável técnico |
| 2. Avaliação jurídica | Termo da licença, obrigações, impacto no código proprietário | Jurídico (interno ou externo) |
| 3. Modelo comercial | Custo da licença comercial (ex.: Enterprise Roboflow) vs. custo de abrir código | Negócio |
| 4. Registro | ADR em `docs/adr/` + entrada no registro de licenças | Responsável técnico |

**Sem as quatro assinaturas, a dependência não entra.** "Depois a gente resolve" é proibido — a dívida
de AGPL contamina o produto de forma irreversível (o código já distribuído não "des-contamina").

### 6.1 Aprovações já concedidas

| Pacote | Aprovado? | Condição |
|--------|-----------|----------|
| `rfdetr` (Apache-2.0) | ✅ | Livre, sem condição |
| Tamanhos RF-DETR Atto/Femto/Pico/XL/2XL | ❌ | PML 1.0 — exigiria plano Roboflow em dia |
| `ultralytics` | ❌ | AGPL — bloqueado |
| `inference` | ⏸️ | Pendente de inspeção de árvore (§5) |

---

## 7. Gate de licença de **dataset** (igual em criticidade)

Licença de código e licença de dado são riscos separados. Um modelo treinado em dataset BY-NC carrega
a restrição para o produto.

### 7.1 Allowlist

| Licença | Uso comercial | Veredito |
|---------|---------------|----------|
| CC BY 4.0 | ✅ com atribuição | Permitido |
| CC BY-SA 4.0 | ⚠️ *share-alike* pode alcançar o derivado | Revisar |
| MIT | ✅ | Permitido |
| Public Domain / CC0 | ✅ | Permitido |
| **CC BY-NC 4.0** | ❌ | **Proibido** |
| "Sem licença declarada" | ❌ | **Proibido** (padrão = todos os direitos reservados) |
| Termos próprios do autor | ⚠️ | Ler antes |

### 7.2 Registro obrigatório por dataset

| Campo | Exemplo |
|-------|---------|
| `origem` | Universe / coleta própria / parceiro |
| `url` ou `local` | — |
| `licenca` | `CC BY 4.0` |
| `licenca_verificada_em` | 2026-11-20 |
| `licenca_verificada_por` | nome |
| `permite_comercial` | sim/não |
| `atribuicao_exigida` | texto da atribuição |
| `hash_manifest` | sha256 |

Sem esse registro, o dataset **não entra em treino**.

---

## 8. Procedência dos pesos de modelo

Todo peso baixado precisa de registro (tabela `modelos_registro` ou arquivo versionado):

| Campo | Por quê |
|-------|---------|
| `modelo_id` + `versao` | Reprodutibilidade |
| `licenca_no_download` | A licença pode mudar — registrar a versão vigente **na data** |
| `sha256` dos pesos | Garantir que o artefato não mudou |
| `origem_url` | Rastreabilidade |
| `data_download` | Auditoria |
| `uso_permitido` | `comercial_cloud` / `comercial_selfhosted` / `nao_comercial` |

> Ponto sensível: a Roboflow declarou que a licença comercial de YOLO self-hosted depende de **plano em
> dia** e é **add-on Enterprise**. Se um dia um modelo YOLO for usado, a licença tem prazo de validade
> ligada à assinatura — o registro precisa capturar isso, senão o produto continua rodando com licença
> vencida sem ninguém perceber.

---

## 9. Evidências a manter

| Evidência | Onde | Frequência |
|-----------|------|-----------|
| Log do gate no CI | CI | todo push |
| `pip freeze` do ambiente de produção | artefato de release | todo release |
| Registro de datasets (§7.2) | `docs/legal/datasets.md` | por dataset |
| Registro de pesos (§8) | `docs/legal/modelos.md` | por download |
| Print do "Data Licensing and Model Training" desligado | `docs/legal/roboflow-config/` | na criação e a cada 6 meses |
| Revisão da página de licenças da Roboflow | `docs/legal/licencas-roboflow.md` | trimestral (a página muda — mudou em out/2026) |

---

## 10. Estado atual (verificado estaticamente)

| Verificação | Resultado | Método |
|-------------|-----------|--------|
| `ultralytics`/YOLO em `requirements.txt` | **ausente** | leitura do arquivo (7 linhas) |
| Dependência AGPL no backend | **nenhuma identificada** | leitura das 7 deps |
| Dependência AGPL no PWA | **nenhuma identificada** | `package.json` tem `tailwindcss` (MIT) e `vitest` (MIT) |
| Pacotes LGPL presentes | `psycopg2-binary`, `fpdf2` (a confirmar por metadados) | leitura + conhecimento da licença — **confirmar com a Camada 2** |
| Dataset em uso | **nenhum** | não há pipeline de dado |
| `inference` instalado | **não** | `requirements.txt` não o contém |

**Conclusão do gate hoje: PASSA** (estado limpo), com duas pendências de verificação:
árvore de dependências do `inference` (§5) e confirmação das licenças LGPL por metadados (§3.3).

---

## 11. Critérios de aceite do gate

| ID | Critério | Evidência |
|----|----------|-----------|
| LG1 | Camada 1 roda em CI e falha o build em caso de nome proibido | job vermelho proposital registrado |
| LG2 | Camada 2 roda em CI e lista licenças do ambiente | log do CI |
| LG3 | `inference` inspecionado antes de qualquer instalação | `Requires-Dist` anexado |
| LG4 | Registro de datasets preenchido para 100% do dataset de treino | arquivo `docs/legal/datasets.md` |
| LG5 | Registro de pesos preenchido para 100% dos modelos usados | arquivo `docs/legal/modelos.md` |
| LG6 | Print da configuração de privacidade da Roboflow arquivado | `docs/legal/roboflow-config/` |
| LG7 | Nenhum pacote AGPL no ambiente de produção | `pip freeze` + Camada 2 |

**Bloqueio:** LG1, LG3 e LG7 são pré-requisito para iniciar a Trilha B (treino). LG4 é pré-requisito
para o primeiro treino. LG6 é pré-requisito para o **primeiro upload** de imagem.
