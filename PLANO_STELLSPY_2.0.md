# stellSPY 2.0 — Plano Técnico e Comercial

> **Documento de decisão.** Consolida a diretriz de produto 2.0 e o spike técnico de integração
> Roboflow em um plano executável.
> **Data:** 2026-11-03 · **Natureza:** planejamento. Nenhum código alterado, nenhuma dependência
> instalada, nenhum deploy, nenhuma conta paga, nenhuma migração executada.

---

## 1. Sumário executivo

A stellSPY tem **um núcleo de valor real e testado** — conferência NF-e × especificação com decisão
VERDE/AMARELO/VERMELHO, snapshot auditável, PDF e notificação — e **uma fundação de produto ausente**:
não existe construtora, usuário, papel, evidência, recebimento, pedido de compra nem ocorrência.

O 2.0 **não é reescrita**. É a construção da fundação em volta do núcleo, em 5 fases, sem tocar no
que funciona.

Sobre visão computacional: **é viável e barata, mas não é o gargalo** — e há duas armadilhas
concretas descobertas neste spike:

1. **Licenciamento:** YOLO (AGPL-3.0) self-hosted comercialmente **exige Enterprise add-on** na
   Roboflow. Como offline na obra implica self-hosting, escolher YOLO cria dependência contratual.
   O caminho correto é **RF-DETR (Apache-2.0)**.
2. **Pipeline:** hoje **não existe upload de imagem**. Sem construir `upload → storage → hash → fila →
   inferência → revisão`, nenhum modelo tem onde rodar.

**Decisão:** GO para o experimento de visão computacional (condicionado a 4 requisitos), e GO para o
plano 2.0 na ordem fundação → evidência → pedido → ocorrência → visão.

---

## 2. Entregáveis

### 2.1 Diretriz 2.0

| # | Entregável exigido | Documento |
|---|--------------------|-----------|
| 1 | Diagnóstico técnico atualizado | [`docs/2.0/DIAGNOSTICO_TECNICO.md`](docs/2.0/DIAGNOSTICO_TECNICO.md) |
| 2 | Arquitetura-alvo | [`docs/2.0/ARQUITETURA_ALVO.md`](docs/2.0/ARQUITETURA_ALVO.md) |
| 3 | Mapa de funcionalidades (existentes × faltantes) | [`DIAGNOSTICO_TECNICO.md §3`](docs/2.0/DIAGNOSTICO_TECNICO.md) |
| 4 | Modelo de dados | [`docs/2.0/MODELO_DE_DADOS.md`](docs/2.0/MODELO_DE_DADOS.md) |
| 5 | Roadmap por fases | [`docs/2.0/ROADMAP_E_COMPLEXIDADE.md`](docs/2.0/ROADMAP_E_COMPLEXIDADE.md) |
| 6 | Estimativa de complexidade | [`ROADMAP_E_COMPLEXIDADE.md §8`](docs/2.0/ROADMAP_E_COMPLEXIDADE.md) |
| 7 | Matriz de riscos | [`docs/2.0/RISCOS_E_PLANO_DE_TESTES.md §I`](docs/2.0/RISCOS_E_PLANO_DE_TESTES.md) |
| 8 | Plano de testes | [`RISCOS_E_PLANO_DE_TESTES.md §II`](docs/2.0/RISCOS_E_PLANO_DE_TESTES.md) |
| 9 | Estratégia de validação comercial | [`docs/2.0/VALIDACAO_COMERCIAL_GONOGO.md`](docs/2.0/VALIDACAO_COMERCIAL_GONOGO.md) |
| 10 | Critérios objetivos GO/NO-GO | [`VALIDACAO_COMERCIAL_GONOGO.md §6–8`](docs/2.0/VALIDACAO_COMERCIAL_GONOGO.md) |

### 2.2 Spike Roboflow

| # | Entregável exigido | Documento |
|---|--------------------|-----------|
| 1 | Viabilidade (Annotate, Train, Workflows, Inference, cloud, self-host, export, licença, custo) | [`ROBOFLOW_FEASIBILITY.md`](docs/roboflow/ROBOFLOW_FEASIBILITY.md) |
| 2 | Arquitetura do adaptador | [`ROBOFLOW_ARCHITECTURE.md`](docs/roboflow/ROBOFLOW_ARCHITECTURE.md) |
| 3 | Custos e limites do plano gratuito | [`ROBOFLOW_COST_ANALYSIS.md`](docs/roboflow/ROBOFLOW_COST_ANALYSIS.md) |
| 4 | Avaliação dos primeiros modelos (sacos, vergalhões, OCR) | [`ROBOFLOW_MODEL_EVALUATION.md`](docs/roboflow/ROBOFLOW_MODEL_EVALUATION.md) |
| 5 | Plano de integração | [`ROBOFLOW_INTEGRATION_PLAN.md`](docs/roboflow/ROBOFLOW_INTEGRATION_PLAN.md) |
| 6 | Decisão final GO/NO-GO | §4 deste documento |

### 2.3 Auditoria de base

| Documento | Conteúdo |
|-----------|----------|
| [`ANALISE_PROJETO.md`](ANALISE_PROJETO.md) | Auditoria completa do repositório: 14 achados (6 altos), segurança, testes, documentação |

---

## 3. Cinco achados que mudam o plano

| # | Achado | Fonte | Consequência |
|---|--------|-------|--------------|
| 1 | **Não existe upload de imagem.** Só `foto_url` (texto, baixado pelo servidor) | grep no repo | Pipeline de evidência é pré-requisito de qualquer visão |
| 2 | **YOLO self-hosted comercial = Enterprise add-on.** RF-DETR Nano–Large é Apache-2.0 e livre | [roboflow.com/licensing](https://roboflow.com/licensing) | Padronizar RF-DETR; YOLO só como benchmark |
| 3 | **"Data Licensing and Model Training" vem LIGADO** em workspaces novos | [docs/roboflow.com/…/plans](https://docs.roboflow.com/platform/billing-and-plans/plans) | Desligar **antes** do primeiro upload, ou LGPD em risco |
| 4 | **Self-hosted não consome crédito**; cloud custa 0,125–0,1875 cr/1.000 imagens | [roboflow.com/credits](https://roboflow.com/credits) | Inferência nunca será o gargalo de custo: 10 créditos/mês ≈ 53–80 mil imagens |
| 5 | **Não há identidade de usuário nem construtora** no schema; `usuario_id` do override é string livre | grep em `supabase/` | RBAC, auditoria nominal e multiempresa exigem fundação nova |

---

## 4. Decisão GO/NO-GO — experimento de visão computacional

### 4.1 Veredito

> ## **GO CONDICIONADO**
>
> Primeiro experimento com **vergalhão** e **sacos de cimento**, usando **RF-DETR Apache-2.0**,
> com custo monetário **zero** e duração de **6 semanas**.

### 4.2 Condições não negociáveis

| # | Condição | Verificação |
|---|----------|-------------|
| C1 | Modelo base em **RF-DETR Nano→Large** (Apache-2.0). Nenhuma dependência AGPL | `requirements.txt` sem `ultralytics` |
| C2 | **"Data Licensing and Model Training" DESLIGADO** antes do 1º upload | Print do workspace anexado ao relatório |
| C3 | Projetos **privados**, nada publicado em Universe; datasets com licença verificada (BY-NC proibido) | Checklist de licença por dataset |
| C4 | Apenas imagens próprias ou com autorização escrita; nenhuma imagem de cliente sem base legal | Termo de uso de imagem assinado |

### 4.3 Critérios objetivos de aprovação (pré-registrados)

**Vergalhão** (≥ 150 imagens não vistas, anotador cego):

| Critério | GO | NO-GO |
|----------|-----|-------|
| MAPE em feixes ≤ 50 barras | ≤ 3% | > 6% |
| Imagens com erro zero | ≥ 75% | < 55% |
| Viés de sub/supercontagem | \|viés\| ≤ 1% | > 3% |
| Separação de 3 bitolas (F1) | ≥ 0,90 | < 0,75 |
| Latência p95 | ≤ 3 s | > 6 s |

**Sacos de cimento:**

| Critério | GO | NO-GO |
|----------|-----|-------|
| MAE em pilhas ≤ 50 sacos | ≤ 1,0 saco | > 2,0 |
| Imagens com erro zero | ≥ 70% | < 50% |
| MAPE global | ≤ 4% | > 8% |
| Tempo de revisão humana | ≤ 15 s | > 30 s |

**Regra composta:** `GO` = todos os critérios na faixa GO **e** licença Apache-2.0 **e** custo
≤ R$ 0,05/recebimento. `PIVOT` = 1–2 na faixa intermediária → modo assistido obrigatório.
`NO-GO` = qualquer critério na faixa NO-GO.

### 4.4 Ordem recomendada

**Vergalhão primeiro**, não sacos. Motivos: é o material núcleo do produto atual; o erro de bitola é o
mais caro; o objeto é rígido e regular; e existe *use case* oficial na plataforma
([Roboflow — Rebar counting](https://universe.roboflow.com/use-cases/rebar-counting)). Sacos são o
teste mais difícil —começar por eles é apostar o cronograma na categoria com maior chance de NO-GO.

### 4.5 Onde já é NO-GO hoje

| Item | Veredito |
|------|----------|
| Contagem autônoma de sacos sem revisão humana | **NO-GO** |
| IA substituindo a conferência NF-e × especificação | **NO-GO** por definição de produto |
| YOLO self-hosted comercial sem contrato Enterprise | **NO-GO** jurídico |
| VLM/agente generativo como contador | **NO-GO** por decisão de produto |
| OCR automático de validade/lote | **NO-GO** neste estágio |
| "Offline resolvido pelo Roboflow Inference" | **NO-GO** — não é verdade |

---

## 5. Decisão — plano 2.0

### 5.1 Ordem de execução

```
F0 (2 sem)  Estancar: 6 bugs altos + CI
F1 (6 sem)  Identidade + multiempresa + EVIDÊNCIA + recebimento   ← vendável
F2 (6 sem)  Pedido de compra + ocorrência + dossiê                ← vendável
F3 (8 sem)  Visão computacional + OCR restrito (se GO)            ← vendável
F4 (8 sem)  Retenção + certificados + indicadores + ERP           ← vendável
F5 (6 sem)  Offline e sincronização                               ← requisito de campo
```

**Total:** ~36 semanas · 111–140 dias-dev · 1 desenvolvedor sênior.

### 5.2 Por que esta ordem e não outra

- **F0 antes de tudo:** A1 (SSRF), A2 (produto nunca bloqueia), A3 (override inconsistente) e A4
  (devolução inalcançável) tornariam insegura qualquer fase seguinte.
- **F1 antes de vendas:** sem evidência e sem autor identificado, o produto é um PDF — e o dossiê
  seria uma ficção.
- **F1 antes de F3:** o modelo não tem onde rodar sem storage e upload.
- **F2 antes de F3:** sem pedido de compra, a visão computacional só recontaria o que a NF já diz.
  O valor da contagem aparece quando existe um **compromisso** com o qual comparar.

### 5.3 O que **não** será feito

- Reescrever `domain/conferente.py`, `chave_nfe.py`, `pwa_session.py`, `fila_retentativa.py`,
  `whatsapp_evolution.py` — são bons e testados.
- Microserviços, Kubernetes, event streaming.
- App nativo nesta fase (offline nativo é Fase 6+, se algum dia).
- Qualquer ação automática que libere ou bloqueie pagamento.

---

## 6. Os cinco riscos que exigem atenção agora

| Rank | Risco | Score | Ação |
|------|-------|-------|------|
| 1 | **Dependência de uma única pessoa** | 25 | Este pacote de documentos + CI + commits pequenos |
| 2 | **Produto sem comprador** (dor não validada) | 20 | Rodar E1 (10 entrevistas) **antes** da primeira migração |
| 3 | **Exposição de dados de cliente** (bucket público, imagem sem base legal) | 20 | F0 + F1: bucket privado, EXIF strip, política de retenção |
| 4 | **Ausência de testes de borda** | 20 | F0: TestClient + Postgres em container |
| 5 | **Escopo 12 módulos > capacidade** | 20 | Disciplina de fase e gate; dizer não é requisito |

---

## 7. Próximos 30 dias (concreto)

| Semana | Comercial | Técnico |
|--------|-----------|---------|
| 1 | Agendar 10 entrevistas (E1) | F0: A1, A2, A6, `.gitignore`, CI |
| 2 | E1 concluído → decidir se a dor existe | F0: A3, A4, A5, M1 (reaper) |
| 3 | E2 (concierge, 1 obra) | F1: `tenant_id` + `construtoras` + role de app |
| 4 | E4/E5 (preço e canal) | F1: `usuarios`, RBAC, teste de isolamento |

**Ponto de parada:** se E1 não confirmar a dor, **não** iniciar F1. Nenhum cronograma técnico
sobrevive a uma dor inexistente.

---

## 8. Conformidade com as restrições

| Restrição | Status |
|-----------|--------|
| Não iniciar implementação | ✅ Nenhuma linha de código de produto alterada |
| Não executar migrations em produção | ✅ Nenhuma migração criada ou executada |
| Não fazer deploy | ✅ Nada publicado |
| Não contratar serviços / adicionar custos | ✅ Nenhuma conta criada; custo incorrido US$ 0 |
| Priorizar open source e infra existente | ✅ RF-DETR Apache-2.0 + Inference Apache-2.0 + Postgres/Supabase já em uso |
| Não duplicar funcionalidades | ✅ Mapa de funcionalidades em `DIAGNOSTICO_TECNICO.md §3` |
| Não reescrever sem justificativa | ✅ Lista explícita de preservação em `DIAGNOSTICO_TECNICO.md §6` |
| Somente análise e planejamento (spike) | ✅ Os 5 `ROBOFLOW_*.md` são documentos |

**Limitação de método:** a sessão não teve shell funcional
(`SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)`), então nada foi executado — nem testes,
nem build, nem `git status`. Toda afirmação sobre o repositório vem de leitura e busca textual.
