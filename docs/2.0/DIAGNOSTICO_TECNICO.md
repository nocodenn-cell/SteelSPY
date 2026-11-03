# stellSPY 2.0 — Diagnóstico Técnico e Mapa de Funcionalidades

> Complementa e resume [ANALISE_PROJETO.md](../../ANALISE_PROJETO.md) (auditoria completa, 14 achados
> de severidade alta/média/baixa). Aqui o foco é **o que existe × o que o 2.0 exige**.
> Data: 2026-11-03 · Análise estática, sem execução (shell indisponível na sessão de auditoria).

## 1. Retrato do sistema hoje

| Dimensão | Situação |
|----------|----------|
| Backend | FastAPI sync, SQLAlchemy com SQL texto, 32 arquivos, ~4.200 linhas |
| Banco | Postgres/Supabase, 9 migrações, 5 tabelas de domínio |
| Frontend | PWA vanilla (sem build de JS), Tailwind compilado |
| Analytics | Streamlit lendo o mesmo banco |
| Jobs | 2 entrypoints de cron (`fila_worker_main`, `relatorio_semanal_main`) |
| Integrações | NFe.io, Evolution API (WhatsApp), SMTP, Supabase Storage |
| Testes | 65 funções, 15 arquivos — **zero** em routers/fila/persistência |
| IA | **nenhuma** — o "matching" é regra determinística (e isso é uma força) |

**O que o sistema faz bem:** recebe uma chave de NF-e, busca o XML, normaliza itens, compara com a
especificação da obra, decide VERDE/AMARELO/VERMELHO, persiste com snapshot auditável, emite PDF e
notifica. O núcleo é sólido e testado.

**O que o sistema não é:** não é multiempresa, não tem identidade de usuário, não tem evidência
fotográfica própria, não tem pedido de compra, não tem ocorrência de divergência como entidade, não
tem workflow de aprovação, não tem offline.

## 2. As quatro ausências estruturais

Tudo o que o 2.0 pede esbarra nestas quatro. Elas são pré-requisito, não "feature".

### 2.1 Identidade e multiempresa

Verificado no schema e no código:

- **não existe** tabela `construtoras`, `clientes`, `usuarios`, `obra_usuarios`;
- **não existe** `org_id`/`tenant_id` em nenhuma tabela;
- autenticação é **um segredo compartilhado por obra** (`obras.api_key`), não uma identidade.

Consequências diretas:

| Requisito do 2.0 | Por que não é atendível hoje |
|------------------|------------------------------|
| "Isolamento multiempresa" | O isolamento é por obra. Duas obras da mesma construtora não se conhecem; duas construtoras se distinguem apenas por chaves distintas. Não há entidade para aplicar política. |
| "Controle de acesso por obra e função" | Não há função (role), não há usuário. Todos com a API key têm poder total, inclusive override. |
| "Auditoria de operações" | `override_info.usuario_id` é `str | None` **livre**, sem FK, sem validação (`conferencia.py:80`). Não se sabe quem autorizou. |

> O diagrama ER de [`docs/ARQUITETURA.md`](../ARQUITETURA.md) já previa `CLIENTES ||--o{ OBRAS`.
> O SQL nunca implementou. É a maior distância entre doc e código do projeto.

### 2.2 Evidência (arquivo)

Não existe upload de imagem nem tabela de arquivos. `foto_url` é uma **URL de terceiro** que o
servidor baixa na hora de gerar o laudo (`laudo_pdf.py:133`). Não há:
`evidencias`, `documentos`, hash, EXIF, storage de imagem, retenção, nem vínculo com item.

### 2.3 Ocorrência de divergência

A divergência hoje é **um efeito colateral do status**: um item VERMELHO no `nfe_itens` e um texto em
`mensagem_item`. Não há entidade com ciclo de vida (aberta → em análise → resolvida → encerrada),
responsável, prazo, nem histórico. O `override` existe, mas muda o status sem tocar nos itens
(ver `ANALISE_PROJETO.md` A3).

### 2.4 Pedido de compra

Não existe. A comparação é NF-e × **especificação** (uma linha de projeto), não NF-e × **pedido**
(um compromisso comercial com fornecedor, preço e prazo). São coisas diferentes:

| | Especificação (existe) | Pedido de compra (falta) |
|--|------------------------|--------------------------|
| Origem | Projeto/engenharia | Compras/contrato |
| Grão | bitola, marca, qtd planejada | item, qtd pedida, preço, prazo, fornecedor |
| Pergunta | "é o material certo?" | "é o que eu pedi, pelo preço que combinei?" |

O sistema atual responde a primeira. O 2.0 precisa das duas.

## 3. Mapa de funcionalidades (12 módulos)

Legenda: ✅ implementado · 🟡 parcial · ⛔ ausente

| # | Módulo | Estado | O que já existe | Lacuna principal |
|---|--------|--------|-----------------|------------------|
| 1 | Gestão de construtoras e obras | 🟡 | `obras` com CNPJ, tolerância, modo aprendizado, e-mails, WhatsApp | Sem construtora, sem usuários, sem papéis, sem cadastro via UI |
| 2 | Recebimento inteligente | 🟡 | `POST /conferir` com idempotência e snapshot | Não há entidade **recebimento** (data, portaria, conferente, veículo); não há evidência |
| 3 | Importação/interpretação de NF-e | ✅ | `nfe_io` + adapter + validação de DV + multi-material | Só leitura por chave; sem upload de XML/PDF; sem manifesto |
| 4 | Associação com pedido de compra | ⛔ | — | Nenhuma tabela, nenhum conceito |
| 5 | Visão computacional p/ contagem | ⛔ | — | Sem upload, sem storage, sem inferência (ver `../roboflow/`) |
| 6 | OCR de marcas/especificações | ⛔ | `nfe_item_campos.py` faz regex no **texto** da NF | Não lê imagem |
| 7 | Gestão de divergências | 🟡 | Status por item, `divergencias` JSONB, PDF por item | Sem ocorrência, ciclo de vida, responsável, prazo, histórico |
| 8 | Dossiê digital de recebimentos | 🟡 | Laudo PDF + PDF de divergências + Storage | Sem dossiê consolidado, sem anexos, sem assinatura, sem índice |
| 9 | Alertas e retenção financeira | 🟡 | WhatsApp (obra + fallback), e-mail semanal SMTP | Sem solicitação de retenção, sem aprovação, sem integração financeira |
| 10 | Auditoria de certificados/laudos | ⛔ | — | Sem registro de certificado, validade, fornecedor, norma |
| 11 | Indicadores de fornecedor | ⛔ | Dashboard por obra | Sem consolidação por emitente/CNPJ ao longo do tempo |
| 12 | Operação offline e sincronização | ⛔ | Service worker mínimo (não cacheia assets) | Sem fila local, sem sync idempotente, sem resolução de conflito |

**Placar:** 1 de 12 pronto · 5 parciais · **6 ausentes**.

## 4. Débitos que **bloqueiam** o 2.0 (não são cosméticos)

Extraídos da auditoria; a ordem é a de dependência.

| # | Débito | Por que bloqueia o 2.0 |
|---|--------|------------------------|
| D1 | Sem identidade/tenant (§2.1) | Nada de RBAC, auditoria nominal ou isolamento é possível |
| D2 | Sem upload/evidência (§2.2) | Módulos 5, 6, 8 e 10 são impossíveis |
| D3 | Sem pedido de compra (§2.4) | Módulo 4 e a proposta de valor "auditoria de compra" não existem |
| D4 | Sem ocorrência (§2.3) | Módulos 7 e 9 viram texto solto |
| D5 | Override inconsistente (A3) | Dossiê e auditoria passariam a registrar mentira |
| D6 | Idempotência ignora `tipo` (A4) | Devolução e sincronização offline quebram |
| D7 | Sem normalização de unidade em cimento/bloco (A5) | Multimaterial gera falso positivo — e o 2.0 amplia categorias |
| D8 | `modo_aprendizado` default ON (A2) | O produto não bloqueia nada por padrão |

## 5. Débitos operacionais (não bloqueiam, mas cobram juros)

| # | Débito | Efeito |
|---|--------|--------|
| O1 | Nenhum teste de router/fila | Regressão silenciosa a cada mudança |
| O2 | Sem CI | Nada impede merge quebrado |
| O3 | Sem `.gitignore` na raiz | `node_modules` (1.082 arquivos) no repositório |
| O4 | `.env` não é carregado; fallback `localhost` | Config errada sem erro |
| O5 | Deps sem teto de versão | Build não reprodutível |
| O6 | `tzdata` ausente | Job de relatório quebra no Windows |
| O7 | Sem rate limit, sem métricas, sem `correlation_id` | Custo imprevisível e incidente cego |
| O8 | Laudo em bucket público | Exposição LGPD (CNPJ + valores) |
| O9 | `sinonimos` e `normalizacao_materiais` mortas | Promessa de dicionário não cumprida |
| O10 | `relatorio_semanal_main.py` duplamente espaçado | Diff ilegível |

## 6. O que **preservar** (não reescrever)

A diretriz diz "não reescrever módulos sem justificativa técnica". Estes são os que eu **não** tocaria:

| Módulo | Por quê |
|--------|---------|
| `domain/conferente.py` (núcleo de matching) | Testado, puro, sem dependência de infra. Extrair funções, não reescrever |
| `utils/chave_nfe.py` | Correto e crítico (evita custo de API) |
| `pwa_session.py` + `auth_obra.py` | Bem feito; evolui para JWT/multi-tenant em camadas, não do zero |
| `fila_retentativa.py` | Padrão correto (`SKIP LOCKED`); precisa de reaper, não de reescrita |
| `whatsapp_evolution.py` | Retry/backoff bem resolvidos; extrair o padrão para `utils/retry.py` |
| `nfe_io.py` | Adapter limpo; ganha `fonte` e `trace_id`, não reescrita |
| Migrações existentes | Idempotentes; o 2.0 **adiciona**, nunca altera destrutivamente |

**Justificativa para o que será novo:** o que falta são *entidades* (construtora, usuário,
recebimento, evidência, pedido, ocorrência) e *bordas* (upload, sync, RBAC). Nenhuma delas exige
reescrever o núcleo de conferência.

## 7. Conclusão do diagnóstico

O sistema tem **um núcleo de valor real** (conferência NF-e × especificação, auditável e testado) e
**uma fundação de produto ausente** (identidade, evidência, ocorrência, pedido). O 2.0 não é uma
reescrita: é a construção da fundação em volta do núcleo existente, sem tocá-lo.

Ordem correta: **fundação → evidência → pedido → ocorrência → visão computacional**.
Fazer visão antes da fundação é construir o telhado antes da parede.
