# stellSPY 2.0 — Validação Comercial e Critérios GO/NO-GO

> Todas as cifras de preço, CAC e retenção são **hipóteses a testar**, não previsões.
> O documento define como falsear cada hipótese.

## 1. Tese comercial

**O que vendemos:** não é "IA que conta material". É **prova de que o que chegou é o que foi comprado
e especificado** — com rastro datado, foto, documento e responsável identificado.

**Por que alguém paga:** porque hoje a conferência de recebimento é feita com WhatsApp, foto solta e
memória. Quando há disputa com fornecedor, não existe prova. O custo do erro é concreto e recorrente:

| Situação típica | Perda estimada (hipótese) |
|-----------------|---------------------------|
| Vergalhão de bitola errada liberado | R$ 3.000–20.000 (retrabalho + estrutura) |
| 2 t de aço faturadas e não entregues | R$ 12.000–16.000 |
| Cimento vencido aplicado | R$ 5.000–50.000 (demolição parcial) |
| Divergência aceita sem registro | Glosa do financeiro + atrito jurídico |
| Retenção sem lastro documental | Pagamento indevido ou retenção indevida |

**A conta que fecha:** uma única divergência evitada por mês paga a assinatura de várias obras.

## 2. Cliente ideal (ICP)

| Atributo | Alvo |
|----------|------|
| Segmento | Construtora de médio porte, obra vertical ou industrial |
| Faturamento | R$ 50 M–500 M/ano |
| Obras simultâneas | 3–20 |
| Volume de recebimento | ≥ 80 NF-e/mês de material controlado |
| Dor atual | Falta de rastreabilidade, auditoria interna, exigência de investidor ou cliente |
| Decisor | Diretor de engenharia, gerente de suprimentos, qualidade/PMO |
| Usuário | Fiscal de recebimento, almoxarife, engenheiro de obra |
| Sinal de compra | Já tem planilha de conferência **e** alguém dedicado a isso |

**Anti-ICP (dizer não):** obra única (não recorre), autoconstrução, construtora sem processo de
suprimentos, quem só quer "app de foto".

## 3. Modelo de receita (3 hipóteses a testar)

| Modelo | Estrutura | Prós | Contras |
|--------|-----------|------|---------|
| **A. Por obra/mês** | R$ 490 (piloto) → R$ 890 (core) por obra ativa | Previsível, fácil de explicar | Cliente pequeno acha caro; obra sazonal |
| **B. Por recebimento** | R$ 1,90/recebimento, mínimo R$ 390/mês | Justo, escala com uso | Imprevisível; desincentiva uso |
| **C. Por usuário** | R$ 149/usuário/mês | Padrão SaaS | **Mata adoção no campo** — fiscal não quer conta |

**Recomendação:** **A como base + franquia generosa de usuários** (até 10 por obra). O usuário de
campo nunca deve pensar em custo por clique. Uso (recomendação) é o que gera valor; cobrar por
usuário pune exatamente o comportamento que queremos.

### 3.1 Estrutura sugerida

| Plano | Preço (hipótese) | Inclui |
|-------|------------------|--------|
| Piloto 60 dias | R$ 490/obra/mês | 1 obra, 3 usuários, dossiê, suporte direto |
| Core | R$ 890/obra/mês | Obras ilimitadas no plano, 10 usuários, dossiê, ocorrências |
| Enterprise | sob consulta | SSO, ERP, SLA, dados em região dedicada |

### 3.2 Unit economics (hipótese)

| Item | Valor | Base |
|------|-------|------|
| Receita média por obra/mês | R$ 890 | hipótese |
| Custo de infra por obra/mês | R$ 15–30 | hosting + créditos de visão (`../roboflow/ROBOFLOW_COST_ANALYSIS.md`) |
| Custo de suporte por obra/mês | R$ 50–120 | 1 h/mês a R$ 80/h |
| **Margem bruta** | **~85–92%** | |
| CAC estimado (venda direta) | R$ 3.000–8.000 | hipótese; validar em E4 |
| Retenção média | 18–30 meses | hipótese; medir no piloto |
| **LTV** | R$ 12.000–24.000 | |
| **LTV/CAC** | **2,5–5×** | saudável se > 3 |

> Estes números são o **modelo a ser derrubado**, não a prova. O primeiro piloto existe para medir
> retenção e CAC reais.

## 4. Experimentos de validação (em ordem, com critério de morte)

| # | Experimento | Semanas | Custo | Mata se |
|---|-------------|---------|-------|---------|
| **E1** | 10 entrevistas com fiscais/engenheiros (não pitch, descoberta) | 2 | R$ 0 | < 3 de 10 descreverem **espontaneamente** o problema de conferência |
| **E2** | Concierge MVP: rodar o fluxo à mão para 1 obra (planilha + PDF + WhatsApp), sem produto novo | 3 | R$ 0 | O cliente não usar o resultado 2 semanas seguidas |
| **E3** | Piloto pago de 60 dias com 1 construtora, escopo fechado | 8 | R$ 0 | Não aceitar pagar R$ 490 (nem simbólico) → o problema não dói o bastante |
| **E4** | Teste de preço: 3 ofertas (390 / 890 / 1.900) para 3 prospects diferentes | 3 | R$ 0 | Todos escolherem a mais barata **e** houver churn por preço |
| **E5** | Teste de canal: 20 contatos frios (LinkedIn/indicação) | 3 | R$ 0 | Taxa de resposta < 10% ou 0 reuniões |
| **E6** | Teste de substituição: perguntar "o que você cancelaria para usar isto?" | junto de E1 | R$ 0 | Nada é cancelável → orçamento não existe |

**Ordem importa:** E1 e E2 custam zero e matam mais rápido. Construir a Fase 1 antes de E2 é apostar
8 semanas de engenharia em uma dor não confirmada.

## 5. Estrutura do piloto pago

| Elemento | Definição |
|----------|-----------|
| Duração | 60 dias |
| Escopo | 1 obra, 1 equipe de recebimento, 3 usuários |
| Preço | R$ 490/mês (simbólico, mas **pago** — grátis não valida nada) |
| Compromisso do cliente | 1 responsável interno, 30 min/semana de feedback |
| Compromisso nosso | acompanhamento semanal + ajuste de regra em até 5 dias |
| Métricas medidas | nº de recebimentos, % com evidência, tempo de conferência, divergências detectadas, NPS |
| Saída | relatório de 5 páginas + decisão de continuidade |

**Por que cobrar no piloto:** grátis atrai curioso. Pagamento simbólico filtra compromisso e testa
disposição a pagar com atrito mínimo.

## 6. Critérios GO/NO-GO — nível produto

Gate ao fim da **F1 + piloto** (≈ semana 12):

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| G1 | Piloto pago assinado | ≥ 1 | 0 |
| G2 | Obras ativas no piloto | ≥ 3 | < 2 |
| G3 | Recebimentos com evidência anexada | ≥ 70% | < 40% |
| G4 | Uso do fiscal (dias/semana) | ≥ 3 | < 1,5 |
| G5 | Tempo de conferência vs. manual | −30% ou melhor | sem ganho |
| G6 | NPS do fiscal | ≥ 30 | < 10 |
| G7 | Churn no piloto | 0 | ≥ 1 |
| G8 | Custo por recebimento | ≤ R$ 0,50 | > R$ 1,50 |
| G9 | Divergências detectadas que passariam batido | ≥ 5 no período | 0 |

**Regra:** 7 de 9 GO para avançar à F2. Qualquer NO-GO em G1, G6 ou G9 trava a fase.

## 7. Critérios GO/NO-GO — nível visão computacional

Gate próprio (Fase 3), detalhado em
[`../roboflow/ROBOFLOW_MODEL_EVALUATION.md`](../roboflow/ROBOFLOW_MODEL_EVALUATION.md) §6.

| Decisão | Condição |
|---------|----------|
| **GO autônomo** | MAPE ≤ 3% (vergalhão) ou ≤ 4% (saco) **e** revisão humana < 25% dos casos |
| **GO assistido** | MAPE ≤ 8% **e** o fiscal corrige em < 15 s |
| **PIVOT** | Só funciona em condições controladas (laboratório) |
| **NO-GO** | Não supera o baseline OpenCV — nesse caso, manter o baseline |

O modo assistido é **resultado aceitável**, não fracasso: gera valor (padroniza, documenta) com risco
menor.

## 8. Critérios GO/NO-GO — nível negócio (12 meses)

| # | Critério | GO | NO-GO |
|---|----------|-----|-------|
| N1 | Clientes pagantes | ≥ 5 | < 2 |
| N2 | MRR | ≥ R$ 8.000 | < R$ 2.000 |
| N3 | Receita concentrada no maior cliente | < 40% | > 70% |
| N4 | CAC payback | ≤ 6 meses | > 12 meses |
| N5 | Retenção a 6 meses | ≥ 80% | < 60% |
| N6 | Churn mensal | ≤ 3% | > 8% |
| N7 | Tempo de implantação por obra | ≤ 2 dias | > 2 semanas |

**Condição de encerramento:** se em 12 meses N1 < 2 **e** N5 < 60%, o produto não encontrou mercado.
Encerrar ou pivotar para ferramenta interna/serviço, não insistir em SaaS.

## 9. Matriz de decisão ponderada (para o comitê)

| Dimensão | Peso | Como medir |
|----------|------|-----------|
| Dor comprovada | 25% | E1 (quantos descrevem espontaneamente) |
| Disposição a pagar | 20% | E3 (piloto pago) |
| Adoção real | 20% | G4 (uso semanal) |
| Diferenciação | 15% | Cliente citaria a stellSPY se cancelasse? |
| Viabilidade técnica | 10% | Gates de CV e estabilidade |
| Escalabilidade operacional | 10% | Tempo de implantação por obra |

Score ≥ 3,5/5 → **GO**. Entre 2,5 e 3,5 → **PIVOT** (foco em 1 segmento). < 2,5 → **NO-GO**.

## 10. O que **não** fazer comercialmente

| Não fazer | Por quê |
|-----------|---------|
| Prometer "IA que conta tudo sozinha" | Garante decepção no primeiro erro |
| Vender antes da F1 | Sem evidência, é um PDF; a promessa vira dívida |
| Aceitar piloto gratuito | Não valida disposição a pagar |
| Cobrar por usuário de campo | Pune a adoção que gera valor |
| Posicionar como "substituto do engenheiro" | Risco jurídico e rejeição profissional |
| Integrar ERP no piloto | Ciclo longo; não é o que fecha a primeira venda |
| Competir com ERP em gestão | Escopo perdido; nosso diferencial é o recebimento |

## 11. Sequência recomendada dos próximos 90 dias

| Semana | Comercial | Técnico |
|--------|-----------|---------|
| 1–2 | E1 (10 entrevistas) | F0 (estancar) |
| 3–4 | E2 (concierge, 1 obra) | F1 (tenant + evidência) |
| 5–6 | E4/E5 (preço e canal) | F1 (testes de borda) |
| 7–8 | E3 (fechar piloto pago) | F1 (PWA captura) |
| 9–12 | Piloto rodando + feedback semanal | F2 (pedido + ocorrência) |
| 12 | **Gate G1–G9** | **Gate de fase** |

Se E1 falhar na semana 2, **parar** e reavaliar o produto antes de escrever a primeira migração do
2.0. Nenhum cronograma técnico sobrevive a uma dor inexistente.
