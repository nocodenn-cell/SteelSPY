# DECISÃO GO/NO-GO COMERCIAL

> ## Decisão vigente: **NO-GO PROVISÓRIO — gate fechado**
>
> **Data:** 2026-11-03 · **Base:** 0 de 10 entrevistas realizadas.
>
> Não é uma decisão de mérito sobre o produto. É o estado correto de um gate que exige evidência e não
> a tem. O padrão de um gate sem dados é **fechado** — não "aberto até prova contrária".
>
> **Consequência imediata:** a Fase 0 (fundação: tenant, identidade, evidências) **não está autorizada a
> começar** com base nesta sprint. A autorização anterior (`docs/execucao/MATRIZ_GO_NO_GO.md`,
> Decisão #1) fica **condicionada** aos critérios de §3.

---

## 1. Por que NO-GO e não "indefinido"

| Raciocínio | Consequência |
|------------|--------------|
| Não há evidência de dor recorrente | Não se justifica investir 31 dd de fundação |
| Não há evidência de impacto financeiro | Não se justifica definir preço |
| Não há oportunidade qualificável | Não há piloto para financiar o desenvolvimento |
| Já existe concorrente adjacente anunciando "controle de recebimentos" | A diferenciação ainda não foi testada com comprador |

**Alternativa rejeitada:** tratar como "GO condicional" para não travar o cronograma. Isso inverteria a
lógica do gate: transformaria ausência de dado em permissão. É exatamente o erro que a diretriz proíbe
("Não confundir interesse em tecnologia com intenção de compra").

---

## 2. Critérios de GO (definidos pela diretriz)

| # | Critério | Como será medido | Evidência exigida | Status |
|---|----------|------------------|-------------------|--------|
| **G1** | Dor **recorrente** | relatada em ≥ 6/10 **e** triangulada em ≥ 3 empresas | `MAPA_DE_DORES.md` §3–4 | ❌ 0/10 |
| **G2** | Processo atual com **limitações demonstráveis** | ≥ 6/10 sem registro estruturado **e** caso concreto de falha | fichas E01–E10 + citação | ❌ 0/10 |
| **G3** | **Impacto operacional ou financeiro** identificável | ≥ 5/10 com perda concreta (número ou caso com desfecho) | `ENTREVISTAS_REGISTRO.md` campo `perda_rs` | ❌ 0/10 |
| **G4** | **Interesse concreto** em testar | ≥ 3/10 oferecem teste ou apresentam o decisor | fichas + follow-up registrado | ❌ 0/10 |
| **G5** | **≥ 1 oportunidade comercial qualificável** | 1 empresa com dor triangulada **e** score WTP ≥ 11/15 **e** decisor identificado | `VALIDACAO_COMERCIAL_RESULTADOS.md` §5 | ❌ 0 |

**Regra de aprovação:** **G1 ∧ G2 ∧ G3 ∧ (G4 ∨ G5)** → GO.
**G5 sozinho sem G1** → não é GO: uma empresa com dor isolada não sustenta um SaaS.

---

## 3. Matriz de decisão

| Cenário | Condição | Decisão | O que acontece |
|---------|----------|---------|----------------|
| **A** | Todos os critérios ✅ | **GO** | Autoriza Fase 0 + inicia piloto pago |
| **B** | G1–G3 ✅, G4/G5 parcial | **GO CONDICIONAL** | Fase 0 começa; piloto em 60 dias; sem promessa de preço |
| **C** | G1 ✅, G3 ❌ (dor sem número) | **REPOSICIONAR** | Revisar público e posicionamento; nova rodada de 5 entrevistas; **Fase 0 travada** |
| **D** | G1 ❌ (dor não prioritária) | **NO-GO** | Parar o 2.0; reavaliar produto ou encerrar |
| **E** | Amostra insuficiente (< 8 entrevistas) | **SEM DECISÃO** | Completar a amostra; gate permanece fechado |

> **Cenário C é o mais provável e o mais mal interpretado.** "A dor existe mas não custa dinheiro" não é
> um quase-GO: é um sinal de que o público errado foi escolhido ou o problema foi enquadrado errado.

---

## 4. O que seria necessário para virar GO

Pacote de evidência mínimo, tudo anexável:

| # | Artefato | Onde |
|---|----------|------|
| 1 | 10 fichas preenchidas, com consentimento registrado | `ENTREVISTAS_REGISTRO.md` |
| 2 | Tabela consolidada com scores por perfil | `ENTREVISTAS_REGISTRO.md` §7 |
| 3 | Mapa de dores com veredito por hipótese | `MAPA_DE_DORES.md` §4 |
| 4 | Matriz de triangulação com ≥ 3 empresas | `MAPA_DE_DORES.md` §3 |
| 5 | 5 citações a favor **e** 5 contra | `VALIDACAO_COMERCIAL_RESULTADOS.md` §3.4 |
| 6 | Tabela de disposição a pagar com preço citado | `ANALISE_DISPOSICAO_PAGAMENTO.md` §8 |
| 7 | Identificação do decisor por empresa | fichas + `VALIDACAO...` §5 |
| 8 | Registro de objeções com códigos | fichas |
| 9 | Análise de dores adjacentes | `MAPA_DE_DORES.md` §5 |

**Sem os 9, a decisão não pode ser tomada** — mesmo que a conversa "tenha parecido boa".

---

## 5. Regras de decisão pré-comprometidas

Declaradas agora, para impedir ajuste depois dos dados:

| # | Regra |
|---|-------|
| R1 | Os limiares de G1–G5 **não mudam** após a primeira entrevista |
| R2 | "Achismo do fundador" não conta como evidência, mesmo quando correto |
| R3 | Entrevista com rede pessoal conta, mas no máximo 4 de 10 (registrar viés) |
| R4 | Entrevistado que elogia e não dá número **não conta** para G3 |
| R5 | Pedido de proposta sem pergunta de preço **não conta** para G4 |
| R6 | Se menos de 8 entrevistas, a decisão é "sem decisão" (cenário E) |
| R7 | Dor induzida pela pergunta não conta para G1 (ver H11) |
| R8 | Concorrente já existente **não** invalida a oportunidade; invalida se o comprador disser "já tenho isso" em ≥ 5/10 |

---

## 6. Gatilhos de parada imediata

| # | Condição observada | Ação |
|---|--------------------|------|
| P1 | ≥ 7/10 não mencionam recebimento espontaneamente | Parar; reavaliar produto |
| P2 | ≥ 7/10 dizem "nunca tivemos problema" | Parar; reavaliar público |
| P3 | 0/10 sabem quantificar perda | Reposicionar; sem preço possível |
| P4 | 0/10 já pagam qualquer software | Modelo de receita inviável; rever canal |
| P5 | ≥ 5/10 dizem "já tenho isso no sistema" | Reposicionar a cunha (não o produto) |
| P6 | Nenhum decisor acessível em 10 tentativas | Canal inviável |

---

## 7. Consequência de cada decisão

| Decisão | Fase 0 | Fase 1 | Trilha B (CV) | Comercial |
|---------|--------|--------|---------------|-----------|
| **GO** | autoriza | planeja | mantém cronograma | fecha piloto |
| **GO CONDICIONAL** | autoriza | adia | mantém (barato, independente) | piloto em 60 dias |
| **REPOSICIONAR** | ❌ trava | ❌ trava | pode continuar (custo zero) | nova rodada |
| **NO-GO** | ❌ encerra | ❌ encerra | encerra | encerra 2.0 |

> A Trilha B (RF-DETR) é a única que **pode sobreviver** a um REPOSICIONAR: custa R$ 0 e produz um
> ativo reutilizável (dataset e modelo), útil mesmo em outro posicionamento.

---

## 8. Estado de verificação (o que é fato e o que não é)

| Afirmação | Verdadeira? |
|-----------|-------------|
| Nenhuma entrevista foi realizada | ✅ **fato** |
| Nenhum dado de cliente foi coletado | ✅ **fato** |
| Nenhuma empresa foi contatada | ✅ **fato** |
| Existe concorrente adjacente com preço público de R$ 497/mês | ✅ **fato verificado** ([fonte](https://store.omie.com.br/apps/rd-obras)) |
| O preço hipotético anterior (R$ 890/obra) é incompatível com a âncora de mercado | ⚠️ **análise**, não fato — depende de como o comprador compara |
| Existe dor recorrente no recebimento | ❌ **não verificado** |
| Existe disposição a pagar | ❌ **não verificado** |
| Existe oportunidade qualificável | ❌ **não verificado** |
| A Fase 0 pode começar | ❌ **não** — gate fechado por falta de evidência comercial |

---

## 9. Próxima decisão necessária

> ### Existe **uma** decisão agora: iniciar a coleta das 10 entrevistas.
>
> Custo: R$ 0 e ~23 h. É a ação com maior retorno e menor risco de todo o programa — e a única que pode
> **invalidar** os 31 dd de Fase 0 que estão parados esperando por ela.

### Sequência imediata (2 semanas)

| Quando | Ação | Responsável | Saída |
|--------|------|-------------|-------|
| D+0 | Construir lista de 30 contatos (fontes em `KIT_OPERACIONAL_SPRINT.md` §5) | Fundador | `pipeline.csv` |
| D+1 | Enviar 20 abordagens (WhatsApp + e-mail) | Fundador | 6–8 agendamentos |
| D+2 a D+10 | Realizar as 10 entrevistas (2/2/2/2/2) | Fundador | 10 fichas |
| Mesmo dia de cada entrevista | Preencher a ficha | Fundador | registro íntegro |
| D+11 a D+12 | Consolidar mapa de dores, WTP e resultados | Fundador | 3 documentos preenchidos |
| D+12 | Reabrir este documento e decidir | Fundador | GO / CONDICIONAL / REPOSICIONAR / NO-GO |

### O que **não** fazer enquanto o gate está fechado

- Não iniciar a Fase 0 "só a parte de infraestrutura".
- Não definir preço final.
- Não prometer prazo a ninguém.
- Não pedir proposta a cliente.
- Não alterar os critérios deste documento.

---

## 10. Registro de decisões

| Data | Decisão | Base | Quem |
|------|---------|------|------|
| 2026-11-03 | **NO-GO PROVISÓRIO** (gate fechado) | 0/10 entrevistas | Auditoria desta sprint |
| — | — | — | aguardando dados |
