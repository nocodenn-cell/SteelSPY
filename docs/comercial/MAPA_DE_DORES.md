# MAPA DE DORES — Hipóteses e Estrutura de Evidência

> ## ⚠️ Este documento NÃO contém achados
>
> **Status: 12 hipóteses formuladas · 0 confirmadas · 0 refutadas · 0 entrevistas realizadas.**
>
> O que está aqui é o **mapa de hipóteses** que a sprint deve testar, com o sinal que confirma e o que
> refuta cada uma. Nenhuma linha de "evidência" foi preenchida com suposição. Preencher este mapa com
> intuição seria pior do que deixá-lo vazio — produziria uma decisão de investimento baseada em ficção.

---

## 1. Como ler

| Elemento | Significado |
|----------|-------------|
| **H** | Hipótese falsificável sobre a dor |
| **Persona** | Quem, dentro da construtora, tem a informação (não quem "acha") |
| **Pergunta** | A pergunta do roteiro que testa a hipótese |
| **Confirma se** | Observação concreta que sustenta |
| **Refuta se** | Observação que derruba |
| **Peso** | Quanto a hipótese é *load-bearing* para o produto. Peso 3 = se cair, o produto cai |

**Regra de triangulação:** uma dor só é considerada **real** se aparecer em **≥ 2 personas da mesma
empresa** (ex.: almoxarife diz que falta registro **e** o financeiro confirma que não tem prova). Uma
única voz é opinião; duas vozes independentes são estrutura.

---

## 2. As 12 hipóteses

### H1 — Frequência · peso 3

**Hipótese:** o recebimento de material controlado (aço, cimento, bloco) acontece **≥ semanalmente**
e se concentra em **1–2 pessoas**.

| | |
|---|---|
| Persona | A (almoxarife), E (engenheiro) |
| Pergunta | "Na última semana, quantos recebimentos de material controlado aconteceram? Quem estava lá?" |
| Confirma se | ≥ 1 recebimento/semana **e** o responsável acumula outra função |
| Refuta se | recebimento mensal ou menos, ou equipe dedicada com processo maduro |
| Se cair | o produto não vira hábito; a tese de SaaS recorrente cai |

### H2 — Registro · peso 3

**Hipótese:** a conferência é registrada de forma **não estruturada** (papel, WhatsApp, memória), sem
rastro consultável.

| | |
|---|---|
| Persona | A, F |
| Pergunta | "Onde isso é registrado? Me mostra como ficou o último." |
| Confirma se | planilha solta, caderno, grupo de WhatsApp, ou "não registra" |
| Refuta se | ERP com módulo de recebimento **em uso efetivo** |
| Se cair | o produto vira "mais um lugar para digitar" — e não há dor de prova |

### H3 — NF × pedido · peso 3

**Hipótese:** a NF-e **não é conferida sistematicamente** contra o pedido de compra.

| | |
|---|---|
| Persona | C (comprador), F |
| Pergunta | "O recebimento é comparado com o pedido? Por quem, como?" |
| Confirma se | "o comprador confere depois", "só se desconfiar", "não dá tempo" |
| Refuta se | conferência 3-way automática no ERP |
| Se cair | metade do valor do 2.0 (módulo 4) perde sentido |

### H4 — NF × especificação · peso 3

**Hipótese:** a NF **não é conferida** contra a especificação técnica do projeto (bitola, tipo de
cimento, classe de bloco).

| | |
|---|---|
| Persona | E, A |
| Pergunta | "Existe conferência contra a especificação? Quem faz?" |
| Confirma se | "o engenheiro olha por cima", "confio no fornecedor", "já vem certo" |
| Refuta se | checklist técnico formal por entrega |
| Se cair | o núcleo atual da stellSPY (conferência × especificação) perde a dor |

### H5 — Divergências silenciosas · peso 3

**Hipótese:** divergências de quantidade, bitola e marca **ocorrem** e **não são registradas**.

| | |
|---|---|
| Persona | A, E |
| Pergunta | "Já chegou bitola diferente? Conta como foi." |
| Confirma se | relato concreto com desfecho (aceitou, devolveu, aplicou) |
| Refuta se | "nunca aconteceu" repetido em 8 de 10 |
| Se cair | não há ocorrência para gerir (módulo 7) |

### H6 — Perda quantificável · peso 3

**Hipótese:** existe **perda financeira quantificada em R$** nos últimos 12 meses, e o entrevistado
**sabe o número** (ou sabe estimar com confiança).

| | |
|---|---|
| Persona | D, F |
| Pergunta | "Quanto isso custou, em reais?" (insistir com gentileza) |
| Confirma se | número concreto ou faixa defensável |
| Refuta se | "não sei", "nunca somei", resposta genérica em todos |
| Se cair | o produto é "nice to have"; não há orçamento, só curiosidade |

> **Esta é a hipótese mais importante da sprint.** Se H6 cair, todas as outras podem ser verdadeiras e
> o negócio ainda não fecha.

### H7 — Pagamento sem prova · peso 2

**Hipótese:** o financeiro paga a NF **sem prova física** de que o material chegou.

| | |
|---|---|
| Persona | F |
| Pergunta | "Descreve o caminho da NF até o pagamento. Qual documento prova a entrega?" |
| Confirma se | "confio no almoxarife", "o fiscal assina o canhoto", "a nota é a prova" |
| Refuta se | 3-way match com recebimento no ERP |
| Se cair | o elo com dinheiro (módulo 9) perde força |

### H8 — Retenção informal · peso 2

**Hipótese:** já houve retenção, glosa ou desconto por divergência — **informalmente**.

| | |
|---|---|
| Persona | F, C |
| Pergunta | "Já aconteceu de o financeiro segurar pagamento? Com base em quê?" |
| Confirma se | "segurei no telefone", "descontei da próxima", sem documento |
| Refuta se | nunca ocorreu / processo formal com lastro |
| Se cair | "solicitação de retenção" (módulo 9) vira feature sem uso |

### H9 — Rastreabilidade em auditoria · peso 2

**Hipótese:** a falta de rastro já gerou **consequência externa** (auditoria, investidor, seguro,
certificação, disputa judicial).

| | |
|---|---|
| Persona | D, F |
| Pergunta | "Se um auditor pedisse a prova de um recebimento de 8 meses atrás, o que existiria?" |
| Confirma se | caso real com consequência (apontamento, ressalva, perda) |
| Refuta se | "nunca precisamos" |
| Se cair | o dossiê (módulo 8) é conveniência, não necessidade |

### H10 — Orçamento e autoridade · peso 3

**Hipótese:** existe **orçamento** e **autoridade** para contratar software operacional na faixa
R$ 200–1.000/mês por contrato.

| | |
|---|---|
| Persona | D |
| Pergunta | "Qual orçamento existe para software de obra? Quem assina? Qual o limite sem ir ao board?" |
| Confirma se | verba anual, limite de alçada citado, já assinou compra similar |
| Refuta se | "nada acima de R$ 100", "tudo passa pelo conselho", nunca comprou software |
| Se cair | ciclo de venda inviável para 1 pessoa; o modelo de negócio precisa mudar |

### H11 — Dor não reconhecida (hipótese de refutação) · peso 3

**Hipótese (contrária):** o processo atual é percebido como **suficiente** — a dor não está na agenda.

| | |
|---|---|
| Persona | todas |
| Pergunta | indireta: "o que te tira o sono na obra hoje?" (se recebimento não aparecer espontaneamente) |
| Confirma (de que não há dor) se | recebimento **não** surge espontaneamente em ≥ 7 de 10 |
| Refuta (de que há dor) se | surge espontaneamente, sem você mencionar |

> **Por que esta hipótese existe:** para impedir que a entrevista vire busca de confirmação. A dor só é
> prioritária se o entrevistado a mencionar **antes** de você perguntar. Dor induzida é dor fabricada.

### H12 — Influência do comprador · peso 1

**Hipótese:** o comprador/suprimentos tem influência para **puxar** a adoção de ferramenta operacional.

| | |
|---|---|
| Persona | C, D |
| Pergunta | "Quem decide comprar uma ferramenta para o recebimento?" |
| Confirma se | o comprador é sponsor ou co-decisor |
| Refuta se | só o diretor decide e ninguém mais opina |
| Se cair | a estratégia de venda muda (foco só em D) |

---

## 3. Matriz de triangulação (preencher por empresa)

Só marcar ✅ quando **duas personas da mesma empresa** sustentarem a hipótese.

| Empresa | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 | H9 | H10 | H11 | H12 |
|---------|----|----|----|----|----|----|----|----|----|-----|-----|-----|
| Construtora A | | | | | | | | | | | | |
| Construtora B | | | | | | | | | | | | |
| Construtora C | | | | | | | | | | | | |
| Construtora D | | | | | | | | | | | | |
| Construtora E | | | | | | | | | | | | |
| Construtora F | | | | | | | | | | | | |
| Construtora G | | | | | | | | | | | | |
| Construtora H | | | | | | | | | | | | |
| Construtora I | | | | | | | | | | | | |
| Construtora J | | | | | | | | | | | | |

**Legenda:** ✅ triangulada · ◐ uma voz · ✗ refutada · vazio = sem dado

---

## 4. Tabela de evidências (preencher após cada entrevista)

| H | Fonte (E##) | Trecho literal | Tipo de evidência | Força |
|---|-------------|----------------|-------------------|-------|
| H1 | | | relato / número / documento | 1–3 |
| H2 | | | | |
| H3 | | | | |
| H4 | | | | |
| H5 | | | | |
| H6 | | | | |
| H7 | | | | |
| H8 | | | | |
| H9 | | | | |
| H10 | | | | |
| H11 | | | | |
| H12 | | | | |

**Força da evidência:** 3 = número/documento · 2 = relato concreto com desfecho · 1 = opinião genérica.

---

## 5. Dores que o produto **não** resolve (evitar escopo)

Registrar quando aparecerem, mas **não** transformar em requisito:

| Dor adjacente | Por que está fora |
|---------------|-------------------|
| Atraso de entrega do fornecedor | Logística, não auditoria |
| Preço acima do combinado | Financeiro/negociação, não recebimento físico |
| Qualidade do material depois de aplicado | Controle tecnológico, não recebimento |
| Gestão de estoque e consumo | ERP; escopo diferente |
| Programação de mão de obra | Planejamento |
| Emissão/validação fiscal da NF | Obrigação do emitente |

> Se 3 ou mais entrevistados apontarem uma dor adjacente **com mais intensidade** que a dor de
> recebimento, isso é um sinal forte de reposicionamento — e vai para
> `VALIDACAO_COMERCIAL_RESULTADOS.md`, não para o backlog.

---

## 6. Estado atual do mapa

| Métrica | Valor |
|---------|-------|
| Hipóteses formuladas | 12 |
| Hipóteses com ≥ 1 evidência | **0** |
| Hipóteses trianguladas (≥ 2 personas/empresa) | **0** |
| Hipóteses refutadas | **0** |
| Entrevistas que sustentam o mapa | **0 de 10** |

**Conclusão do mapa hoje: nenhuma dor do recebimento está confirmada.** O mapa está pronto para
receber evidência; não contém nenhuma.
