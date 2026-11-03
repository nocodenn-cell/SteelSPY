# stellSPY 2.0 — Matriz de Riscos e Plano de Testes

## PARTE I — MATRIZ DE RISCOS

Escala: **P**robabilidade e **I**mpacto de 1 a 5. **Score = P × I** (≥ 15 = crítico; 8–14 = alto;
≤ 7 = moderado). Revisão mensal obrigatória.

### 1. Riscos de produto e mercado

| ID | Risco | P | I | Score | Mitigação | Sinal de alerta |
|----|-------|---|---|-------|-----------|-----------------|
| R01 | Cliente compra "conferência NF-e" mas o valor percebido é só "PDF bonito" | 4 | 5 | **20** | Vender o **dossiê + rastro**, não o PDF; medir horas economizadas | Renovação com uso < 3 receb./mês |
| R02 | Obra não padroniza captura e a IA vira ruído | 4 | 4 | **16** | Modo assistido desde o dia 1; guiar captura no PWA | > 40% das fotos fora do enquadramento |
| R03 | Ciclo de venda B2B longo mata o caixa | 4 | 5 | **20** | Piloto pago de 60 dias, escopo fechado, preço baixo | Nenhum contrato em 90 dias |
| R04 | Concorrente (ERP grande ou Roboflow-like) embute a função | 3 | 4 | 12 | Foco no **fluxo do canteiro** e no vínculo com a especificação; não competir em CV puro | Anúncio de módulo equivalente por ERP tier-1 |
| R05 | Escopo 2.0 (12 módulos) maior que a capacidade | 5 | 4 | **20** | Roadmap faseado com GO/NO-GO por fase | Duas fases atrasadas em sequência |

### 2. Riscos técnicos

| ID | Risco | P | I | Score | Mitigação | Sinal de alerta |
|----|-------|---|---|-------|-----------|-----------------|
| R06 | Visão computacional não atinge acurácia de contagem | 4 | 4 | **16** | Baseline OpenCV antes do modelo; critérios pré-registrados; modo assistido | MAPE > 8% após 3 iterações |
| R07 | `conferente` acumula responsabilidades e fica intestável | 4 | 3 | 12 | Extrair funções puras; proibir nova regra de negócio nele sem teste | Arquivo > 800 linhas |
| R08 | Sem testes de borda, regressão silenciosa | 5 | 4 | **20** | F0 instala TestClient + Postgres em container | Bug em produção em rota sem teste |
| R09 | Fila travada em `processando` | 3 | 4 | 12 | Reaper + métrica de fila parada | Job > 2 h sem progresso |
| R10 | Deploy manual gera divergência de ambiente | 4 | 3 | 12 | CI obrigatório; migração versionada; healthcheck com DB | "Funciona local, quebra em prod" |
| R11 | Custo de infra/API imprevisível | 2 | 3 | 6 | Self-hosted quando possível; alerta de consumo; rate limit | Fatura 2× o previsto |

### 3. Riscos de segurança e privacidade

| ID | Risco | P | I | Score | Mitigação | Sinal de alerta |
|----|-------|---|---|-------|-----------|-----------------|
| R12 | Vazamento entre tenants (dado de uma construtora visível a outra) | 3 | 5 | **15** | `tenant_id` + RLS + role de app + teste automatizado de isolamento | Teste falhando em CI |
| R13 | Imagem de canteiro (com pessoas) armazenada sem base legal | 4 | 5 | **20** | EXIF strip, política de retenção, cláusula contratual, blur | Foto com rosto em dossiê enviado |
| R14 | Laudo/dossiê em bucket público | 5 | 4 | **20** | Bucket privado + URL assinada (hoje está público) | URL aberta em navegador anônimo |
| R15 | SSRF via `foto_url` (redirect) | 4 | 4 | **16** | `follow_redirects=False` + revalidação (F0) | Requisição a IP privado no log |
| R16 | API key em texto plano no banco | 5 | 3 | **15** | Hash + exibição única + rotação | Dump com chave legível |
| R17 | Uso indevido de imagem de cliente para treino de modelo | 3 | 5 | **15** | Setting desligado; só imagens próprias; contrato | Dataset com foto de obra sem termo |

### 4. Riscos legais e de licenciamento

| ID | Risco | P | I | Score | Mitigação | Sinal de alerta |
|----|-------|---|---|-------|-----------|-----------------|
| R18 | Contaminação AGPL por uso de YOLO self-hosted | 3 | 5 | **15** | Padronizar RF-DETR Apache-2.0 (ver `../roboflow/`) | `pip install ultralytics` em `requirements.txt` |
| R19 | Dataset comunitário com licença BY-NC usado comercialmente | 3 | 4 | 12 | Checklist de licença por dataset antes do uso | Dataset sem campo de licença registrado |
| R20 | Assinatura/dossiê interpretado como laudo técnico oficial | 3 | 4 | 12 | Texto explícito "não substitui responsável técnico" (já existe no PDF) | Cliente usando dossiê em disputa judicial |
| R21 | Retenção financeira interpretada como decisão da plataforma | 2 | 5 | 10 | Plataforma **solicita**, nunca aprova; UI deixa claro quem decide | Cliente pedindo "bloqueio automático" |

### 5. Riscos operacionais

| ID | Risco | P | I | Score | Mitigação | Sinal de alerta |
|----|-------|---|---|-------|-----------|-----------------|
| R22 | Perda de dado offline na reconexão | 3 | 5 | **15** | `id_cliente` desde a Fase 1; teste de caos | Reclamação de recebimento "sumido" |
| R23 | Fiscal abandona o app no primeiro erro | 4 | 4 | **16** | Degradação graciosa; nunca bloquear o recebimento | Uso cai após erro |
| R24 | Dependência de uma única pessoa | 5 | 5 | **25** | Documentação executável (este pacote); CI; ROADMAP | Nenhum commit em 2 semanas |

### 6. Riscos de fornecedor (Roboflow)

| ID | Risco | P | I | Score | Mitigação |
|----|-------|---|---|-------|-----------|
| R25 | Mudança de preço/limite do free tier | 4 | 2 | 8 | Adaptador isola; self-hosted é plano B |
| R26 | Deprecação de modelo/algoritmo | 3 | 3 | 9 | `modelo_versao` gravada; reprocessamento possível |
| R27 | Indisponibilidade da API cloud | 3 | 3 | 9 | Fila + fallback para self-hosted |
| R28 | Mudança nos termos de licenciamento | 2 | 4 | 8 | Revisão trimestral da página de licenças |

### 7. Top 5 — onde colocar energia agora

| Rank | Risco | Por quê |
|------|-------|---------|
| 1 | **R24** dependência de uma pessoa | Encerra o projeto inteiro; score mais alto |
| 2 | **R01/R03** valor percebido e ciclo de venda | Nenhum código salva produto sem comprador |
| 3 | **R13/R14** privacidade e exposição | Risco jurídico irreversível |
| 4 | **R08** ausência de testes de borda | Multiplica todos os outros riscos |
| 5 | **R05** escopo maior que capacidade | Garante atraso em cadeia |

---

## PARTE II — PLANO DE TESTES

### 8. Situação atual (ponto de partida)

| Camada | Hoje | Meta F1 |
|--------|------|---------|
| Unitário de domínio | ✅ 65 testes | manter ≥ 80% de cobertura em `domain/` |
| Router/HTTP | ⛔ **zero** | ≥ 1 teste por rota e por código de erro |
| Integração com banco | ⛔ **zero** | Postgres em container, migrações aplicadas |
| Contrato de adaptador | ⛔ zero | mock determinístico por engine |
| Isolamento multi-tenant | ⛔ zero | **obrigatório antes do 2º cliente** |
| Idempotência | ⛔ zero | upload, conferência, sync |
| E2E PWA | ⛔ zero | fluxo captura → resultado |
| Avaliação de modelo (CV) | ⛔ zero | protocolo com métricas de contagem |
| Segurança | parcial (só SSRF unitário) | + isolamento, authz, upload malicioso |

### 9. Pirâmide alvo

```
              ┌──────────────────────┐
              │  E2E (poucos)        │  5%   fluxo canteiro em navegador
              ├──────────────────────┤
              │  Integração (médio)  │ 25%   router + Postgres + fila
              ├──────────────────────┤
              │  Contrato (médio)    │ 10%   adapters, engines, ERP
              ├──────────────────────┤
              │  Unitário (muitos)   │ 60%   domínio puro, regras
              └──────────────────────┘
                    + avaliação de modelo (fora da pirâmide)
```

### 10. Testes por módulo

| Módulo | O que testar | Como | Critério |
|--------|--------------|------|----------|
| `conferente` | bitola, marca, quantidade, multimaterial, modo aprendizado, agregação | pytest puro, tabela de casos | 100% dos ramos de status |
| `chave_nfe` | DV válido/inválido, tamanho, caracteres | pytest puro | caso real de NF-e conhecida |
| `auth_obra` / sessão | cookie válido, expirado, assinatura errada, obra trocada | pytest + monkeypatch | nenhum falso positivo |
| `POST /conferir` | 200 idempotente, 400 chave, 401/403 authz, 409 pendente, 422 devolução | `TestClient` + DB | todos os códigos cobertos |
| `POST /override` | só de VERMELHO, histórico, consistência com itens | `TestClient` + DB | estado coerente após override |
| PDFs | geração sem exceção, conteúdo obrigatório, fonte Unicode | snapshot + inspeção de bytes | PDF abre e contém CNPJ/chave |
| Fila | claim concorrente, reaper, falha transitória vs. definitiva | 2 threads + DB | nenhuma linha órfã em `processando` |
| Upload (F1) | mime, tamanho, idempotência por hash, EXIF strip | `TestClient` | reenvio não duplica |
| Isolamento (F1) | tenant A não lê B (query e RLS) | teste dedicado, 2 tenants | 0 vazamento |
| Sync (F5) | lote, duplicata, conflito, relógio errado | teste + DB | zero duplicata |
| Motor de visão | payload inválido, timeout, 429, resposta vazia | `httpx.MockTransport` | degrada sem quebrar |
| ERP adapter | idempotência de escrita, falha, timeout | mock | nunca duplica pedido |

### 11. Dados de teste

| Tipo | Estratégia |
|------|-----------|
| NF-e | XMLs reais **anonimizados** em `backend/tests/fixtures/nfe/` (hoje só há mock em `nfe_io`) |
| Banco | Postgres efêmero por sessão; migrações aplicadas do zero (testa as migrações também) |
| Imagem | fixtures pequenas (JPEG 100 KB) + 1 caso de "arquivo grande" e 1 de mime falso |
| Modelo | `engine_mock` devolvendo detecções fixas; nenhum teste depende de rede |
| Tempo | `freezegun` ou injeção de `hoje` (o comparador de cimento já aceita `hoje=`) |

### 12. Testes de segurança (obrigatórios)

| # | Teste | Esperado |
|---|-------|----------|
| S1 | URL `foto_url` com redirect para IP privado | requisição bloqueada |
| S2 | Upload com `Content-Type` mentiroso (`.exe` como `image/jpeg`) | rejeitado |
| S3 | Upload > limite | 413 sem gravar arquivo |
| S4 | Token de sessão de obra A acessando obra B | 403 |
| S5 | Usuário `fiscal` tentando override | 403 |
| S6 | Usuário `auditor` tentando escrever | 403 |
| S7 | Query de tenant A retornando linha de B (RLS) | 0 linhas |
| S8 | API key revogada | 401 |
| S9 | `id_cliente` duplicado de outro dispositivo | duplicata absorvida, não 500 |
| S10 | Path traversal no `storage_key` | impossível por construção (UUID) |

### 13. Protocolo de avaliação de visão computacional (fora da pirâmide)

Detalhado em [`../roboflow/ROBOFLOW_MODEL_EVALUATION.md`](../roboflow/ROBOFLOW_MODEL_EVALUATION.md).
Resumo dos invariantes de teste:

1. Split **por obra**, nunca por imagem.
2. Métrica de decisão = **contagem** (MAE, MAPE, erro-zero), não mAP.
3. Anotador que valida **não vê** a predição.
4. Critérios de aceite **pré-registrados** antes de ver os números.
5. Toda inferência registrada com versão de modelo — para poder reproduzir.

### 14. Gates de CI

| Gate | Bloqueia merge? |
|------|-----------------|
| `pytest` (unitário + integração) | **Sim** |
| Cobertura `domain/` ≥ 80% | Sim |
| Migrações aplicam do zero em banco vazio | **Sim** |
| Build do CSS do PWA sem erro | Sim |
| Lint (ruff) | Sim (a partir de F1) |
| Teste de isolamento multi-tenant | **Sim** (a partir de F1) |
| Verificação de que nenhuma dependência AGPL entrou | **Sim** |

> O último gate é barato e evita o risco R18: um script que faz grep em `requirements.txt` e no lock
> por `ultralytics`, `yolov5`, `yolov8`.

### 15. Testes manuais de campo (não automatizáveis)

| # | Roteiro | Frequência |
|---|---------|-----------|
| M1 | Recebimento completo no sol, tela suja, luvas | cada release |
| M2 | Foto com 0% de sinal (galpão escuro) e recuperação | cada release |
| M3 | Celular descarrega no meio do recebimento | F5 |
| M4 | Sincronização após 8 h offline | F5 |
| M5 | Impressão do dossiê em impressora de obra | F2 |
| M6 | Fiscal leigo, sem treinamento, 3 recebimentos | cada fase |

### 16. Critério de qualidade para avançar de fase

Uma fase só é declarada concluída se:

- [ ] todos os gates de CI verdes;
- [ ] nenhum risco de score ≥ 15 em aberto **naquela fase**;
- [ ] roteiro manual M6 executado com ≥ 2 fiscais reais;
- [ ] nenhuma rota antiga quebrada (teste de compatibilidade);
- [ ] documentação da fase atualizada (não deixar dívida de doc — é o O10 do diagnóstico).
