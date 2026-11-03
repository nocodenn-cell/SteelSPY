# ANÁLISE DE DISPOSIÇÃO DE PAGAMENTO

> **Status: 0 entrevistas realizadas.** Este documento tem duas partes com naturezas diferentes e
> separadas de propósito:
>
> - **Parte I — âncoras de mercado:** verificável hoje, com fonte. É análise real.
> - **Parte II — estrutura de apuração:** o instrumento que vai medir a disposição a pagar nas
>   entrevistas. **Está vazia**, porque não houve entrevista.
>
> O preço hipotético anterior (`docs/2.0/VALIDACAO_COMERCIAL_GONOGO.md`: R$ 490 piloto / R$ 890 core
> por obra) é **questionado** pela Parte I e precisa ser re-testado. Não foi alterado por decreto — foi
> colocado em dúvida por dado de mercado.

---

# PARTE I — ÂNCORAS DE MERCADO (verificável)

## 1. O que o mercado cobra hoje

| Player | Posicionamento | Preço público | Fonte |
|--------|----------------|---------------|-------|
| **RDObras** (via Omie.Store) | Gestão de obra + RDO + requisições + **"controle de recebimentos de insumos"** | **a partir de R$ 497,00/mês**; implantação autônoma; consultoria avulsa R$ 120/h; reajuste por IGPM | [Omie.Store — RDObras](https://store.omie.com.br/apps/rd-obras) |
| **Sienge** | Suíte enterprise (incorporação, obra, pós-venda) + Construcompras + Construpoint | **sob consulta** (sem preço público) | [sienge.com.br/precos](https://sienge.com.br/precos-do-sienge-plataforma-sob-medida-para-sua-construtora/) |
| **Gestor Obras** (Sienge) | "Solução ágil para pequenas construtoras" | sob consulta | mesmo site |
| **Koper** | Gestão para construtoras, com página de planos | valores não capturáveis sem JS; existe página de planos | [koper.com.br/planos](https://koper.com.br/planos/) |
| **Totvs / Omie ERP** | ERP generalista com módulo de obra | planos próprios | — |

### 1.1 Duas leituras que importam

**Leitura 1 — o padrão de preço do segmento PME é ~R$ 500/mês por empresa.**
O RDObras anuncia R$ 497/mês como entrada, com escopo amplo (orçamento, cronograma, RDO, medição,
estoque, requisições). Não há, na página, cobrança por obra — aparentemente é valor por empresa
**[a confirmar em entrevista]**.

**Leitura 2 — o mercado enterprise não publica preço.**
Sienge e Totvs vendem por proposta, com implantação. Isso significa que **o comprador do nosso ICP já
foi treinado** a: (a) ver preço por empresa, não por obra; (b) esperar demonstração + proposta;
(c) comparar com uma suíte inteira, não com um ponto.

## 2. O problema que isso cria para o preço hipotético anterior

A hipótese anterior era **R$ 890 por obra/mês** no plano core.

| Cenário | Preço SteelSpy (hipótese antiga) | Referência de mercado | Razão |
|---------|----------------------------------|------------------------|-------|
| 1 obra | R$ 890/mês | R$ 497/mês (suíte inteira) | **1,8×** |
| 3 obras | R$ 2.670/mês | R$ 497/mês | **5,4×** |
| 10 obras | R$ 8.900/mês | R$ 497/mês | **17,9×** |

> **Conclusão dura:** um produto de **um único ponto do processo** não sustenta, no papel, preço por
> obra acima de uma suíte de gestão de obra inteira. O comprador vai comparar assim, mesmo que a
> comparação seja injusta (profundidade ≠ amplitude). Isso precisa ser testado e, provavelmente,
> corrigido antes de qualquer proposta.

**Três saídas possíveis — todas hipóteses a testar:**

| Saída | Preço | Racional |
|-------|-------|----------|
| A. Preço por obra baixo | R$ 190–290/obra/mês | Comparável a "módulo", não a "sistema" |
| B. Preço por empresa com franquia | R$ 690–990/empresa/mês até 3 obras | Alinha com o padrão de mercado observado |
| C. Preço por recebimento | R$ 2–4/recebimento, mínimo R$ 390 | Cobra pelo uso, ancora no esforço |

## 3. Inteligência competitiva já visível

O RDObras **já anuncia** "Controle de Recebimentos de Insumos: acompanhe o quantitativo dos insumos
recebidos em suas obras com base no que foi previsto".

Isso é importante e desconfortável:

| O que o concorrente cobre | O que ele **não** cobre (a nossa cunha) |
|---------------------------|------------------------------------------|
| Quantitativo previsto × recebido | Prova por item: foto, hash, data, responsável |
| Registro no ERP | Divergência como **ocorrência** com ciclo de vida |
| Requisição de compra | Conferência contra **especificação técnica** (bitola, FCK, dimensões) |
| RDO | Dossiê auditável para terceiro (auditor, investidor, fornecedor) |

> A pergunta que a sprint precisa responder: **o comprador percebe essa diferença, ou ouve "já tenho
> isso no sistema"?** Se ouvir a segunda, o posicionamento precisa mudar — não o produto.

---

# PARTE II — ESTRUTURA DE APURAÇÃO (a preencher)

## 4. Regra fundamental: interesse ≠ intenção de compra

**Frase para colar na parede da sprint:**

> Interesse em tecnologia é curiosidade. Intenção de compra é **comportamento passado** e
> **compromisso presente**. Só os dois últimos contam.

| Sinal fraco (não conta) | Sinal forte (conta) |
|-------------------------|---------------------|
| "Que legal isso" | "Já pagamos R$ X por mês por algo parecido" |
| "Faz sentido" | "Quem assina é o [nome], posso te apresentar" |
| "Precisamos disso" | "Me manda o contrato do piloto" |
| "Manda uma proposta" | "Quanto custa? Pode começar quando?" |
| "Depois a gente vê" | "Vou reservar orçamento para o próximo trimestre" |
| "Se for barato eu uso" | "O valor está dentro do que pagamos" |

## 5. Os cinco sinais comportamentais (S1–S5)

Cada um só conta se observado **na fala concreta**, não inferido.

| # | Sinal | Pergunta que revela | Pontuação |
|---|-------|---------------------|-----------|
| S1 | Já paga por software similar | "Quais softwares pagos vocês usam na obra? Quanto por mês?" | 0 = nenhum · 1 = ≤ R$ 300 · 2 = R$ 300–1.000 · 3 = > R$ 1.000 |
| S2 | Orçamento nomeado e disponível | "Existe verba para isso? Onde está?" | 0 = não · 1 = "talvez" · 2 = verba anual · 3 = verba com saldo |
| S3 | Autoridade identificada e acessível | "Quem assina? Qual o limite sem ir ao board?" | 0 = desconhecido · 1 = board · 2 = diretor · 3 = decisor presente na conversa |
| S4 | Perda >> preço | "Quanto custou a última?" | 0 = não sabe · 1 = < 3× preço · 2 = 3–10× · 3 = > 10× o preço anual |
| S5 | Aceita piloto pago | "Toparia pagar um piloto simbólico de R$ 490 para 60 dias?" | 0 = não · 1 = "depois" · 2 = "acho que sim" · 3 = sim agora |

**Score de disposição (máx. 15):** ≥ 11 = oportunidade qualificável · 7–10 = morno · ≤ 6 = não compra.

## 6. Calculadora de valor (fazer na frente do entrevistado)

Fórmula:

```
Custo anual da dor = (erros por mês) × (perda média por erro) × 12
Preço justificável  = Custo anual da dor × taxa de captura (10% a 30%)
```

### 6.1 Quanto a construtora precisa perder para justificar cada preço

| Preço mensal | Custo anual | Perda anual necessária @ 30% de captura | @ 10% |
|--------------|-------------|------------------------------------------|-------|
| R$ 290 | R$ 3.480 | R$ 11.600 | R$ 34.800 |
| R$ 490 | R$ 5.880 | R$ 19.600 | R$ 58.800 |
| R$ 890 | R$ 10.680 | R$ 35.600 | R$ 106.800 |
| R$ 1.900 | R$ 22.800 | R$ 76.000 | R$ 228.000 |

> **Pergunta de validação:** "vocês perdem R$ 35 mil por ano em recebimento?" Se a resposta for "não,
> muito menos", o preço de R$ 890 por obra está acima do valor capturável — independentemente de o
> produto ser bom.

### 6.2 Perdas de referência (usar só como âncora, não como verdade)

Valores do plano comercial anterior — **hipóteses, não dados de entrevista**:

| Situação | Ordem de grandeza |
|----------|-------------------|
| Vergalhão de bitola errada liberado | R$ 3.000–20.000 |
| 2 t de aço faturadas e não entregues | R$ 12.000–16.000 |
| Cimento vencido aplicado | R$ 5.000–50.000 |

Se o entrevistado relatar um caso **nessa ordem de grandeza**, 1 a 3 casos/ano já justificam R$ 290–490.

## 7. Escada de preço a testar (não é tabela de venda)

| Oferta | Estrutura | Quando testar |
|--------|-----------|---------------|
| P1 | R$ 290/obra/mês (mín. 2 obras) | conversas com engenheiro/comprador |
| P2 | R$ 690/empresa/mês até 3 obras | conversas com diretor |
| P3 | R$ 1.900/empresa/mês até 10 obras | construtora média/grande |
| P4 | R$ 3,00/recebimento, mínimo R$ 390 | quem rechaza assinatura mensal |

**Método de teste (sem induzir):** perguntar primeiro o que pagam hoje (S1), depois apresentar **uma**
oferta e registrar a reação literal — não as três. Apresentar três transforma a conversa em menu e o
entrevistado escolhe a mais barata por reflexo.

## 8. Tabela de apuração (vazia)

| ID | Perfil | S1 | S2 | S3 | S4 | S5 | **Total /15** | Preço citado | Reação literal | Qualificável? |
|----|--------|----|----|----|----|----|---------------|--------------|----------------|---------------|
| E01 | D | | | | | | | | | |
| E02 | D | | | | | | | | | |
| E03 | E | | | | | | | | | |
| E04 | E | | | | | | | | | |
| E05 | A | | | | | | | | | |
| E06 | A | | | | | | | | | |
| E07 | C | | | | | | | | | |
| E08 | C | | | | | | | | | |
| E09 | F | | | | | | | | | |
| E10 | F | | | | | | | | | |

## 9. Objeções de preço (registrar literalmente)

| Objeção | O que perguntar em seguida |
|---------|----------------------------|
| "Está caro" | "Caro comparado a quê?" (registrar a referência) |
| "Não tenho orçamento" | "Quando abre o orçamento? Quem decide?" |
| "Já pago o Sienge" | "Quanto? O que ele resolve do recebimento?" |
| "Se for barato, eu uso" | "Quanto seria barato o suficiente para você assinar hoje?" |
| "Vou esperar a obra acabar" | "E na próxima obra, entra?" |
| "Preciso ver com o diretor" | "Posso falar com ele? O que ele vai querer saber?" |

## 10. O que **não** concluir

| Proibido concluir | Por quê |
|-------------------|---------|
| "O mercado aceita R$ 890" | Sem entrevista, é hipótese |
| "O mercado rejeita R$ 890" | Mesma coisa, ao contrário |
| "RDObras é concorrente direto" | É adjacente; a sobreposição é parcial |
| "Se 8 disserem que é caro, baixamos o preço" | Dizer "caro" é gratuito; comportamento não é |
| "Quem não respondeu não tem a dor" | Pode ser só canal errado |

## 11. Estado atual

| Item | Estado |
|------|--------|
| Âncoras de mercado verificadas | ✅ 1 preço público (R$ 497) + 2 sob consulta |
| Hipótese de preço anterior questionada | ✅ sim (razão 1,8×–17,9×) |
| Disposição a pagar medida em campo | ❌ **0 de 10** |
| Oferta recomendada | ❌ **não definida** — depende dos dados |
| Oportunidade qualificável identificada | ❌ **nenhuma** |
