# Sprint 5 — Visão aplicada ao recebimento (preparação)

> Iniciada em 2026-11-03, **sem integrar modelo não validado**. Nada desta pasta
> toca rota, banco, PWA ou Storage. Orçamento adicional: **R$ 0**.

## 1. Objetivo

Contar pontas de vergalhão visíveis na fotografia do recebimento, comparar com o
pedido de compra e a NF-e e entregar a proposta ao humano com marcação e
confiança — nunca substituindo a decisão humana sem validação medida.

A VC-01 provou o pipeline e a recusa, mas deu **NO-GO** para contagem automática:
o dataset usado não era do cenário real e nenhum detector chegou perto do
critério de aceite. A Sprint 5 começa por **dados**, não por modelo.

## 2. O que já está pronto (contratos executáveis)

| Ferramenta | Comando | O que garante |
|------------|---------|---------------|
| Validador de dataset | `python -m exp_vc02.cli validar --manifesto … --rotulos …` | hash, dimensões, caminho relativo, anonimização, COCO íntegro e **zero vazamento entre divisões** |
| Avaliador de detecções | `python -m exp_vc02.cli avaliar --verdade … --predicoes …` | AP/mAP@[.5:.95], precisão/recall/F1 e **portão de validação humana** |

Ambos são agnósticos de modelo: o mesmo comando mede RF-DETR, YOLO ou qualquer
detector futuro. Testes em `backend/tests/test_vc02_dataset.py` e
`backend/tests/test_vc02_metricas.py`.

## 3. Dataset (pré-requisito bloqueante)

Coleta mínima por obra: fotos do recebimento real em ângulos, distâncias e luzes
variadas, com a **ponta visível**; registrar também pilhas parcialmente ocultas,
porque é nelas que o modelo erra.

Regras de governança:

- divisão **por obra**, nunca por imagem (fotos da mesma obra compartilham fundo);
- `obra_ref` anonimizada, sem CNPJ, endereço ou nome de pessoa;
- manifesto com SHA-256 e dimensões; imagem repetida entre divisões é erro;
- rótulos COCO por divisão (`treino.json`, `validacao.json`, `teste.json`);
- licença e consentimento registrados no manifesto.

Meta inicial: ≥ 60 obras, ≥ 600 fotos rotuladas, teste ≥ 30% das obras.
Sem isso, qualquer métrica mede o dataset, não o modelo.

## 4. Protocolo de avaliação

1. Calibrar limiar **somente** em `validacao`; `teste` é intocável até o fim.
2. Rodar `avaliar` no teste com os limiares acordados (sugestão inicial:
   mAP@0.5 ≥ 0,85 · precisão ≥ 0,95 · recall ≥ 0,90).
3. Revisão humana de ≥ 100 detecções no teste, registrada em
   `validacao_humana` (`aprovado`, `amostras`, responsável, data).
4. Só com os três itens verdes o modelo pode ser integrado — e ainda assim em
   modo proposta, com recusa explícita quando a confiança for baixa.
5. Comparação com pedido/NF-e continua sendo regra de negócio determinística;
   a visão não altera status de divergência sozinha.

## 5. Sequência planejada

| Etapa | Entrega | Depende de |
|-------|---------|------------|
| S5.1 | coleta e anonimização do dataset real | acesso às obras |
| S5.2 | anotação COCO + validação com `exp_vc02.dataset` | S5.1 |
| S5.3 | fine-tune RF-DETR e predições em COCO | dataset + GPU |
| S5.4 | avaliação com `exp_vc02.metricas` e revisão humana | S5.3 |
| S5.5 | proposta no PWA (marcações + confiança + recusa) | S5.4 aprovado |
| S5.6 | dossiê com contagem proposta × conferida e trilha | S5.5 |

## 6. Bloqueios atuais

| Bloqueio | Efeito |
|----------|--------|
| Sem fotografias do recebimento real | S5.1 não começa |
| Sem GPU nesta máquina (RTX 4070 ausente) | S5.3 local inviável; avaliar ambiente gratuito com aprovação |
| Orçamento R$ 0 | sem anotação paga e sem treino em nuvem paga |

## 7. Não objetivos desta preparação

- não importar modelo no `backend/app`;
- não criar rota, migração, bucket ou flag de produção;
- não declarar contagem automática homologada;
- não usar número simulado em relatório.
