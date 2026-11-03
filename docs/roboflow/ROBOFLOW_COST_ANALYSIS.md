# ROBOFLOW — Análise de Custos

> **Restrição respeitada:** nenhum plano foi contratado, nenhuma conta criada, nenhum custo gerado.
> Todos os valores abaixo são **estimativas** derivadas de taxas públicas.

## 1. Economia de créditos (fonte: roboflow.com/credits, 2026-11-03)

| Recurso | O que 1 crédito compra |
|---------|------------------------|
| Armazenamento de imagens | 5.000 imagens |
| Upload | 10.000 imagens |
| Versões de dataset | 20.000 imagens |
| Auto-labeling (IA) | 1.000 imagens |
| Labeling interativo | 100 imagens |
| **Treino (GPU)** | **30 minutos** |
| *Self-hosted* (inferência) | **ilimitado — não consome crédito** |
| Google Vision OCR (bloco de Workflow) | 1.000 imagens |

### Inferência na nuvem — créditos por 1.000 imagens

| Modelo | cr/1.000 | imagens por crédito |
|--------|----------|---------------------|
| RF-DETR **Nano** | 0,125 | 8.000 |
| RF-DETR **Small–Large** | 0,1875 | 5.333 |
| RF-DETR **Seg** Nano | 0,1875 | 5.333 |
| RF-DETR **Seg** Small–Large | 0,25 | 4.000 |
| Classificação (ViT/ResNet) | 0,0625 | 16.000 |
| **PP-OCR** (detecção + reconhecimento) | 0,375 | 2.667 |
| PP-OCR (só reconhecimento) | 0,125 | 8.000 |
| DocTR / EasyOCR | 0,375 | 2.667 |

**Descontos por volume** (faixas cumulativas por workspace/mês):
250k–500k imagens → −25% · 500k–1M → −50% · 1M–2M → −60% · >5M → −80%.

## 2. Planos

| Plano | Preço | Créditos/mês | Observação |
|-------|-------|--------------|------------|
| **Free Tier** | **US$ 0** | **10** | Sem cartão; projetos privados por padrão; ~80.000 inferências ou ~5 h de GPU |
| **Core** | US$ 39/mês | 10 + pacote de créditos | Pacotes mensais; créditos não acumulam no mensal |
| Enterprise | sob consulta | negociado | Necessário para **self-host comercial** de YOLO / RF-DETR PML |

> **Ponto cego honesto:** o preço unitário do crédito adicional em pacotes não está publicado nas
> páginas consultadas **[a verificar]** com a tabela de pacotes logado. Isso não bloqueia a decisão,
> porque o caminho recomendado (self-hosted) é **não tarifado**.

## 3. Cenários de consumo na stellSPY

Premissas: 1 recebimento = 3 fotos (pilha de sacos, feixe de vergalhão, etiqueta/lacre).
22 dias úteis/mês. Cada foto = 1 inferência de detecção + 0,3 inferência de OCR (só quando há
etiqueta legível).

| Cenário | Obras | Receb./mês | Fotos/mês | Inferências | OCR | **Créditos/mês** |
|---------|-------|-----------|-----------|-------------|-----|------------------|
| **Piloto** | 1 | 44 | 132 | 132 | 40 | **0,04** |
| **Tração inicial** | 10 | 440 | 1.320 | 1.320 | 400 | **0,40** |
| **Série A** | 100 | 4.400 | 13.200 | 13.200 | 4.000 | **4,0** |
| **Escala** | 500 | 22.000 | 66.000 | 66.000 | 20.000 | **20,0** |

*(RF-DETR Small a 0,1875 cr/1.000 e PP-OCR a 0,375 cr/1.000.)*

### Leitura

- Até **~500 obras**, a inferência cloud custa **menos de 20 créditos/mês** — cabe folgado mesmo no
  Free Tier de 10 créditos até ~250 obras.
- **A inferência nunca será o gargalo de custo.** O gargalo é rotulagem, treino e engenharia.

## 4. Custo real do experimento (o que sai caro de fato)

| Item | Quantidade | Custo monetário | Custo em horas |
|------|-----------|-----------------|----------------|
| Coleta de imagens em campo | 300–800 fotos, 3–5 obras | R$ 0 (visitas próprias) | 12–20 h |
| Rotulagem (com auto-label + interativo) | ~600 imagens | R$ 0 (crédito do Free Tier) | **10–16 h** |
| Treinos / iterações | 10–20 runs × ~10 min GPU | R$ 0 (≈3–5 créditos) | 4–6 h |
| Avaliação e protocolo | 1 protocolo + 3 rodadas | R$ 0 | 8–12 h |
| Integração do adaptador | ~1 adaptador + testes | R$ 0 | 16–24 h |
| Infra de teste (self-hosted) | 1 máquina | R$ 0 (reuso) | 6–10 h |
| **Total** | | **R$ 0** de licença | **≈ 56–88 h** |

**Conclusão de custo do spike:** o experimento é **executável com custo monetário zero**. O
investimento é tempo de engenharia e visitas a obra.

## 5. Cloud vs. Self-hosted

| Dimensão | Cloud (Serverless) | Self-hosted (Inference) |
|----------|--------------------|--------------------------|
| Custo por imagem | 0,125–0,375 crédito/1.000 | **US$ 0** (não tarifado) |
| Custo fixo | US$ 0–39/mês | Hardware + energia + ops |
| Licença comercial | Incluída em qualquer plano | **Só modelos Apache-2.0** (ou Enterprise) |
| Privacidade | Imagem sai do Brasil | **Imagem nunca sai** |
| Latência | 200–800 ms típico (rede) | ~50–300 ms (LAN) ou CPU mais lenta |
| Offline | Impossível | **Possível** |
| Ops | Zero | Docker, GPU/CPU, atualização de pesos |
| Escala | Automática | Manual (horizontal) |
| Adequação ao piloto | **Ótima** | Boa, se já houver máquina |

### Quando cada um vence

- **Cloud** enquanto: < 250 obras, sem hardware na obra, time pequeno, prioridade é aprender.
- **Self-hosted** quando: (a) cliente exige que a imagem não saia do canteiro; (b) há NF-e de
  fiscalização/LGPD; (c) volume > ~250k imagens/mês; (d) requisito de offline.
- **Ponto de virada econômico:** o cloud só deixa de ser "quase grátis" acima de ~250k imagens/mês
  (≈ 1.900 obras no nosso modelo) — patamar que **não** justifica migrar por custo. A migração se
  justifica por **privacidade e offline**, não por preço.

## 6. Conversão para BRL

Como os valores são em USD, use uma variável de câmbio explícita em vez de fixar um número:

| Cenário | US$/mês | R$/mês @ 5,00 | @ 5,50 | @ 6,00 |
|---------|---------|---------------|--------|--------|
| Free Tier (até ~250 obras) | 0,00 | 0 | 0 | 0 |
| Core (sem excedente) | 39,00 | 195 | 215 | 234 |
| 500 obras / ~20 créditos — excede o Free, exige Core | 39,00 | 195 | 215 | 234 |
| 1 M imagens/mês (faixas com desconto, ~129 créditos) | ~129 cr + Core | ≥ 195 + pacote | idem | idem |

**Recomendação financeira:** orçar **US$ 39/mês (≈ R$ 215)** como teto de licença para toda a fase
de validação. É o único custo recorrente previsível e cabe em qualquer hipótese de receita.

## 7. Comparação com as alternativas gratuitas

| Alternativa | Licença | Custo | Custo oculto |
|-------------|---------|-------|--------------|
| **RF-DETR self-hosted** | Apache-2.0 | R$ 0 | Você opera a infra |
| YOLO26 self-hosted | AGPL-3.0 | Enterprise (US$ ?) | Contrato + possível open-sourcing |
| YOLO26 cloud Roboflow | AGPL-3.0 + licença do plano | R$ 215/mês | Dados saem do país |
| OpenCV clássico (Hough, contornos) | BSD | R$ 0 | Frágil com iluminação/oclusão; mas **excelente baseline de custo zero** |
| Segment Anything (SAM 2/3) | Apache-2.0 / SAM License | R$ 0–0,3125 cr/1.000 | Pesado; bom para *assistir* anotação |

O `OpenCV` merece destaque: para **vergalhão visto de frente em feixe**, um baseline geométrico
(Hough circles/elipses + calibração de escala) pode chegar perto de um modelo pequeno com **custo
zero e zero dado de treino**. Se o baseline clássico já atingir o critério de aceite, o modelo
aprendido vira otimização, não pré-requisito. Essa comparação **precisa** estar no experimento.

## 8. Resumo do custo por unidade de negócio

Considerando o cenário "tração inicial" (10 obras), com Core a US$ 39:

| Métrica | Valor |
|---------|-------|
| Custo de licença por obra/mês | US$ 3,90 (≈ R$ 21) |
| Custo por recebimento | US$ 0,089 (≈ R$ 0,49) |
| Custo por imagem inferida | US$ 0,0018 (≈ R$ 0,010) |
| Custo de armazenamento (5.000 img/crédito) | desprezível no volume do piloto |

Um único vergalhão de 10 mm com 12 m custa hoje ~R$ 40–60. **Um erro de contagem evitado paga o mês
inteiro de licença de uma obra.** O argumento comercial não deve ser "a IA é barata", e sim "o erro
que ela evita é caro".
