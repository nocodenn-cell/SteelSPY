# Análise técnica — stellSPY

> Auditoria estática do repositório em `C:\Naturecode\stellSPY` (branch `main`).
> Data: 2026-11-03 · Escopo: estrutura, arquitetura, código, testes, segurança, documentação.

---

## 1. Sumário executivo

O projeto é um **monólito modular FastAPI** que audita o recebimento de material de construção
(NF-e × especificação da obra), classifica cada item em **VERDE / AMARELO / VERMELHO** e entrega
evidência em PDF, alerta por WhatsApp e relatório CSV semanal. Há também um PWA vanilla e um
dashboard Streamlit sobre o mesmo Postgres.

**Estado geral:** código maduro para um MVP, bem organizado em camadas e com boa separação de
responsabilidades. A base de testes unitários (65 funções) cobre bem o *domínio*, mas **não cobre
as bordas** (routers, fila, persistência) — justamente onde estão os defeitos mais graves.

**Números:** 9 migrações SQL · 51 arquivos Python (~4.200 linhas em `app/`) · 15 arquivos de teste ·
1.082 arquivos em `pwa/node_modules` (presentes no diretório e não cobertos por nenhum `.gitignore`).

**Os 6 riscos que eu corrigiria antes do piloto pago:**

| # | Risco | Impacto |
|---|-------|---------|
| A1 | SSRF real via `foto_url` (redirects seguidos) | Servidor usado como proxy para rede interna |
| A2 | `modo_aprendizado` **ligado por padrão** | O produto nunca bloqueia nada por default |
| A3 | Override deixa `nfe_logs` e `nfe_itens` contraditórios | Laudo/dashboard mostram dados inconsistentes |
| A4 | Idempotência ignora `tipo` | Devolução da mesma chave nunca é registrada |
| A5 | Cimento/bloco comparam quantidade **sem normalizar unidade** | Falso VERMELHO (sacos × m³) |
| A6 | `.env` nunca é carregado; fallback silencioso para `localhost` | Config errada em produção sem erro |

---

## 2. Inventário da pasta

```
stellSPY/
├── .cursor/context.md            # contexto resumido para agentes/IDE
├── .git/                         # branch main
├── backend/
│   ├── .env.example              # 86 linhas — referência de configuração
│   ├── .gitignore                # só cobre backend/
│   ├── pytest.ini                # pythonpath=. · testpaths=tests
│   ├── requirements.txt          # 7 deps, todas com ">=" sem teto
│   ├── requirements-dev.txt      # + pytest
│   ├── assets/fonts/DejaVuSans.ttf
│   ├── app/
│   │   ├── main.py               # FastAPI + CORS + /health
│   │   ├── db.py                 # engine SQLAlchemy sync
│   │   ├── auth_obra.py          # X-API-KEY ou cookie de sessão
│   │   ├── pwa_session.py        # cookie HMAC-SHA256 (sem libs externas)
│   │   ├── fila_worker_main.py   # entrypoint do worker (cron)
│   │   ├── relatorio_semanal_main.py  # entrypoint do job de CSV/e-mail
│   │   ├── routers/              # auth_pwa.py, conferencia.py
│   │   ├── domain/conferente.py  # 670 linhas — núcleo de matching
│   │   ├── services/             # 16 módulos (NF-e, PDF, WhatsApp, SMTP, fila…)
│   │   └── utils/                # chave_nfe.py, url_seguras.py
│   └── tests/                    # 15 arquivos, 65 testes
├── dashboard/                    # app.py, queries.py, metros.py (Streamlit)
├── docs/                         # ARQUITETURA, CHECKLIST_GOLIVE, DASHBOARD_ECONOMIA
├── pwa/                          # index.html, sw.js, manifest.json, js/{config,api,main,render}
└── supabase/migrations/          # 9 arquivos SQL versionados
```

### O que **não** existe (e faria diferença)

| Ausente | Consequência |
|---------|--------------|
| `README.md` na raiz | Onboarding depende de `.cursor/context.md` |
| `.gitignore` na raiz | `pwa/node_modules/` (1.082 arquivos) e `dashboard/__pycache__/` não são ignorados |
| CI (`.github/workflows`) | Nenhuma verificação automática de testes/lint |
| `LICENSE`, `Dockerfile`, `docker-compose` | Deploy manual em Render/Fly |
| Lock de dependências no backend | Build não reprodutível (só o PWA tem `package-lock.json`) |
| Pre-commit / ruff / black / mypy | Estilo mantido só por disciplina |

---

## 3. Arquitetura real (o que o código faz)

```mermaid
flowchart LR
    subgraph Cliente
        PWA["PWA vanilla<br/>index.html + js/"]
    end

    subgraph API["FastAPI (backend/app)"]
        AUTH["auth_pwa · auth_obra"]
        CONF["POST /conferir"]
        OVER["POST /override/{id}"]
        PDF["GET /laudo.pdf<br/>GET /divergencias.pdf"]
    end

    subgraph Dominio
        CONFENTE["domain/conferente.py<br/>matching + status agregado"]
        MATCH["material_categoria · nfe_item_campos<br/>comparador_cimento · comparador_bloco"]
    end

    subgraph Servicos
        NFE["nfe_io (httpx)"]
        PERS["conferencia_persist · nfe_persistencia"]
        DPdf["laudo_pdf · divergencias_pdf"]
        WA["whatsapp_evolution"]
        FILA["fila_retentativa"]
    end

    DB[("Postgres / Supabase")]
    STOR[("Supabase Storage")]
    EXT["NFe.io / Evolution / SMTP"]

    PWA --> AUTH --> DB
    PWA --> CONF
    CONF --> NFE --> EXT
    CONF --> CONFENTE --> MATCH
    CONF --> PERS --> DB
    CONF --> FILA --> DB
    CONF -.BackgroundTasks.-> WA
    PDF --> DPdf --> STOR
    FILA --> NFE
    JOB["relatorio_semanal_main"] --> DB
    JOB --> EXT
    DASH["dashboard Streamlit"] --> DB
```

**Decisão arquitetural mais importante:** o sistema é **stateless** na API; toda a verdade está no
Postgres (`nfe_logs.xml_data` guarda o *snapshot* da conferência). Isso permite reconstruir a
resposta de forma idempotente sem reprocessar — ver
[conferencia.py:104](backend/app/routers/conferencia.py#L104). É uma boa escolha, mas cria a
ambiguidade apontada em **A3**.

### Fluxo de status (regra de negócio central)

1. Cada item é classificado em VERDE/AMARELO/VERMELHO
   ([conferente.py:345](backend/app/domain/conferente.py#L345) para aço,
   [comparador_cimento.py:46](backend/app/services/comparador_cimento.py#L46) e
   [comparador_bloco.py:23](backend/app/services/comparador_bloco.py#L23) para os demais).
2. O status da NF é o **pior item** (`_pior` /
   [conferente.py:564](backend/app/domain/conferente.py#L564)).
3. Se `modo_aprendizado` estiver ligado, **todo VERMELHO é rebaixado para AMARELO** antes de sair
   ([conferente.py:411](backend/app/domain/conferente.py#L411)).
4. Override manual: VERMELHO → VERDE com justificativa auditável
   ([conferencia.py:450](backend/app/routers/conferencia.py#L450)).

---

## 4. Pontos fortes (o que preservar)

- **SQL 100% parametrizado** (`text()` + dicionário de binds). Não encontrei uma única
  interpolação de string em query — inclusive nas rotinas da fila.
- **Validação da chave NF-e (módulo 11) antes de qualquer API paga**
  ([chave_nfe.py:28](backend/app/utils/chave_nfe.py#L28)) — decisão que economiza dinheiro real.
- **Fila com `FOR UPDATE SKIP LOCKED`**
  ([fila_retentativa.py:62](backend/app/services/fila_retentativa.py#L62)): o padrão correto para
  concorrência, raramente visto em MVPs.
- **Sessão PWA sem dependências externas**: cookie HttpOnly assinado com HMAC-SHA256 e
  `hmac.compare_digest` ([pwa_session.py:62](backend/app/pwa_session.py#L62),
  [auth_obra.py:42](backend/app/auth_obra.py#L42)). A API key nunca fica no `localStorage`.
- **Consistência de versões nas migrações**: `ADD COLUMN IF NOT EXISTS`, `ON CONFLICT DO NOTHING`,
  `DO $$` para checar colunas — as 9 migrações podem ser reaplicadas sem quebrar.
- **Domínio puro e testável**: `conferente.py` não importa FastAPI nem toca no banco, o que permitiu
  testar o núcleo de matching com dezenas de casos sem nenhuma infraestrutura.
- **WhatsApp com retry exponencial + jitter e classificação de erro transitório vs. definitivo**
  ([whatsapp_evolution.py:153](backend/app/services/whatsapp_evolution.py#L153)) — acima da média.
- **Tipagem moderna** (`from __future__ import annotations`, `str | None`, dataclasses, `Enum`).

---

## 5. Achados — severidade ALTA

### A1 · SSRF real via `foto_url` (redirects seguidos)

[url_seguras.py:33](backend/app/utils/url_seguras.py#L33) valida a URL **inicial** (só HTTPS, host
público). Mas [laudo_pdf.py:139](backend/app/services/laudo_pdf.py#L139) faz
`httpx.get(url, follow_redirects=True)`:

```
foto_url = https://atacante.example/r                      # host público, HTTPS, passa na validação
  → 302 Location: http://169.254.169.254/latest/meta-data  # httpx segue, sem revalidar
```

O `follow_redirects=True` anula tanto a exigência de HTTPS quanto o bloqueio de IP privado/link-local.
Qualquer portador de uma API key de obra consegue sondar a rede interna e o metadata endpoint da
cloud. **Correção:** `follow_redirects=False` (ou hook de revalidação a cada hop), checar
`r.url` no final, e limite de bytes na leitura do corpo.

### A2 · `modo_aprendizado` ligado por padrão anula o bloqueio

[core_schema.sql:15](supabase/migrations/20260410120000_core_schema.sql#L15) define
`modo_aprendizado BOOLEAN NOT NULL DEFAULT TRUE`, e o dataclass repete o default em
[conferente.py:327](backend/app/domain/conferente.py#L327). Resultado por padrão:

- todo item VERMELHO vira AMARELO;
- o PWA mostra "ATENÇÃO", nunca "BLOQUEADO";
- `can_override` fica falso (só existe para VERMELHO) — o override é inalcançável.

O produto vendido como "bloqueio de entrada" entrega, out-of-the-box, um sistema que nunca bloqueia.
**Sugestão:** default `FALSE` para obras novas, ou um `ONBOARDING_MODE` explícito por obra com prazo,
e expor o estado "modo aprendizado" no PDF (já existe a faixa — [laudo_pdf.py:156](backend/app/services/laudo_pdf.py#L156)).

### A3 · Override deixa o banco internamente contraditório

[conferencia.py:496](backend/app/routers/conferencia.py#L496) atualiza **apenas** `nfe_logs`:

```sql
UPDATE nfe_logs SET status_conferencia = 'VERDE', override_info = …, laudo_pdf_url = NULL …
```

Ficam desatualizados:

| Campo | Depois do override | Efeito |
|-------|--------------------|--------|
| `nfe_itens.status_item` | continua `VERMELHO` | Dashboard conta itens vermelhos ([queries.py:53](dashboard/queries.py#L53)) enquanto a NF está verde |
| `nfe_logs.itens_resumo` | continua com vermelhos | Relatório CSV semanal contradiz o status ([relatorio_semanal.py:182](backend/app/services/relatorio_semanal.py#L182)) |
| `xml_data.status` / `.alerta` | intactos | Replay idempotente devolve `status: VERDE` com `alerta: MATERIAL_NAO_SOLICITADO` ([conferencia.py:117](backend/app/routers/conferencia.py#L117)) |
| `mensagem_fiscal` | regenerada com VERDE | Diz "Todos os itens estão dentro da especificação" |

Segundo efeito: reconferir a mesma chave (XML ainda disponível) **recalcula** para VERMELHO e
sobrescreve o VERDE do override, mantendo o `override_info` — o rastro de auditoria passa a
descrever uma decisão que já não vale. **Correção:** gravar o status efetivo em coluna própria
(`status_manual`/`status_efetivo`), propagar para `nfe_itens` (ou marcar `override_aplicado`), e
bloquear recálculo quando houver override vigente.

### A4 · Idempotência ignora `tipo`: devolução nunca é registrada

[conferencia.py:201](backend/app/routers/conferencia.py#L201):

```python
if ex and ex["status_conferencia"] != PENDENTE and ex["xml_data"] is not None:
    return _resposta_conferencia_idempotente(...)   # devolve a conferência da ENTRADA
```

A chave de acesso da NF de devolução pode ser a mesma da NF original (é o caso comum: devolve-se
contra a nota). Como a unique key é `(obra_id, chave_acesso)` e o `tipo` não entra na comparação, o
POST com `tipo="devolucao"` **nunca executa** — retorna o resultado da entrada, com `status` já
consolidado. O fluxo de devolução (migração
[20260410210000](supabase/migrations/20260410210000_nfe_itens_resumo_devolucao.sql#L23) e
`nf_original_id`) está implementado no schema, no upsert e na validação, mas é inalcançável na
prática. **Correção:** incluir `tipo` na chave de idempotência (`UNIQUE (obra_id, chave_acesso, tipo)`)
ou, no mínimo, tratar `tipo` diferente como nova conferência.

### A5 · Cimento e bloco comparam quantidade **crua**, sem normalizar unidade

[comparador_cimento.py:104](backend/app/services/comparador_cimento.py#L104) e
[comparador_bloco.py:66](backend/app/services/comparador_bloco.py#L66) usam
`float(item_recebido["quantidade"])` contra `quantidade_prevista`, **ignorando
`unidade_prevista`**. Se a especificação diz `1 m³` e a NF traz `28 sacos`:

```
delta = |28 − 1| / 1 = 2700%  →  VERMELHO "QUANTIDADE: divergência 2700%"
```

O módulo que resolveria isso existe e está correto —
[normalizacao_cimento.py](backend/app/services/normalizacao_cimento.py#L16) — mas **só é chamado por
testes** (grep: nenhuma referência em `app/`). A tabela `normalizacao_materiais` também foi criada e
semeada sem consumidor. O modo `AMARELO` de quantidade ainda é mascarado pelo `modo_aprendizado`
(A2), mas o falso positivo persiste na mensagem e no PDF. **Correção:** normalizar para
`unidade_prevista` antes de comparar e alimentar os fatores pela tabela em vez de constantes.

### A6 · `.env` nunca é carregado e o banco cai silenciosamente em `localhost`

[db.py:12](backend/app/db.py#L12):

```python
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")
```

Não há `python-dotenv` em nenhum lugar do backend (grep: 0 ocorrências fora de `node_modules`).
Ainda assim, [.env.example:1](backend/.env.example#L1) instrui "Copie para `.env`" e
[CHECKLIST_GOLIVE_SUPABASE.md:66](docs/CHECKLIST_GOLIVE_SUPABASE.md#L66) diz "com `.env` carregado".
O comando documentado `uvicorn app.main:app --reload` **não** lê `.env`. Consequências: (a) o
desenvolvedor acha que configura e não configura; (b) em produção, esquecer `DATABASE_URL` não gera
erro — conecta em `localhost` e falha com stack trace obscuro. **Correção:** `load_dotenv()` no topo
de `db.py` (ou `--env-file` na doc) + falhar rápido quando a variável não existir e o ambiente for
produção.

---

## 6. Achados — severidade MÉDIA

### M1 · Fila pode ficar presa em `processando` para sempre

[fila_retentativa.py:97](backend/app/services/fila_retentativa.py#L97) marca as linhas como
`processando` e faz commit. O `try/except` só envolve `ao_sucesso`; `buscar_xml(chave)` está **fora**
([linha 113](backend/app/services/fila_retentativa.py#L113)). Se ele levantar — e ele levanta:
`r.json()` em [nfe_io.py:222](backend/app/services/nfe_io.py#L222) não trata `JSONDecodeError`, só
`RequestError` — a linha fica `processando` e **nenhum mecanismo a recupera**. Não há reaper, nem
coluna de `claimed_at`, nem alerta de fila parada. **Correção:** `try/finally` por linha, timeout de
claim (`WHERE updated_at < NOW() - INTERVAL '10 min'`) e métrica de linhas em `processando`.

### M2 · Tags de divergência perdidas para cimento/bloco

[conferente.py:272](backend/app/domain/conferente.py#L272) classifica por prefixo **case-sensitive**:

```python
elif m.startswith("Quantidade:"):   # ❌ comparador_cimento emite "QUANTIDADE: …"
```

Os comparadores de cimento e bloco emitem `QUANTIDADE:` em maiúsculas
([comparador_cimento.py:124](backend/app/services/comparador_cimento.py#L124),
[comparador_bloco.py:86](backend/app/services/comparador_bloco.py#L86)). Efeito duplo:

- `nfe_itens.divergencias` fica `[]` numa divergência de quantidade → o PDF por item
  ([divergencias_pdf.py:89](backend/app/services/divergencias_pdf.py#L89)) mostra "—";
- `_motivos_tem_quantidade_critica` ([conferente.py:232](backend/app/domain/conferente.py#L232))
  também falha, então o alerta agregado vira `DIVERGENCIAS_MULTIPLAS` em vez de
  `QUANTIDADE_DIVERGENTE` ([conferente.py:636](backend/app/domain/conferente.py#L636)).

**Correção:** normalizar `m.lower()` no início de cada comparação (ou melhor: fazer os comparadores
devolverem as tags estruturadas em vez de acoplar semântica ao texto da mensagem).

### M3 · O "dicionário de sinônimos" é promessa de marketing, não código

[docs/ARQUITETURA.md:171](docs/ARQUITETURA.md#L171) enumera `DICIONARIO_IA` como ativo do negócio e
"diferencial técnico defensável". A tabela `sinonimos` foi criada
([core_schema.sql:51](supabase/migrations/20260410120000_core_schema.sql#L51)) e **nunca é lida nem
escrita** (grep: 2 ocorrências, ambas DDL). O matching de descrição hoje é heurística fixa em
[material_categoria.py](backend/app/services/material_categoria.py#L10) e
[nfe_item_campos.py](backend/app/services/nfe_item_campos.py#L13). Isso é aceitável no MVP, desde que
a documentação não venda o que não existe — o risco é comercial, não técnico.

### M4 · Rate limiting e observabilidade prometidos, ausentes

[ARQUITETURA.md:231](docs/ARQUITETURA.md#L231) e a §8 (observabilidade) descrevem rate limit por
obra/IP, `correlation_id`, métricas de falso positivo e alertas de fila. Grep por
`rate.?limit|correlation|slowapi|structlog` em `backend/app`: **zero**. Hoje `/conferir` é um
endpoint pago (consome NFe.io) sem limite por obra — uma integração mal configurada pode gerar custo
ilimitado. `/health` também não verifica o banco
([main.py:28](backend/app/main.py#L28)), então um load balancer considera a API saudável com o
Postgres fora.

### M5 · Dependências sem teto superior e sem lock

[requirements.txt](backend/requirements.txt#L1) usa `>=` em todas as 7 linhas — inclusive
`fpdf2>=2.8.0`, cuja API `ln=` (usada ~30 vezes em
[laudo_pdf.py](backend/app/services/laudo_pdf.py#L167)) já está deprecada e será removida. Um
`pip install` daqui a 6 meses pode quebrar a geração de PDF silenciosamente. **Correção:** tetos
(`fpdf2>=2.8,<3`) + lock (`pip-tools`/`uv`) e testes no CI.

### M6 · `tzdata` faltando: o job de relatório quebra no Windows

[relatorio_semanal.py:20](backend/app/services/relatorio_semanal.py#L20) executa
`ZoneInfo("America/Sao_Paulo")` **em tempo de import**. No Windows, `zoneinfo` depende do pacote
`tzdata` (não é dependência transitiva) e não está no
[requirements.txt](backend/requirements.txt). Quem clonar o repo numa máquina limpa verá
`ZoneInfoNotFoundError` ao rodar os testes do relatório — e o job nem inicia. **Correção:** adicionar
`tzdata` (condicional a Windows) ou mover a criação do `ZoneInfo` para dentro de função.

### M7 · Higiene do repositório

- Não existe `.gitignore` na raiz; [backend/.gitignore](backend/.gitignore#L1) só cobre `backend/`.
  Ficam fora de qualquer ignore: `pwa/node_modules/` (**1.082 arquivos**),
  `dashboard/__pycache__/`, `.pytest_cache/` (na raiz do backend, este coberto).
- Existem `.pyc` **órfãos** de módulos que não existem mais:
  `backend/app/domain/__pycache__/classificacao.cpython-312.pyc` e `normalizacao.cpython-312.pyc`
  — sobras de refatoração. Ruído para quem procura código.
- `pwa/package.json` declara `"test": "vitest run"` e `vitest` como devDependency, mas **não existe
  `pwa/tests/`** → o script falha. Ou crie testes (render.js é puro e fácil de testar) ou remova.

### M8 · Cobertura de testes: boa no domínio, cega nas bordas

65 testes, distribuídos assim:

| Área testada | Arquivos | Situação |
|--------------|----------|----------|
| Domínio (matching, status, conversão) | `test_conferente.py` (13) | ✅ sólido |
| Multimaterial (cimento/bloco) | `test_conferencia_multimaterial.py` (4) | ✅ bom |
| NF-e adapter, chave, mensagens, PDFs | 6 arquivos | ✅ bom |
| Sessão PWA, auth por obra | 3 arquivos | ✅ bom |
| WhatsApp (mock de `httpx.post`) | `test_whatsapp_evolution.py` (7) | ✅ bom |
| **Routers (`/conferir`, `/override`, `/laudo.pdf`)** | — | ❌ **zero** (nenhum `TestClient` no repo) |
| **Fila de retentativa** | — | ❌ **zero** |
| **`conferencia_persist` / `nfe_persistencia`** | — | ❌ zero |
| **`laudo_storage`, `dashboard`, PWA** | — | ❌ zero |

Ou seja: **os cinco defeitos de severidade alta A3/A4/A5 e o M1 vivem exatamente na região sem
teste.** Um único teste de router com Postgres em container (testcontainers) teria pego A3 e A4.

### M9 · Laudo em bucket público = dado pessoal acessível por link

[laudo_storage.py:27](backend/app/services/laudo_storage.py#L27) devolve
`/storage/v1/object/public/{bucket}/{id}.pdf`, e o checklist recomenda explicitamente deixar o bucket
**público** ([CHECKLIST_GOLIVE_SUPABASE.md:56](docs/CHECKLIST_GOLIVE_SUPABASE.md#L56)). O PDF contém
CNPJ da obra e do fornecedor, chave da NF-e e divergências técnicas — a URL é adivinhável
(`{uuid}.pdf`) e não expira. Para a LGPD, o correto é bucket privado + URL assinada de curta duração
(ou servir o PDF sempre pela API, que já autoriza). O redirect já é restrito ao host do Supabase
([url_seguras.py:62](backend/app/utils/url_seguras.py#L62)), o que limita o *open redirect* mas não a
exposição.

---

## 7. Achados — severidade BAIXA

| # | Achado | Onde |
|---|--------|------|
| B1 | `relatorio_semanal_main.py` está **duplamente espaçado** (uma linha em branco entre cada linha de código): 222 linhas para ~110 de conteúdo. Funciona, mas denuncia um write corrompido — e qualquer diff futura fica ilegível | [relatorio_semanal_main.py](backend/app/relatorio_semanal_main.py#L1) |
| B2 | Docstring desatualizada: `comparador_cimento` diz "Integração … virá após matching por categoria", mas a integração já existe em `conferente.py` | [comparador_cimento.py:4](backend/app/services/comparador_cimento.py#L4) |
| B3 | O checklist de go-live lista **5 das 9** migrações; faltam e-mails, WhatsApp, idempotência e cimento. Quem seguir o doc cria um banco incompleto | [CHECKLIST_GOLIVE_SUPABASE.md:18](docs/CHECKLIST_GOLIVE_SUPABASE.md#L18) |
| B4 | O PWA descarta `esperado`/`recebido`: `render.js` só desenha `item` + `conclusão`, embora a API envie as quatro colunas que o PDF usa | [render.js:109](pwa/js/render.js#L109) |
| B5 | `handleAbrirDivergenciasPdf` reimplementa `fetchLaudoBlob` em vez de reutilizar | [main.js:203](pwa/js/main.js#L203) |
| B6 | Service worker: faz cache da casca no `install`, mas o handler de `fetch` só intercepta `navigate` — CSS/JS não vêm do cache, então **offline não funciona**. Faltam ícones no manifest (não é instalável de verdade) e não há limpeza de caches antigos no `activate` | [sw.js:16](pwa/sw.js#L16), [manifest.json](pwa/manifest.json#L1) |
| B7 | `datetime.utcnow()` (deprecado no 3.12) | [laudo_pdf.py:153](backend/app/services/laudo_pdf.py#L153) |
| B8 | `ln=` do fpdf2 deprecado; e a mesma fonte DejaVuSans é registrada para `""` e `"B"` — negrito é sintético/inexistente | [laudo_pdf.py:261](backend/app/services/laudo_pdf.py#L261) |
| B9 | Bloqueio de SSRF não cobre CGNAT (`100.64/10`) nem IPv4 mapeado em IPv6 | [url_seguras.py:23](backend/app/utils/url_seguras.py#L23) |
| B10 | Contrato JSON usa **chave acentuada** `"conclusão"`, com fallback `"conclusao"` só no gerador de PDF — armadilha para qualquer consumidor novo (dashboard, ERP futuro) | [conferente.py:585](backend/app/domain/conferente.py#L585) |
| B11 | `@layer components` envolvendo `:root`, `body` e `@keyframes` é uso não canônico do Tailwind; e `.sr-only` é reimplementado à mão | [input.css:5](pwa/src/input.css#L5) |
| B12 | `especificacoes` não tem unicidade por `(obra_id, bitola_mm)`: duas linhas para a mesma bitola casam sempre com a primeira, em silêncio | [conferente.py:133](backend/app/domain/conferente.py#L133) |
| B13 | Dashboard filtra por dia em **UTC** com rótulo de data local — o usuário em São Paulo vê um recorte deslocado de 3 h | [queries.py:37](dashboard/queries.py#L37) |
| B14 | `_enviar_texto_com_resiliencia` dorme (`time.sleep`) dentro de `BackgroundTasks`, ocupando thread do pool por até ~60 s | [whatsapp_evolution.py:194](backend/app/services/whatsapp_evolution.py#L194) |

---

## 8. Segurança — leitura consolidada

| Controle | Estado | Comentário |
|----------|--------|-----------|
| Autenticação por obra (API key) | ✅ | `compare_digest`, chave única por obra |
| Sessão PWA (HMAC, HttpOnly, SameSite configurável) | ✅ | bem feito, sem libs |
| Autorização por recurso (IDOR) | ✅ | todo `GET/POST` por `nfe_log_id` valida `obra_id` |
| Injeção de SQL | ✅ | 100% parametrizado |
| Validação de entrada (Pydantic v2) | ✅ | validadores de SSRF e de devolução |
| SSRF | ⚠️ **A1** | redirect contorna as checagens |
| Segredos | ✅ | `.env` ausente do repo; só `.env.example` |
| Rate limiting | ❌ | ausente (M4) |
| RLS no Postgres | ⚠️ | previsto na doc, inexistente no SQL; a API conecta como `postgres`, que **ignora RLS** de qualquer forma |
| Exposição de evidência (LGPD) | ⚠️ **M9** | bucket público com PDF identificável |
| CORS | ✅ | origens explícitas, credenciais permitidas só quando configurado |
| Cabeçalhos de segurança no PWA | ⚠️ | sem CSP/`X-Frame-Options` (depende do host estático) |

**Alerta importante sobre RLS:** mesmo que se adicionem políticas no Supabase, a API usa a role
`postgres` via `DATABASE_URL` — que é `BYPASSRLS`. RLS só protegeria acesso direto anônimo (chave
`anon`), não a API. Se a intenção é isolamento multi-tenant, ele tem de ser feito em código (como já
é, via `obra_id`) ou trocando a credencial para uma role restrita.

---

## 9. Documentação × código

| Documento | Estado |
|-----------|--------|
| [ARQUITETURA.md](docs/ARQUITETURA.md#L1) | Excelente nível de detalhe (C4, sequência, ER). **Desatualizado** em: dicionário de sinônimos (M3), rate limiting e observabilidade (M4), RLS (§7), entidade `CONVERSAO_MATERIAIS` (virou `normalizacao_materiais`, sem consumidor) |
| [CHECKLIST_GOLIVE_SUPABASE.md](docs/CHECKLIST_GOLIVE_SUPABASE.md#L1) | Útil e acionável. Lista 5 de 9 migrações (B3) |
| [DASHBOARD_ECONOMIA.md](docs/DASHBOARD_ECONOMIA.md#L1) | Coerente com o código |
| [.cursor/context.md](.cursor/context.md#L1) | Bom resumo; a lista de "próximos passos" está **desatualizada** — cimento já foi integrado e blocos já existem |
| `README.md` | **não existe** |

---

## 10. Roadmap sugerido (ordem de execução)

### Bloco 1 — bloqueadores do piloto (≈2–3 dias)

1. **A1** — `follow_redirects=False` + revalidação de host por hop em `_carregar_imagem_url`.
2. **A6** — `load_dotenv()` + falha rápida sem `DATABASE_URL`.
3. **A2** — `modo_aprendizado` default `FALSE`; migração sinalizando obras existentes.
4. **A3** — status efetivo separado (`status_calculado` vs `status_efetivo`), override propagado e
   recalculo bloqueado quando há override vigente.
5. **A4** — `tipo` na chave de idempotência.
6. **A6/A5** — normalizar quantidade de cimento/bloco pela unidade da especificação, consumindo
   `normalizacao_materiais`.

### Bloco 2 — confiabilidade (≈3–5 dias)

7. **M1** — `try/finally` por linha da fila + reaper de `processando` + `JSONDecodeError` tratado.
8. **M8** — `TestClient` + Postgres em container cobrindo `/conferir`, `/override`, fila e replay
   idempotente. **É o item de maior retorno por esforço.**
9. **M4** — rate limit simples (por obra + IP) e `/health` com `SELECT 1`.
10. **M5/M6** — tetos de versão, lock, `tzdata`.

### Bloco 3 — higiene e produto (≈2 dias)

11. `.gitignore` na raiz, remover `.pyc` órfãos, README com quickstart real.
12. CI (GitHub Actions): `pytest` + `npx tailwindcss` + `vitest`.
13. **M9** — bucket privado + URL assinada.
14. **M2** — comparadores devolvendo tags estruturadas.
15. PWA: cache real dos assets no SW, ícones no manifest, exibir `esperado`/`recebido`.

### Bloco 4 — dívida de produto

16. Dicionário de sinônimos de verdade (tabela `sinonimos` já existe e está vazia).
17. Quebrar `conferente.py` (670 linhas) em `matching/`, `validacao/` e `agregacao/` — hoje ele
    concentra roteamento por categoria, mensagens, formatação e agregação.
18. Observabilidade: `correlation_id` por conferência e métricas de falso positivo.

---

## 11. Nota de método

A análise foi **estática** (leitura de todo o código de `backend/app`, `dashboard`, `pwa/js`,
`supabase/migrations` e `docs`). O shell desta sessão falhou na preparação do sandbox
(`SetNamedSecurityInfoW failed (Win32 5): grantWrite(C:\Naturecode\stellSPY)`), portanto **não foi
possível executar `pytest`, `npm run build:css` nem `git status`**. As afirmações sobre ausência de
testes e de arquivos vieram de busca textual (`grep`/`glob`) em todo o repositório, não de execução.

Se o problema de ACL for corrigido, o próximo passo natural é rodar:

```powershell
cd backend; python -m pytest -q
cd ..\pwa; npm run build:css
```
