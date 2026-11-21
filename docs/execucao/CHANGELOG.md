# CHANGELOG

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
O projeto **não segue versionamento semântico ainda** — não há tag nem release.

> **Princípio:** este changelog registra apenas o que **efetivamente mudou** no repositório e no
> ambiente. Intenção, plano e análise não entram aqui.

---

## [Não lançado] — 2026-11-21 — P-07: SSRF em foto_url via redirect e DNS

### Corrigido

- `laudo_pdf._carregar_imagem_url` usava `httpx.get(follow_redirects=True)` e validava só a URL inicial. Um
  redirect para `10.x`, `127.0.0.1` ou `169.254.169.254` era seguido. Um hostname público que resolvia para
  rede privada também passava, porque a validação era só literal.
- Novo `baixar_foto_segura` em `app/utils/url_seguras.py`: redirects manuais (máximo 3), validação em cada
  salto, todos os endereços DNS precisam ser públicos, conexão ao IP validado (fecha DNS rebinding),
  porta 443 e sem proxy do ambiente (`trust_env=False`).
- `_carregar_imagem_url` passa a delegar para `baixar_foto_segura`. Falhas continuam devolvendo `None`.

### Testes

- `tests/test_foto_ssrf.py` — 43 testes: redirects legítimos (mesmo host e host público diferente), redirects
  maliciosos, IP privado e IPv4 mapeado, DNS misto, rebinding, falha de DNS, URL inválida, conteúdo não
  imagem, limite de tamanho e classificação de IP.
- Teste de mutação: classificar todo IP como público fez 13 falharem; revalidar só a URL original fez 10
  falharem. Ambas as mutações foram revertidas.
- Suíte completa com PostgreSQL: **484 passam, 0 pulados**.

### Limitações

- Porta diferente de 443 agora é recusada. Nenhum uso conhecido depende disso.

## [Não lançado] — 2026-11-19 — correlação: unidades no motor pedido × NF-e

### Corrigido

- **Bug pré-existente:** `correlacionar` registrava `quantidade_consumida_base` e mantinha o saldo na unidade
  crua da NF (kg, t) e não na base comparável (m, kg). A soma `faturada` de `pedidos.py` misturava kg com
  metros para aço com bitola.

### Alterado

- `correlacao.chave_base`: sacos e toneladas agora convergem para `kg` (1 saco = 50 kg, 1 t = 1000 kg),
  pela mesma `converter_quantidade_recebida` da conferência. Antes `SACO` virava base `saco`, incomparável
  com `kg`, e a linha ia para revisão. **Efeito visível:** o nome da base em relatórios de pedido em sacos
  passa de `saco` para `kg`.
- Sem bitola, linha em sacos/toneladas só casa com item cuja categoria detectada é a mesma da linha
  (evita que cimento consuma areia em kg). Descrição sem categoria conhecida não casa nesse caminho.
- m³ continua em base própria: a conversão depende da densidade do material.

### Testes

- `tests/test_correlacao.py`: 6 novos + 1 de regressão do saldo; 2 ajustados (`SACO` agora `kg`; fixture de
  cimento com descrição de cimento). Suíte unitária: **265 passam**, 0 falham.
- `tests/integration` executada contra PostgreSQL 16 após iniciar o Docker Desktop: **176 passam**. Suíte completa: **441 passam, 0 pulados**.

## [Não lançado] — 2026-11-18 — P-10: unidades na conferência de cimento e bloco

### Corrigido

- `comparador_cimento` / `comparador_bloco` comparavam `quantidade` da NF com `quantidade_prevista`
  **sem considerar a unidade** (28 sacos × previsto 1 m³ = "2700% VERMELHO"). Agora a quantidade da NF é
  convertida para `unidade_prevista` (sacos ↔ kg ↔ m³ ↔ t; milheiro → un) e a conversão aparece na
  mensagem como evidência.
- Par de unidades sem conversão segura → **AMARELO "não comparável"**, nunca um percentual inventado.
- Mensagens `QUANTIDADE:` em caixa alta escapavam de `divergencias_from_motivos` e de
  `_atualizar_alerta_por_motivos`; padronizadas em `Quantidade:`. Divergência de cimento passa a gerar a
  tag `quantidade` e o alerta `QUANTIDADE_DIVERGENTE` (antes caía em `DIVERGENCIAS_MULTIPLAS`).
- Dimensões de bloco comparadas pelos números (`19 x 19 x 39 cm` == `19x19x39`).

### Adicionado

- `backend/app/services/quantidade_material.py` (reusa `normalizar_cimento`; sem dependência nova).
- `backend/tests/test_quantidade_material.py` — 13 testes. Suíte unitária: 242 → **255 passam**.

### Aço (mesma entrega)

- `quantidade_recebida_em_metros` aceita `TON`, `PC/PCS/PCT`, `MT/M1`, caixa baixa e `metros_por_barra` nulo (antes gerava erro genérico). Unidade desconhecida continua AMARELO. +5 testes; suíte: **260 passam**.

### Verificação de integração

- `backend/tests/integration` executada contra PostgreSQL 16 (`stellspy-pg`, porta 55432): **176 passam, 0 pulados**. Suíte completa: 436 passam, 0 pulados.

## [Não lançado] — 2026-11-03 — P-18: estabilização de dependências

### Adicionado

- **`backend/constraints.txt`** — 34 pacotes com as versões **efetivamente testadas**, incluindo
  transitivas. É o travamento da resolução, não a lista de dependências.
- **`backend/README.md`** — procedimento oficial de instalação limpa, as três camadas de dependência e
  a regra para subir versão. Preenche a lacuna de README do backend.

### Alterado

- **`backend/requirements.txt`** — dependências diretas passam a declarar limites de compatibilidade:
  - `0.x` → teto no próximo **minor** (`fastapi>=0.162.0,<0.163`, `uvicorn>=0.54.0,<0.55`,
    `httpx>=0.28.1,<0.29`, `psycopg2-binary>=2.9.13,<2.10`, `fpdf2>=2.9.0,<2.10`)
  - `>=1.x` → teto no próximo **major** (`sqlalchemy>=2.1.6,<3.0`, `pydantic>=2.14.2,<3.0`)
  - `tzdata` permanece sem teto: são dados, não API
- **`backend/requirements-dev.txt`** — `pytest>=9.2.0,<10.0`; removida a duplicata de `httpx` (já é
  dependência direta de produção).

### Verificação

| Item | Resultado |
|------|-----------|
| Ambiente recriado do zero com `-c constraints.txt` | ✅ 34/34 pacotes idênticos |
| Divergência contra o baseline aprovado | **0** (nenhum upgrade) |
| `pip check` | ✅ `No broken requirements found.` |
| Suíte completa | ✅ **82 passed** |
| Imports | ✅ 32 módulos, 0 falhas |
| OpenAPI | ✅ 8 rotas |
| `GET /health` | ✅ 200 `{"status":"ok"}` |
| Geração de PDF | ✅ 24.974 bytes, cabeçalho `%PDF-` |

### Não alterado

- Nenhuma versão foi trocada. Nenhum pacote instalado. Nenhum upgrade.
- Código de produto, migrações, banco, PWA, dashboard: intocados.

---

## [Não lançado] — 2026-11-03 — Correção P-16 (inicialização do FastAPI)

### Corrigido

- **`app.main` não importava.** `app/routers/conferencia.py` anotava a rota de laudo como
  `-> Response | RedirectResponse`; o FastAPI 0.162 rejeita a união de subclasses de `Response` como
  `response_model` e levanta `FastAPIError` no import. A API **não subia**.
  Correção: `response_model=None` no decorador da rota (uma linha + comentário). Nenhuma lógica de
  geração de PDF foi tocada; nenhum contrato HTTP mudou.
  Commit: `851da0acb1cd149d5088bf271ef9efcfda398c58`

### Adicionado

- `backend/tests/test_app_boot.py` — 13 testes de regressão que faltavam desde o início do projeto:
  import de `app.main`, import dos 32 módulos de `app/`, inicialização do `TestClient`, `GET /health`,
  registro das 8 rotas, contrato OpenAPI, `response_model is None` na rota de laudo, path param UUID,
  404 JSON para `nfe_log` inexistente (banco substituído por stub) e regressão de geração de PDF.

### Alterado — documentação

- `docs/execucao/DECISOES_TECNICAS.md` — ADR-009 (correção da anotação) e ADR-010 (política de versões)
- `docs/execucao/EVIDENCIAS.md` — E12 (antes/depois da correção)
- `docs/execucao/MATRIZ_GO_NO_GO.md` — G-02 reclassificado, G-10 criado e fechado

### Resultado dos testes

| Momento | Resultado |
|---------|-----------|
| Antes da correção (novo teste) | 5 failed, 1 passed, 6 errors |
| Depois da correção (novo teste) | **13 passed** |
| Suíte completa antes | 69 passed |
| **Suíte completa depois** | **82 passed** (69 + 13) |
| Imports dos 32 módulos | **0 falhas** |

### Não alterado

- `requirements.txt` — nenhuma versão alterada (a política está **proposta** em ADR-010, não aplicada)
- Migrações, banco, Supabase remoto, autenticação, PWA, dashboard
- Nenhum push, nenhum deploy

---

## [Não lançado] — 2026-11-03 — Sprint de Engenharia 0

### Adicionado — documentação

- `docs/execucao/STATUS_EXECUCAO.md` — painel de estado por fase
- `docs/execucao/CHANGELOG.md` — este arquivo
- `docs/execucao/DECISOES_TECNICAS.md` — 8 ADRs (ambiente, venv, tzdata, PostgreSQL, versionamento)
- `docs/execucao/RELATORIO_TESTES.md` — baseline 69/69 e mapa de lacunas
- `docs/execucao/EVIDENCIAS.md` — 8 evidências executadas com saída de comando
- `docs/execucao/PROXIMOS_PASSOS.md` — 12 ações priorizadas com gates
- `docs/execucao/MATRIZ_GO_NO_GO.md` — revisão com gates reais (§14)

### Adicionado — artefatos de ambiente (não versionáveis)

- `backend/.venv/` — ambiente isolado, Python 3.13.15, 33 pacotes *(já coberto por `backend/.gitignore`)*
- `backend/baseline_freeze.txt` — congelamento das 33 dependências do baseline
- `C:\Naturecode\dsh-acl-reports\acl-report-93b21a23c8ef40a6907a0fb0f38669b7.jsonl` — relatório do
  diagnóstico de permissões *(fora do repositório)*
- `C:\Naturecode\dsh-acl-reports\acl-backup-a6d2da9d61d543479b0c37caa17558fa.json` + `.ps1` — backup e
  script de reversão do reparo de ACL *(fora do repositório)*

### Alterado — ambiente (fora do repositório)

- Permissões de `C:\Naturecode\stellSPY`: adicionada entrada de controle total para o usuário atual,
  porque faltava o direito de alterar o proprietário (`WRITE_OWNER`). Reversível pelos arquivos de
  backup acima. **Nenhum arquivo do projeto foi modificado.**
- Instalado `tzdata` **somente dentro do `.venv`** (workaround — ver ADR-003).

### Corrigido

- **Nada no código de produto.**

### Não alterado (confirmado)

- `backend/app/**` — nenhuma linha modificada
- `backend/tests/**` — nenhuma linha modificada
- `backend/requirements.txt` — **não** alterado (falta `tzdata`; correção pendente de aprovação)
- `supabase/migrations/**` — nenhuma migração criada ou executada
- `pwa/**`, `dashboard/**` — intocados
- `docs/2.0/**`, `docs/roboflow/**`, `docs/comercial/**` — intocados nesta sprint

---

## Registro de defeitos encontrados (não corrigidos)

| ID | Defeito | Severidade | Origem | Correção |
|----|---------|-----------|--------|----------|
| D-TZ | `tzdata` ausente em `requirements.txt` — suíte não coleta | Alta | execução | P-01 |
| D-VC | Repositório sem nenhum commit | **Crítica** | execução | P-02 |
| D-FP | `fpdf2`: `ln=` e `dest=` depreciados | Média | execução | Fase 0 |
| D-ENV | Sandbox não permite escrita em subpastas do workspace | Operacional | execução | ADR-001 |

---

## Histórico anterior (anterior a esta sprint)

| Data | Entregável | Natureza |
|------|-----------|----------|
| 2026-11-03 | `ANALISE_PROJETO.md` | análise estática — 14 achados |
| 2026-11-03 | `PLANO_STELLSPY_2.0.md` + `docs/2.0/*` (6 docs) | planejamento |
| 2026-11-03 | `docs/roboflow/*` (5 docs) | estudo de viabilidade |
| 2026-11-03 | `docs/execucao/*` (6 docs) | preparação de execução |
| 2026-11-03 | `docs/comercial/*` (6 docs) | preparação comercial |

> Nenhum desses pacotes alterou código de produto. Este é o primeiro registro com **execução real**.
