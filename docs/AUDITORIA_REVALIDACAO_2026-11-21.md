# Revalidação integral da auditoria técnica — SteelSPY

- **Data da revalidação:** 2026-11-21
- **Auditoria de referência:** `ANALISE_PROJETO.md` (2026-11-03), achados A1–A6, M1–M9, B1–B14
- **Branch analisada:** `main` (`6582142`), que é também o `HEAD` da branch `claude/steelspy-audit-revalidation-f21194` (árvore limpa no início da sprint)
- **Natureza da sprint:** somente diagnóstico. Nenhum código foi alterado; nenhum commit, push, merge, deploy ou migração foi feito. O único artefato novo é este documento.

---

## 1. Sumário executivo

**Veredito curto:** o SteelSPY ficou mais maduro desde 03/11 — a suíte passou de 65 testes unitários para **441 testes que passam contra PostgreSQL real, sem nenhum pulado** —, mas **o `main` ainda carrega os riscos mais graves da auditoria**: SSRF por redirect, override que deixa o banco contraditório, idempotência que torna a devolução inalcançável, fila que pode travar para sempre e laudos em bucket público.

**Ponto crítico de governança:** boa parte das correções existe em **duas branches não integradas ao `main`**. A `dec4d1` passa a suíte completa (493 testes, 0 pulados, verificado nesta sprint):

| Branch | Commits à frente do `main` | O que contém (por achado) |
|---|---|---|
| `claude/steelspy-project-analysis-dec4d1` (tip `b87aed2`) | 16 | A1 (`follow_redirects=False` + teste), A4 (`tipo` na idempotência), A6 (`load_dotenv` + `DATABASE_URL`), M1 (reaper `fila_reaper_travadas`), M9 (sem `enviar_laudo_pdf`, PDF só pela API). Ainda pendentes ali: A2 (código ok, mas `conferente.py:334` tem default `False`), B7 (`utcnow`), B14 (`time.sleep`) |
| `claude/steelspy-intelligence-evolution-247192` (tip `752318d`) | 9 | A1 (`url_seguras.py:175` com `follow_redirects=False` e `tests/test_foto_ssrf.py`), A2 (`conferente.py:328` default `False`), A4 (`conferencia.py:223` com `tipo`) |

Essas correções **não contam como resolvidas** para o `main`, conforme a regra da sprint: um commit com nome relacionado em outra branch não é evidência de correção no código atual. Elas são a principal alavanca do roadmap (seção 10): integrá-las é, provavelmente, mais barato do que reimplementar.

**Números (29 achados):**

| Classificação | Qtd. | Itens |
|---|---|---|
| RESOLVIDO | **4** | M2, M5, M6, B5 |
| PARCIALMENTE RESOLVIDO | **7** | A2, A5, M4, M7, M8, B6, B9 |
| NÃO RESOLVIDO | **18** | A1, A3, A4, A6, M1, M3, M9, B1, B2, B3, B4, B7, B8, B10, B11, B12, B13, B14 |
| REGRESSÃO | **0** | — |
| NÃO VERIFICADO | **0** | todos os itens receberam evidência de código; as lacunas de ambiente estão listadas na seção 5.3 |
| OBSOLETO | **0** | — |

**Respostas objetivas (conclusão executiva):**

1. **Resolvidos:** 4 de 29 integralmente.
2. **Parcialmente resolvidos:** 7.
3. **Continuam abertos:** 18 (incluindo os 4 de severidade ALTA A1, A3, A4 e A6).
4. **Não puderam ser verificados:** nenhum achado do escopo. Ficaram fora de verificação: CI em Linux (não executei), RLS com a `DATABASE_URL` real de produção (não tenho acesso) e lint (não há configuração de lint no repositório).
5. **Bloqueador para o piloto?** **Sim.** No `main`: A1 (SSRF real via redirect), A4 (devolução inalcançável), A3 (override contraditório no banco e no replay), M1 (NF presa em `processando` sem recuperação) e M9 (laudo em URL pública e adivinhável, com CNPJ e chave de NF-e — exposição LGPD). A6 também pesa: a API sobe sem erro quando `DATABASE_URL` não existe e conecta em `localhost`.
6. **O produto está tecnicamente mais maduro do que em 03/11?** **Sim, em base de testes, infraestrutura e segurança de acesso** (isolamento por RLS, role de aplicação `NOBYPASSRLS`, sessão com CSRF, rate limit de login, constraints travadas, CI que reprova skip). **Não no comportamento de negócio que o piloto vai usar** (override, devolução, fila) — nessas áreas o `main` está como em 03/11. A maturidade maior de fato existe nas branches não integradas.
7. **Próxima sprint recomendada:** **integração e fechamento de bloqueadores**, nesta ordem: (a) decidir e executar a integração das branches `dec4d1` e `intelligence-evolution` em um único caminho, com suíte completa; (b) fechar A1, A4, A3, A6, M1 e M9 no `main`; (c) só depois atacar o restante de média e baixa severidade. Detalhes na seção 10.

---

## 2. Situação atual do projeto

### 2.1 Git e árvore de trabalho

- `main` = `origin/main` = `6582142` ("docs: registra suite completa (441) apos correlacao por unidade").
- Árvore limpa na abertura da sprint; `git fsck --no-dangling` sem erros.
- Branches locais relevantes:
  - `claude/steelspy-project-analysis-dec4d1` → `b87aed2` (16 commits fora do `main`).
  - `claude/steelspy-intelligence-evolution-247192` → `752318d` (9 commits fora do `main`).
  - `feat/sprint3-operacional` → `afda40d`, com `origin/feat/sprint3-operacional` 9 commits à frente de origem; não foi analisada nesta sprint.
- Há 4 outras worktrees (inclui o checkout principal e as das branches acima). Nenhuma foi alterada.

### 2.2 Escopo do código (main)

- 29 migrações SQL em `supabase/migrations/` (eram 9 na auditoria).
- Backend FastAPI com routers `auth_pwa`, `auth_usuario`, `conferencia`, `evidencias`, `pedidos`; serviços de NF-e, PDF (laudo, divergências, dossiê), WhatsApp, fila, correlação, evidências e normalização.
- PWA vanilla com service worker; dashboard Streamlit; job de relatório semanal.
- CI em `.github/workflows/testes.yml`: sobe PostgreSQL 16 como serviço, roda `pytest -rs` e falha se houver qualquer teste pulado.

### 2.3 Estado de cada eixo, em uma frase

| Eixo | Estado no `main` |
|---|---|
| Testes | 441 passam com PostgreSQL real; 0 pulados. Cobrem routers, RLS, auth, pedidos, evidências, operacional. |
| Dependências | Travadas em `constraints.txt` com tetos em `requirements.txt`. |
| Segurança de acesso | Sessão HMAC com revogação, CSRF, RBAC por obra, isolamento multiempresa via RLS, role `stellspy_app` sem `BYPASSRLS`. |
| SSRF | Validação de entrada presente; download ainda segue redirects. |
| Regra de negócio (override, devolução, fila) | Substancialmente como na auditoria. |
| Armazenamento de laudos | Ainda em bucket público. Evidências de foto estão em storage privado. |
| PWA | Cache de casca e estáticos funciona; manifest sem ícones; `esperado`/`recebido` não exibidos; `npm test` quebrado. |

---

## 3. Matriz completa — A1 a A6, M1 a M9, B1 a B14

Legenda das colunas: **Classificação** · **Evidência principal (main)** · **Commit (main)** · **Teste que comprova** · **Risco residual** · **Próxima ação**.

### 3.1 ALTA

| ID | Achado | Classificação | Evidência principal (main) | Commit (main) | Teste | Risco residual | Próxima ação |
|---|---|---|---|---|---|---|---|
| A1 | SSRF via `foto_url` e redirects | **NÃO RESOLVIDO** | `backend/app/services/laudo_pdf.py:139` ainda usa `httpx.get(url, follow_redirects=True)`; `laudo_pdf.py:140-142` lê `r.content` sem teto de bytes; `url_seguras.py:33-59` valida só a URL inicial | — (correções em outras branches, ver §6) | `tests/test_url_seguras.py` cobre só literais de IP e allowlist; **nenhum caso de redirect** | **Alto**: redirect para `169.254.169.254` ou rede interna continua possível a partir de qualquer API key de obra; download sem limite | Integrar `follow_redirects=False` (como em `dec4d1`) + revalidação por hop + teto de bytes + teste de redirect |
| A2 | `modo_aprendizado` ligado por padrão | **PARCIALMENTE RESOLVIDO** | Migração `supabase/migrations/20261103150300_modo_aprendizado_default.sql` faz `SET DEFAULT FALSE`. Porém `backend/app/domain/conferente.py:327` (`modo_aprendizado: bool = True`) e `conferente.py:361` (`d.get("modo_aprendizado", True)`) mantêm `TRUE` no código | `ff59dbc` | `tests/integration/test_modo_aprendizado_db.py` | **Médio**: obras existentes continuam em modo aprendizado (decisão documentada na migração); código e banco divergem no default de fallback | Trocar o default do código para `False`; decidir se obras antigas são migradas ou mantidas |
| A3 | Override inconsistente (`nfe_logs` × `nfe_itens` × `xml_data`) | **NÃO RESOLVIDO** | `backend/app/routers/conferencia.py:580-587`: `UPDATE nfe_logs SET status_conferencia='VERDE', override_info=…` — nada em `nfe_itens`, `itens_resumo` ou `xml_data`. Não há `UPDATE nfe_itens` em `backend/app` | `bd053ba` (só corrige lock `FOR UPDATE OF n`) | Nenhum teste verifica propagação para `nfe_itens`/`itens_resumo`/PDF | **Alto**: replay (`conferencia.py:111-138`) devolve VERDE com `alerta` e `motivos` antigos; dashboard e CSV seguem contraditórios | Status efetivo separado + propagação + teste de consistência pós-override |
| A4 | Idempotência ignora `tipo` | **NÃO RESOLVIDO** | `backend/app/routers/conferencia.py:212-216`: `SELECT … WHERE obra_id = :obra AND chave_acesso = :chave` sem `tipo`; `conferencia.py:227-238` retorna a conferência da entrada. Constraint `UNIQUE (obra_id, chave_acesso)` em `supabase/migrations/20260410120000_core_schema.sql:44` | — (correção em `dec4d1` e `intelligence-evolution`, ver §6) | Nenhum teste de devolução com chave repetida no `main` | **Alto**: devolução da mesma chave nunca é registrada; o fluxo `nf_original_id` existe no schema mas não é alcançado | Integrar `AND tipo = :tipo` e ajustar a unicidade para incluir `tipo` (com migração) |
| A5 | Cimento e bloco sem normalização de unidade | **PARCIALMENTE RESOLVIDO** | Normalização presente: `comparador_cimento.py:117-118` e `comparador_bloco.py:80-81` chamam `converter_quantidade_recebida` (`backend/app/services/quantidade_material.py:60-115`). Unidade sem conversão segura vira AMARELO "não comparável" (`comparador_cimento.py:121-126`). Lacunas: fatores são constantes em `backend/app/services/normalizacao_cimento.py:4,16`; `normalizacao_materiais` só existe na migração `20260414120000_cimento_materiais_expand.sql`, **sem leitor** em `backend/app`; m², L e lata não têm equivalência | `e886bb8`, `ac5dd7d`, `d10cc3f` | `tests/test_quantidade_material.py`, `tests/test_cimento_modulo.py`, `tests/test_conferencia_multimaterial.py` | **Médio**: falso VERMELHO por sacos × m³ está eliminado; a tabela de fatores não é fonte de verdade | Ler fatores de `normalizacao_materiais` por obra/fornecedor |
| A6 | `.env` não carregado; fallback silencioso para `localhost` | **NÃO RESOLVIDO** | `backend/app/db.py:19-22`: `os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres")`; nenhuma chamada a `load_dotenv` em `backend/app` (`python-dotenv` só aparece como transitiva em `constraints.txt:45`) | — (correção em `dec4d1`: `load_dotenv()` e `DATABASE_URL` obrigatória, ver §6) | Nenhum teste de falha rápida sem `DATABASE_URL` | **Alto**: API sobe sem erro e tenta `localhost` com credencial padrão; a doc (`backend/.env.example:1`) ainda manda "Copie para .env" | Carregar `.env` explicitamente e falhar em produção sem `DATABASE_URL` |

### 3.2 MÉDIA

| ID | Achado | Classificação | Evidência principal (main) | Commit (main) | Teste | Risco residual | Próxima ação |
|---|---|---|---|---|---|---|---|
| M1 | Fila presa em `processando` | **NÃO RESOLVIDO** | Claim marca `processando` sem timestamp: `supabase/migrations/20261103140300_operacional_rls.sql:68-69`. `backend/app/services/fila_retentativa.py:128` chama `buscar_xml(chave)` **fora** do `try` (que começa em `:130`). `backend/app/services/nfe_io.py:225`: `r.json()` sem tratar `JSONDecodeError`. Não há reaper nem `claimed_em` (`grep` em `app/` e migrações) | — (reaper em `dec4d1`, `fila_reaper_travadas`) | `tests/integration/test_operacional.py:167` só prova que o claim marca `processando` | **Alto**: uma exceção no meio do lote aborta o tick e deixa as linhas restantes travadas para sempre; NF não é conferida | `try/finally` por linha + reaper por tempo de claim + teste de linha órfã |
| M2 | Tags de divergência perdidas (cimento/bloco) | **RESOLVIDO** (com ressalva) | Comparadores emitem `Quantidade:` (`comparador_cimento.py:125,132,137`; `comparador_bloco.py:88,94,99`) e o domínio casa `Quantidade:` (`conferente.py:233,280`) | `e886bb8` | `tests/test_quantidade_material.py:84` (unitário) | **Baixo**: acoplamento por texto permanece e não há teste ponta a ponta do comparador até `nfe_itens.divergencias` | Tags estruturadas (proposta original) ou teste ponta a ponta |
| M3 | Dicionário de sinônimos não implementado | **NÃO RESOLVIDO** | Tabela `sinonimos` só em DDL (`core_schema.sql:51-61`); `grep sinonimos` em `app/` e `dashboard/` sem leitura nem escrita. Matching é heurística fixa (`material_categoria.py:10`, `nfe_item_campos.py:13`). `docs/ARQUITETURA.md:171` ainda descreve `DICIONARIO_IA` como ativo | — | — | **Comercial**: a documentação vende o que não existe | Ou implementar ou retirar a promessa da doc |
| M4 | Rate limit e observabilidade | **PARCIALMENTE RESOLVIDO** | Rate limit de **login** por e-mail e IP em memória: `backend/app/limite_tentativas.py`, usado em `routers/auth_usuario.py:32`. `/health` continua estático (`backend/app/main.py:68-70`). `/conferir` (endpoint pago) sem limite. Sem `correlation_id`. Tratamento de indisponibilidade do banco com 503 (`main.py:37-65`) — melhoria fora do escopo da auditoria | `81bbbab` (login) | `tests/integration/test_auth.py:393` (`test_login_bloqueia_apos_o_limite_de_falhas`) | **Médio**: custo de NFe.io sem teto por obra; LB considera API saudável com banco fora | `/health` com `SELECT 1`; limite por obra em `/conferir`; `correlation_id` |
| M5 | Dependências sem teto e sem lock | **RESOLVIDO** | `backend/requirements.txt` com tetos (`fastapi>=0.162.0,<0.163`, `fpdf2>=2.9.0,<2.10`, `sqlalchemy>=2.1.6,<3.0` etc.); `backend/constraints.txt` com versões exatas e transitivas; CI instala com `-c backend/constraints.txt` (`testes.yml`) | `04b76bf`, `bce0155` | Suíte inteira passou com o conjunto travado (441) | **Baixo**: atualização é manual; constraints não tem processo automatizado | Manter política de subida de versão documentada |
| M6 | `tzdata` e Windows | **RESOLVIDO** | `backend/requirements.txt` declara `tzdata>=2024.1`; `backend/constraints.txt:52` fixa `tzdata==2026.6`. A suíte completa rodou no Windows 11 nesta sprint sem erro de zona | `04b76bf` | Suíte completa (441 passam) em Windows 11 | **Baixo**: `relatorio_semanal.py:20` ainda cria `ZoneInfo` em tempo de import | Mover para função (opcional) |
| M7 | Higiene do repositório | **PARCIALMENTE RESOLVIDO** | `.gitignore` na raiz existe e ignora `node_modules/` (`.gitignore:45`); `README.md` na raiz existe; `git ls-files` não lista `.pyc` nem `node_modules`. **Pendência:** `pwa/package.json:6` tem `"test": "vitest run"` e não há testes em `pwa/` — executado nesta sprint: `No test files found, exiting with code 1` | `59b0cef`, `6668591` | Execução de `npm run test` na cópia do `HEAD` | **Baixo/médio**: o script de teste falha e não há gate de PWA na CI | Criar testes ou remover o script; adicionar build CSS e vitest à CI |
| M8 | Cobertura de testes nas bordas | **PARCIALMENTE RESOLVIDO** | Avanço real: 161 funções de teste em `tests/integration/` com `TestClient` em 9 arquivos; `/override` testado (`test_auth.py`, `test_permissoes_portao.py`, `test_operacional.py`); fila testada com `processar_tick_fila` (`test_operacional.py:189-194`); RLS testado por tabela (`test_operacional.py:28-48`). **Lacunas:** nenhum teste de linha presa, de devolução com chave repetida, de propagação do override, nem de redirect em `foto_url`. PWA e dashboard sem teste | `280cfac`, `d58342e`, `5f56f68` | — | **Médio**: os defeitos A3, A4, M1 e A1 continuam fora do que a suíte prova | Testes de regressão para cada item ALTA antes de corrigir |
| M9 | Laudo público e LGPD | **NÃO RESOLVIDO** (no `main`; corrigido em `dec4d1`, §6.2) | `backend/app/services/laudo_storage.py:27-30` monta URL `/storage/v1/object/public/…`; `backend/app/routers/conferencia.py:402-416` grava essa URL e responde **302** para ela. `docs/CHECKLIST_GOLIVE_SUPABASE.md:56` recomenda bucket público. Não há código de retenção ou anonimização (só a permissão `solicitar_retencao` em `autorizacao.py:35,78`) | — (correção em `dec4d1`: laudo só pela API, §6) | Nenhum | **Alto para LGPD**: PDF com CNPJ, chave de NF-e e divergências, em URL previsível (`{uuid}.pdf`) e sem expiração | Bucket privado + URL assinada curta ou servir sempre pela API |

### 3.3 BAIXA

| ID | Achado | Classificação | Evidência principal (main) | Commit (main) | Risco residual / próxima ação |
|---|---|---|---|---|---|
| B1 | Espaçamento duplo em `relatorio_semanal_main.py` | **NÃO RESOLVIDO** | `backend/app/relatorio_semanal_main.py`: 222 linhas, 131 vazias | — | Reformatar e ajustar diff |
| B2 | Docstring desatualizada de `comparador_cimento` | **NÃO RESOLVIDO** | `backend/app/services/comparador_cimento.py:4`: "Integração … virá após matching" | — | Corrigir texto |
| B3 | Checklist de migrações incompleto | **NÃO RESOLVIDO** | `docs/CHECKLIST_GOLIVE_SUPABASE.md:16` lista 5 arquivos `.sql` específicos; `supabase/migrations/` tem **29** | — | Trocar a lista por instrução "aplicar todas em ordem" e `scripts/apply_migrations.py` |
| B4 | PWA não exibe esperado/recebido | **NÃO RESOLVIDO** | `pwa/js/render.js` não referencia `esperado` nem `recebido` (grep). A API já envia (`backend/app/domain/conferente.py:405-492`) | — | Exibir as colunas no PWA |
| B5 | Duplicação de `fetchLaudoBlob` | **RESOLVIDO** | Há uma única `fetchLaudoBlob` em `pwa/js/api.js:309`; `handleAbrirDivergenciasPdf` não existe mais em `pwa/js` | — | — |
| B6 | Service worker e offline | **PARCIALMENTE RESOLVIDO** | `pwa/sw.js:18-30`: cache da casca com versão e limpeza de caches antigos no `activate`; `pwa/sw.js:48-51`: cache-first para `/js/` e `/assets/`, então o app abre offline. API e PDF continuam só na rede (decisão declarada em `sw.js:1,32-35`). **Lacuna:** `pwa/manifest.json` não tem `icons` — não atende o critério de instalação | — | **Baixo**: instalação "de verdade" falha sem ícones |
| B7 | `datetime.utcnow()` | **NÃO RESOLVIDO** | `backend/app/services/laudo_pdf.py:153` | — | Trocar por `datetime.now(timezone.utc)` |
| B8 | `ln=`/`dest=` deprecados e negrito falso | **NÃO RESOLVIDO** | `ln=` em `laudo_pdf.py`, `dossie_pdf.py`, `divergencias_pdf.py` (warnings de deprecação na suíte); `dest=` em `dossie_pdf.py:320`; `add_font("DejaVu", "B", …)` com o mesmo TTF em `laudo_pdf.py:262-263`, `dossie_pdf.py:136-137`, `divergencias_pdf.py:42-43` | — | `fpdf2` está travado em 2.9.0, então hoje quebra só o aviso; migração para `new_x`/`new_y` antes de subir a versão |
| B9 | SSRF: CGNAT e IPv4 mapeado em IPv6 | **PARCIALMENTE RESOLVIDO** | IPv4 mapeado em IPv6 **bloqueado** (testado: `::ffff:169.254.169.254` e `::ffff:10.0.0.1` rejeitados). **CGNAT não bloqueado** (testado: `https://100.64.0.1/x` aceito). Código: `backend/app/utils/url_seguras.py:22-26` não cobre `100.64.0.0/10` | — | Adicionar `100.64.0.0/10` ao bloqueio e teste |
| B10 | Chave JSON acentuada `"conclusão"` | **NÃO RESOLVIDO** | `backend/app/domain/conferente.py:494,514,575,647` gravam `"conclusão"`; o gerador de PDF tem fallback (`laudo_pdf.py`) | — | Chave ASCII `conclusao` com alias de compatibilidade |
| B11 | Organização CSS/Tailwind | **NÃO RESOLVIDO** | `pwa/src/input.css:5` envolve `:root` e `body` em `@layer components`; `.sr-only` reimplementado em `input.css:95` | — | Mover para `@layer base` e usar utilitário do Tailwind |
| B12 | Unicidade de especificações por bitola | **NÃO RESOLVIDO** | `supabase/migrations/20260410120000_core_schema.sql:22-30`: tabela `especificacoes` sem `UNIQUE`; nenhuma migração posterior adiciona | — | Constraint parcial (obra, bitola) e tratamento de duplicata |
| B13 | Dashboard filtra por dia em UTC | **NÃO RESOLVIDO** | `dashboard/queries.py:33-38` e `:79-83` usam intervalo `00:00 UTC` | — | Intervalo em `America/Sao_Paulo` convertido para UTC |
| B14 | `time.sleep` em `BackgroundTasks` | **NÃO RESOLVIDO** | `backend/app/services/whatsapp_evolution.py:194` `time.sleep(sleep_s)`, com `sleep_s` de até 60 s (`:186`) | — | Retentativa assíncrona ou fila; ou limite menor no `BackgroundTasks` |

---

## 4. Evidências técnicas adicionais

### 4.1 SSRF (A1, B9) — testes executados contra `validar_url_imagem_publica`

| Entrada | Resultado |
|---|---|
| `https://100.64.0.1/x` (CGNAT) | **aceita** |
| `https://100.100.1.1/` (CGNAT) | **aceita** |
| `https://[::ffff:169.254.169.254]/x` | bloqueada |
| `https://[::ffff:10.0.0.1]/x` | bloqueada |
| `https://[::1]/x`, `https://[fe80::1]/x`, `https://[fc00::1]/` | bloqueadas |
| `https://169.254.169.254/`, `https://10.0.0.5/`, `https://127.0.0.1/` | bloqueadas |

**Ainda não coberto mesmo com a validação de entrada:**

- **Redirect:** `laudo_pdf.py:139` segue redirects sem revalidar o destino.
- **DNS:** a validação só olha host literal. Um domínio público que resolve para IP privado passa (DNS rebinding não é tratado).
- **Tamanho:** `laudo_pdf.py:140-142` lê o corpo inteiro com `r.content`.

### 4.2 Override e replay (A3)

- O `UPDATE` do override toca só `nfe_logs` (`conferencia.py:580-587`).
- O replay idempotente (`conferencia.py:111-138`) monta a resposta a partir de `xml_data` (snapshot antigo: `alerta`, `motivos`, `itens_processados`) com o `status` atual. Resultado: `status: VERDE` acompanhado de `alerta` e `motivos` de antes do override.
- **Ponto favorável:** como `conferencia.py:227-238` retorna antes de recalcular quando `status != PENDENTE` e `xml_data` existe, reconferir uma NF já com override **não sobrescreve** o VERDE. O efeito descrito no item A3 da auditoria ("recálculo sobrescreve o override") não ocorre no `main`; o problema que sobra é a inconsistência de armazenamento e de leitura.
- `nfe_itens` e `itens_resumo` continuam com os vermelhos originais; o dashboard (`dashboard/queries.py`) e o CSV semanal leem esses campos.

### 4.3 Idempotência e tipo (A4)

- Busca por `(obra_id, chave_acesso)` sem `tipo` (`conferencia.py:212-216`).
- Unicidade no banco em `(obra_id, chave_acesso)` (`core_schema.sql:44`).
- Resultado: `POST /conferir` com `tipo="devolucao"` e chave já conferida devolve a entrada, sem gravar nada.

### 4.4 Fila (M1)

- Claim atômico correto (`FOR UPDATE SKIP LOCKED` em função `SECURITY DEFINER`, `operacional_rls.sql:55-80`).
- Sequência de falha: `processar_tick_fila` marca o lote como `processando` (função do claim) → `buscar_xml` (`fila_retentativa.py:128`, **fora** do `try`) → `buscar_xml_ou_json_por_chave` pode levantar `JSONDecodeError` (`nfe_io.py:225`) → a exceção sobe pelo loop → o worker (`fila_worker_main.py`) termina o tick → as linhas do lote ainda não processadas e a linha da exceção ficam em `processando`.
- Nenhum mecanismo as reabre.

### 4.5 Unidades (A5)

- Conversão ativa para sacos, kg, m³ e toneladas (`quantidade_material.py:60-115`).
- Fatores fixos (`normalizacao_cimento.py`): 28 sacos de 50 kg ≈ 1 m³, massa aparente de 1400 kg/m³.
- A tabela `normalizacao_materiais` (`20260414120000_cimento_materiais_expand.sql`) não é lida pela aplicação.
- Sem `unidade_prevista` na especificação, o comparador compara quantidades como vieram (comportamento legado declarado no código).

### 4.6 Segurança de acesso

- **RLS:** 7 arquivos de migração com `ENABLE ROW LEVEL SECURITY`, 22 ocorrências no total. `tests/integration/test_operacional.py` verifica por tabela que RLS está ligado e forçado, que há policy e que `tenant_id` é obrigatório, e testa isolamento entre tenants.
- **Role de aplicação:** `supabase/migrations/20261103120500_app_role.sql:15-22` cria `stellspy_app` com `NOBYPASSRLS`.
- **Risco não verificado:** `backend/.env.example:4` aponta a `DATABASE_URL` para o usuário `postgres.[REF]` do pooler. Se produção usar essa role, RLS pode ser contornado. Verificação exige acesso ao ambiente de produção, que não tenho.
- **Autorização por obra:** RBAC em `autorizacao.py`; `/conferir` com sessão exige CSRF (`conferencia.py:183-184`) e valida tenant (`conferencia.py:185-190`). Testes de CSRF em `tests/integration/test_auth.py:311-322`.
- **LGPD:** sem política de retenção ou eliminação implementada (ver M9).

### 4.7 PWA (B4, B6)

- Service worker com versão de cache (`steelspy-v4`), limpeza no `activate`, `skipWaiting` e `clients.claim` (`sw.js:18-30`).
- Estáticos com cache-first; navegação com fallback para `index.html`; API e PDF sem cache (`sw.js:36-51`).
- Manifest sem `icons`.
- `render.js` não exibe `esperado`/`recebido`, embora a API envie os dados.

### 4.8 Build CSS e Vitest da PWA (executados)

Executado em cópia exportada do `HEAD` (`git archive`) para um diretório de trabalho novo, fora do repositório:

- `npm ci`: 112 pacotes instalados, exit 0.
- `npm run build:css`: exit 0.
- `npm run test` (`vitest run`): **exit 1** — `No test files found, exiting with code 1`.

---

## 5. Testes executados e resultados

### 5.1 Ambiente

- Windows 11 (10.0.26340), Python 3.13.15, ambiente virtual criado fora do repositório, instalado com `pip install -r requirements-dev.txt -c constraints.txt` (exit 0).
- PostgreSQL 16 (imagem `postgres:16-alpine`) em container local descartável `stellspy-pg-revalidacao`, porta 55432, com as credenciais de teste documentadas em `backend/tests/integration/conftest.py`. Nenhum dado real foi tocado.
- Docker Desktop 29.8.1.

### 5.2 Resultados

| # | Verificação | Comando | Resultado |
|---|---|---|---|
| T1 | Suíte sem banco | `python -m pytest -q` (backend) | **265 passed, 176 skipped** — os 176 pulados são os de integração sem PostgreSQL. Por isso a suíte sem banco não prova nada sobre isolamento, idempotência ou override |
| T2 | Suíte completa com PostgreSQL 16 | `python -m pytest -q -rs` (backend) | **441 passed, 0 skipped**, 401 s, 175 warnings de deprecação do `fpdf2` |
| T3 | Migrações (idempotência) | `python scripts/apply_migrations.py --url <owner local>` executado duas vezes | Nas duas execuções: `29 já aplicadas`, `pendentes: 0`, `concluído: 0 aplicada(s)`, exit 0. O banco já estava migrado por T2 |
| T4 | Build CSS | `npm run build:css` em cópia do `HEAD` | exit 0 |
| T5 | Vitest | `npm run test` em cópia do `HEAD` | **exit 1**: nenhum arquivo de teste |
| T6 | Integridade do Git | `git fsck --no-dangling` | sem erros |
| T7 | Lint | — | **Não executado**: o repositório não tem configuração de lint (ruff, flake8, mypy). Não há o que rodar sem inventar uma configuração |
| T8 | Suíte completa na branch `dec4d1` (não integrada) | `pytest -rs` em exportação (`git archive`) da branch, mesmo PostgreSQL, em diretório fora do repositório | **493 passed, 0 failed, 0 skipped**, 188 s, 199 warnings de deprecação |

### 5.3 Lacunas de verificação (declaradas, não simuladas)

- **CI em Linux (`ubuntu-latest`):** não executei o workflow. A compatibilidade Linux é inferida, não observada.
- **RLS com a `DATABASE_URL` de produção:** não tenho acesso. Não foi possível confirmar qual role a produção usa.
- **Bucket de laudos em produção:** não verificado no provedor; a conclusão de M9 vem do código e do checklist.
- **Lint:** não configurado.
- **Testes de PWA:** não existem; nada a executar além do exposto em T4–T5.

---

## 6. Riscos críticos ainda abertos e branches não integradas

### 6.1 Riscos críticos abertos no `main`

1. **A1 — SSRF via redirect.** Qualquer chave de obra pode fazer o servidor buscar URLs internas por redirect. Não há teto de tamanho.
2. **A4 — devolução inalcançável.** Mesma chave da entrada devolve a entrada. Dado de negócio errado, sem erro visível.
3. **A3 — override inconsistente.** Laudo, dashboard e CSV contradizem o status efetivo.
4. **M1 — NF presa em `processando`.** Sem recuperação automática.
5. **M9 — laudo público.** PDF com CNPJ e chave de NF-e em URL previsível e sem expiração; a API responde 302 para ela.
6. **A6 — configuração silenciosa.** API sobe conectando em `localhost` quando `DATABASE_URL` falta.

### 6.2 Branches não integradas — situação dos achados

As branches foram exportadas com `git archive` para diretório novo, sem checkout e sem alterar o repositório. Os achados abaixo são verificados por leitura de código (`git grep`), não por execução.

| Branch | Achado | Situação na branch |
|---|---|---|
| `claude/steelspy-project-analysis-dec4d1` | A1 | `backend/app/services/laudo_pdf.py:195` com `follow_redirects=False` (cliente com timeout) |
| `claude/steelspy-project-analysis-dec4d1` | A4 | `backend/app/routers/conferencia.py:221-223` busca com `AND tipo = :tipo` |
| `claude/steelspy-project-analysis-dec4d1` | A6 | `backend/app/db.py:14,23` com `load_dotenv()` |
| `claude/steelspy-project-analysis-dec4d1` | M1 | `backend/app/services/fila_retentativa.py:105-112` com `_reaper_travadas` e `fila_reaper_travadas(:m)` |
| `claude/steelspy-project-analysis-dec4d1` | A2 | `backend/app/domain/conferente.py:334` com `modo_aprendizado: bool = False` |
| `claude/steelspy-project-analysis-dec4d1` | M9 | sem `enviar_laudo_pdf` nem `object/public` em `backend/app` (`git grep`) |
| `claude/steelspy-project-analysis-dec4d1` | B7 | **não** corrigido: `laudo_pdf.py:226` ainda usa `utcnow()` |
| `claude/steelspy-project-analysis-dec4d1` | B14 | **não** corrigido: `whatsapp_evolution.py:194` ainda com `time.sleep` |
| `claude/steelspy-project-analysis-dec4d1` | A1 (teste) | `backend/tests/test_url_seguras.py:69` verifica `follow_redirects is False` (teste por mock, não de rede) |
| `claude/steelspy-intelligence-evolution-247192` | A1 (teste) | `backend/tests/test_foto_ssrf.py` cobre redirect e DNS (fixação de IP) |
| `claude/steelspy-intelligence-evolution-247192` | A2 | `conferente.py:328` com `modo_aprendizado: bool = False` |
| `claude/steelspy-intelligence-evolution-247192` | A4 | `conferencia.py:223` com `AND tipo = :tipo` |

**Atenção:** essas evidências são de leitura de código. Não rodei as suítes dessas branches nesta sprint (ver §6.3). Antes de integrar qualquer uma delas, a suíte precisa passar nela.

### 6.3 Suíte completa da branch `dec4d1`

Executada com PostgreSQL 16 local (mesmo container da T2): **493 passed, 0 failed, 0 skipped** (T8). A `dec4d1` tem 52 testes a mais que o `main` e todos passam. Isso não prova que as correções de A1, A3, A4, A6 e M1 estejam completas: não há caso de redirect com rede real e não há teste de override propagado para todos os destinos. Ainda assim, é a evidência de integração mais forte disponível hoje. A `intelligence-evolution` não foi executada nesta sprint.

---

## 7. Regressões encontradas

**Nenhuma regressão confirmada no `main`.** Conferi os itens da auditoria que estavam "corrigidos" em commits anteriores (M2, M5, M6) e o comportamento atual bate com a correção.

Ressalvas que **não são regressão**, mas merecem atenção:

- O comentário de `.github/workflows/testes.yml:1` diz "Os 418 testes da suíte", e `backend/constraints.txt:12` diz "82 testes aprovados": ambos estão desatualizados (a suíte tem 441).
- `docs/execucao/PROXIMOS_PASSOS.md` marca P-07, P-08, P-09, P-11 e P-12 como `PLANEJADO`. Isso é coerente com o `main`, mas incoerente com as branches que já têm as correções.

---

## 8. Divergências entre documentação e código

| Documento | O que diz | O que o código faz | Ação |
|---|---|---|---|
| `ANALISE_PROJETO.md` §2 e §9 | "Não existe README na raiz", "não existe `.gitignore` na raiz" | Ambos existem | Atualizar o documento de auditoria ou marcá-lo como histórico |
| `ANALISE_PROJETO.md` §3 | "65 testes" | 441 testes (265 unitários + 176 de integração) | Idem |
| `docs/ARQUITETURA.md:171` | Mostra `DICIONARIO_IA` como ativo | Tabela `sinonimos` sem leitura nem escrita; M3 | Remover o ativo ou implementar |
| `docs/CHECKLIST_GOLIVE_SUPABASE.md:16` | Lista 5 migrações | 29 migrações | Trocar lista por instrução geral |
| `docs/CHECKLIST_GOLIVE_SUPABASE.md:56` | Recomenda bucket **público** | Expõe PDF identificável (M9) | Corrigir ao fechar M9 |
| `backend/.env.example:1` | "Copie para `.env`" | `.env` não é carregado (A6) | Corrigir ao fechar A6 |
| `.github/workflows/testes.yml:1` | "Os 418 testes" | 441 | Atualizar comentário |
| `backend/constraints.txt:12` | "82 testes aprovados" | 441 | Atualizar comentário |
| `pwa/package.json:6` | `"test": "vitest run"` | Nenhum teste; script falha | Criar testes ou remover |
| `docs/execucao/PROXIMOS_PASSOS.md` (linhas 125–130) | P-07, P-08, P-09, P-11 e P-12 como `PLANEJADO` | Correções existem em branches não integradas | Decidir integração e atualizar o status |

---

## 9. Percentual de resolução por severidade

Duas métricas: **contagem** (só RESOLVIDO conta) e **ponderada** (RESOLVIDO = 1; PARCIALMENTE = 0,5; NÃO RESOLVIDO = 0).

| Severidade | Total | RESOLVIDO | PARCIAL | NÃO RESOLVIDO | % contagem | % ponderada |
|---|---|---|---|---|---|---|
| ALTA (A1–A6) | 6 | 0 | 2 (A2, A5) | 4 (A1, A3, A4, A6) | **0%** | **17%** |
| MÉDIA (M1–M9) | 9 | 3 (M2, M5, M6) | 3 (M4, M7, M8) | 3 (M1, M3, M9) | **33%** | **50%** |
| BAIXA (B1–B14) | 14 | 1 (B5) | 2 (B6, B9) | 11 | **7%** | **14%** |
| **Total** | **29** | **4** | **7** | **18** | **14%** | **26%** |

A leitura honesta: **nenhum item ALTA está integralmente resolvido**. A média severidade é a que mais avançou, e é onde estão as maiores correções de qualidade de engenharia (testes, dependências, CI, unidades).

---

## 10. Roadmap atualizado, priorizado por risco

### Passo 0 — decisão de integração (antes de qualquer código)

- Decidir o caminho das duas branches: integrar `dec4d1` (mais avançada, 16 commits) e avaliar `intelligence-evolution` (9 commits, sobreposição com A1/A2/A4). Conflitos, testes e status do `PROXIMOS_PASSOS` precisam ser resolvidos em um único lugar.
- Rodar a suíte completa após a integração, com PostgreSQL. Só aceitar com 0 pulados.

### Bloco 1 — bloqueadores do piloto (ALTA e M9)

1. **A1** — `follow_redirects=False` em `laudo_pdf.py:139` (ou equivalente integrado), revalidação por hop, teto de bytes no download, bloqueio de `100.64.0.0/10`, e **teste de redirect** que hoje não existe.
2. **A6** — `load_dotenv()` explícito e falha rápida sem `DATABASE_URL` em produção. Teste: subir sem a variável e esperar erro.
3. **A4** — `tipo` na busca de idempotência e na unicidade (com migração), e teste de devolução com chave repetida.
4. **A3** — status efetivo separado (`status_calculado`/`status_efetivo`), propagação para `nfe_itens` e `itens_resumo`, e teste que lê o replay depois do override.
5. **M9** — bucket privado e URL assinada curta, ou servir o PDF só pela API. Alterar também `docs/CHECKLIST_GOLIVE_SUPABASE.md:56`.
6. **M1** — `try/finally` por linha, `claimed_em` e reaper, com teste de linha órfã.

### Bloco 2 — confiabilidade e defaults

7. **A2** — trocar o default do código (`conferente.py:327,361`) para `False` e decidir sobre obras existentes.
8. **A5** — ler fatores de `normalizacao_materiais` em vez de constantes.
9. **M4** — `/health` com `SELECT 1`; limite de `/conferir` por obra; `correlation_id`.
10. **M3** — implementar o dicionário de sinônimos ou retirar a promessa de `docs/ARQUITETURA.md`.
11. **B14** — retirar `time.sleep` do `BackgroundTasks` (ou limitar a espera).

### Bloco 3 — higiene e PWA

12. **M7/CI** — `npm run test` deve ter testes ou ser removido; incluir build CSS e vitest na CI.
13. **B4, B6** — exibir `esperado`/`recebido`; adicionar `icons` ao manifest.
14. **B1, B2, B3, B7, B8, B10, B11, B12, B13** — cosméticos e de contrato (ver matriz).

### Bloco 4 — dívida de produto

15. **M2** — tags estruturadas ou teste ponta a ponta do comparador.
16. **M8** — testes de regressão para cada item ALTA e M1; PWA e dashboard sem teste hoje.
17. **B9** — já incluído no Bloco 1 pelo bloqueio de CGNAT; manter o teste.

---

## 11. Notas de método

- A análise é **de código e de execução**: cada item tem evidência de arquivo/linha. Não usei lembranças de implementações anteriores.
- Quando a evidência veio de outra branch, ela foi marcada como tal e **não** foi usada para classificar o `main`.
- Nenhuma credencial real foi usada ou registrada. O PostgreSQL de teste é descartável e local.
- Uma operação de limpeza na pasta de scratch foi bloqueada pelo usuário durante a sprint; não foi repetida e não afetou o repositório.

---

## 12. Integração na branch `claude/integracao-auditoria-2026-11-21` (sprint de 2026-11-21, etapa 5)

Esta seção não altera a classificação das seções 1–11, que descrevem o `main` (`6582142`). Ela registra o que a branch de integração passou a conter. A base é `claude/steelspy-intelligence-evolution-247192` (`752318d`, ancestral do HEAD), com cherry-picks seletivos de `claude/steelspy-project-analysis-dec4d1` (`b87aed2`).

### 12.1 Causa do travamento de `test_idempotency_key_em_corrida_grava_uma_unica_evidencia`

- **Ambiente (causa medida):** no Windows, `localhost` resolve primeiro para `::1`. Cada conexão nova esperou ~21 s pelo timeout IPv6 antes de cair para `127.0.0.1` (medido: `127.0.0.1` 0,02–0,07 s; `localhost` 21,1 s; `::1` falha em 21 s). A suíte abre dezenas de conexões, então isso vira minutos de espera. Um `faulthandler` com dump aos 120 s mostrou a thread principal parada em `psycopg2.connect`, dentro do fixture `banco_limpo` (`scripts/apply_migrations.py`), e não no teste.
- **Harness (falha de desenho do teste, pelo código):** a barreira de 4 partes ficava dentro de `gravar`, depois da checagem de idempotência. Uma requisição que perdia a corrida no `SELECT` nunca chegava à barreira. O timeout de 2 s com `BrokenBarrierError` ignorado escondia isso, e o teste passava sem garantir a corrida. Com o timeout antigo de 30 s, a mesma situação levaria a uma falha (exceção não tratada), não a um travamento.
- **Implementação:** não é a causa. Uma mutação (sem `rollback` no ramo `IntegrityError`) faz o teste falhar, o que confirma que o caminho de INSERT concorrente é exercitado. Na implementação, a espera no índice único termina quando o vencedor commita.
- **Ressalva:** o travamento de mais de 8 min não foi reproduzido. A causa medida explica esperas de minutos (conexões de 21 s, barreira de 30 s). A variação de tempo do setup, de 3 s a 160 s, segue sem explicação completa (ver 12.6).

### 12.2 Correção

- `backend/tests/integration/conftest.py`: URLs padrão com `127.0.0.1` (override por `STELLSPY_TEST_DB_*` continua).
- `backend/tests/integration/test_hardening_operacional.py`: a barreira saiu de `gravar` e passou para uma sessão embrulhada que espera antes da primeira checagem de idempotência. Só a primeira checagem de cada sessão espera. Timeout de 30 s, sem `except`: se alguma requisição não chegar, o teste falha. Todas as N requisições leem a tabela vazia e disputam o índice único.

### 12.3 Resultados de teste (PostgreSQL 16, container `stellspy-pg-revalidacao`, porta 55432)

| Verificação | Resultado |
|---|---|
| Teste de corrida isolado, 10 execuções | 10 de 10 passam, 0 falhas, 0 pulados. Duração total do teste: 3 s a 160 s (a variação está no setup do banco; a chamada do teste leva 0,4 s a 0,8 s) |
| Suíte `tests/integration` (antes dos cherry-picks) | **183 passed**, 0 pulados, 260 s |
| Suíte completa (após a correção, antes dos cherry-picks) | **494 passed**, 0 pulados, 152 s |
| Suíte completa (após os cherry-picks) | **505 passed**, 0 pulados, exit 0, 177 s |
| Migrações, banco novo e isolado (`postgres:16-alpine`, porta 55440) | Execução 1: 33 aplicadas, exit 0. Execução 2: 0 pendentes, exit 0 |
| Validação final (2026-11-22), suíte completa com PostgreSQL | **505 passed**, 0 pulados, exit 0, 512 s |
| Validação final (2026-11-22), teste de corrida, 3 execuções isoladas | 3 de 3 passam (65 s, 73 s, 239 s; a chamada do teste é rápida, a diferença está no setup) |
| Validação final (2026-11-22), migrações em banco novo `validacao_20261122` | Execução 1: 33 aplicadas, exit 0. Execução 2: 0 pendentes, exit 0 |

### 12.4 Commits integrados

| Hash | Assunto | Origem | Observação |
|---|---|---|---|
| `6247d0b` | test(hardening): corrida de idempotência sem best-effort e banco por 127.0.0.1 | sessão desta etapa | correção das seções 12.1–12.2 |
| `f6a0770` | fix(config): DATABASE_URL obrigatória em produção; .env carregado | `eecbbbc` (A6) | sem conflito de conteúdo |
| `062e65e` | fix(health): /health consulta o banco e responde 503 quando ele cai | `120c131` (M4) | cobre só a parte de `/health`; limite por obra e `correlation_id` seguem abertos |
| `2bbe425` | fix(laudo): PDF entregue só pela API, sem bucket público nem redirect | `5e0586e` (M9) | conflitos resolvidos a favor da base: o SSRF de `url_seguras` (P-07) foi mantido; removidos `url_redirect_laudo_confiavel` e o teste dele; teste de laudo portado com o helper `_preparar_nf_vermelha_com_item` e o `_SNAPSHOT_VERMELHO` |
| `8d39ba7` | fix(fila): reaper libera linhas presas em processando | `3aa3156` (M1) | inclui a migração `20261114120000_fila_reaper.sql`; conflito de testes resolvido mantendo os 2 testes do reaper |
| `c120de6` | fix(fila): exceção em buscar_xml não deixa linha presa em processando | `31c21e1` (M1) | o teste `test_erro_na_busca_do_xml…` já estava em `8d39ba7`, então não foi duplicado; esta commit traz o `try` em `fila_retentativa.py` e o tratamento de corpo não-JSON em `nfe_io.py` |

**Não integrados (decisão nesta etapa):**

- `54a7b21` (agregação do override): substituído pelo `52fee46` (P-09), que já está na base. Os dois desenhos divergem: a branch `dec4d1` projeta `ACEITO_OVERRIDE` e usa a chave `aceitos_por_override`; a base projeta `VERDE` e usa `vermelhos_aceitos`, que o CSV semanal já consome. O commit também traz `pandas` em `requirements-dev.txt`, usado só pelo teste dele. Integrá-lo exigiria escolher um dos dois desenhos. **Não aplicado (verificado em 2026-11-22):** a base já agrega o override (`vermelhos_aceitos` em `itens_resumo`, coluna `itens_vermelhos_aceitos` no CSV e testes do P-09), então o commit duplica o achado. O critério combinado era aplicar só se não duplicasse `52fee46`/`96a6969`. Sem hash resultante.
- `b399f25` (foto do laudo em streaming com teto de bytes e IP fixado): a base já tem `baixar_foto_segura` com teto de 10 MB e fixação de IP (P-07).
- `b87aed2` (testes de bordas com PostgreSQL, fora do escopo listado): candidato a integrar depois.
- Já cobertos pela base, não trazidos: `5d22539`, `4ff8ea0`, `29a26ac`, `482ae30`, `09919ee`, `b92e14d`, `52fee46`, `96a6969`. Normalização de unidades (`2c35c77`, `996a695`, `42e66f9`) já está no `main`. Migrações duplicadas `20261112120000` e `20261113120000` cobertas por `20261121130000` e `20261121120000`. Documentação antiga (`89ae3f8` e o `PROXIMOS_PASSOS` de `dec4d1`) não foi trazida.

### 12.5 Migrações

- Adicionada nesta integração: **`supabase/migrations/20261114120000_fila_reaper.sql`** (função `fila_reaper_travadas`, SECURITY DEFINER; linhas `processando` há mais de 10 min voltam a `pendente`, com contagem de tentativa; na 3ª tentativa viram `falha`).
- Total de arquivos em `supabase/migrations/`: 33 (29 do `main`, + 3 da base `intelligence`, + 1 desta integração).
- Não foi executada em produção.
- **Não verificado:** a aplicação dessa migração num banco que já tem `20261121*` aplicado (ordem fora de sequência). O runner aplica os pendentes por nome, então o comportamento esperado é aplicar sem erro, mas não foi testado. O comando de teste desse cenário foi interrompido pelo usuário e não foi repetido.

### 12.6 Riscos ainda abertos

1. Ordem de migração: `20261114120000` é anterior às `20261121*`. Validar no cenário de produção (ver 12.5) antes de qualquer aplicação.
2. `54a7b21` não aplicado por duplicar o P-09 (12.4). Sem pendência.
3. Variação de tempo do teste de corrida (3 s a 160 s) no setup do banco; não explicada completamente. O travamento de mais de 8 min não foi reproduzido.
4. M4 segue parcial: falta limite por obra em `/conferir` e `correlation_id`.
5. Continuam abertos do `main`: A5 (fatores fixos de cimento), B7 (`utcnow`), B14 (`time.sleep` em `BackgroundTasks`), B8 (`ln=`/`dest=` do `fpdf2`), B13 (dia em UTC no dashboard), M3 (dicionário de sinônimos), e os demais itens baixos da seção 3.3.
6. `b87aed2` e `b399f25` não integrados (12.4).
7. Container `stellspy-pg-migr-validacao-20261121` (porta 55440) continua em execução; não foi removido.
8. Nada foi enviado (push), mesclado no `main` nem aberto PR.

### 12.7 Resultado da integração

Branch `claude/integracao-auditoria-2026-11-21` com 6 commits à frente da base (`6247d0b`, `f6a0770`, `062e65e`, `2bbe425`, `8d39ba7`, `c120de6`). Suíte completa com PostgreSQL: 505 passam, 0 pulados. Migrações validadas em banco novo, com idempotência na segunda execução. Documentos (este arquivo e `PROXIMOS_PASSOS.md`) ainda não commitados. Aguardando aprovação do usuário para a próxima etapa.

---

## 13. Sprint de 2026-11-27 — fechamento dos itens abertos (PR #3)

**Escopo:** plano aprovado pelo usuário, executado na branch `claude/integracao-auditoria-2026-11-21` a partir do `9c6fd63`. Decisões já tomadas: **M3 sai só da documentação** (não implementar); o PR fica pronto para revisão e **o merge no `main` é do usuário**; a ação operacional do **bucket público de laudos** é do usuário e está fora da sprint.

**Estado em uma frase:** dos 29 achados, 19 estão resolvidos na branch, 4 parciais e 6 abertos (ver §13.2). Nada foi mesclado, enviado para produção ou alterado no bucket.

### 13.1 Commits

| Hash | Itens | Testes novos |
|---|---|---|
| `3a7b1bd` | M4 (limite por obra em `/conferir`, `X-Correlation-ID`), B9 (CGNAT) | 8 (5 integração, 3 unitários) |
| `3950f65` | B12 (migração `20261127120000_especificacoes_unica_bitola.sql`), B14 (teto de espera do WhatsApp) | 4 (3 integração, 1 unitário) |
| `110f46e` | B4 (esperado/recebido no PWA), B6 (ícones 192/512), M7 (testes do vitest) | 8 vitest |
| `5b59981` | B7 (`utcnow`), B8 (`ln=`/`dest=` do fpdf2 e negrito falso), B10 (chave `conclusao`) | 5 (guardas estáticas) |
| `a1fe72d` | B13 (dia de São Paulo no dashboard) | 4 |
| `6bb3696` | B1, B2, B3, B11, M3 | 5 (guardas) |
| (este commit) | atualização da documentação (§13 e `PROXIMOS_PASSOS.md`) | — |

Contagem de testes: **513 coletados no `9c6fd63`, 539 no HEAD desta sprint** (+26 pytest); vitest: 8 testes.

### 13.2 Estado por item

| Item | Antes (§3, baseline `main`) | Agora (branch) | Observação |
|---|---|---|---|
| M3 | NÃO RESOLVIDO | **RESOLVIDO** (escopo documentação) | `docs/ARQUITETURA.md` não apresenta mais `DICIONARIO_IA` nem sinônimos como ativos. A tabela `sinonimos` segue sem leitura nem escrita: dívida registrada, não implementação |
| M4 | PARCIAL | **RESOLVIDO** | `/conferir` tem teto de consultas pagas por obra (`CONFERIR_LIMITE_POR_OBRA`, padrão 60 por 600 s, via `limite_tentativas`); respostas idempotentes não gastam cota; `X-Correlation-ID` aceito quando seguro, senão gerado, devolvido no cabeçalho e nos logs. **Ressalva:** contador em memória por processo, como o de login: com N workers o teto efetivo é N × limite |
| M7 | PARCIAL | **PARCIAL** | `npm run test` passa (8 testes reais, script mantido). **Pendência:** `.github/workflows/testes.yml` roda só o pytest; vitest e `build:css` não estão no CI |
| B1 | NÃO RESOLVIDO | **RESOLVIDO** | linhas vazias em excesso removidas de `relatorio_semanal_main.py` (223 → 182 linhas) |
| B2 | NÃO RESOLVIDO | **RESOLVIDO** | docstring de `comparador_cimento.py` descreve o estado atual |
| B3 | NÃO RESOLVIDO | **RESOLVIDO** | checklist manda aplicar todas as migrações em ordem (`supabase db push` ou `scripts/apply_migrations.py`) |
| B4 | NÃO RESOLVIDO | **RESOLVIDO** | `renderizarResultado` mostra Esperado, Recebido na NF e Análise, com travessão para campo ausente |
| B6 | PARCIAL | **RESOLVIDO** | manifest com ícones 192 e 512. **Ressalva:** os PNGs são sólidos provisórios; trocar pela arte da marca |
| B7 | NÃO RESOLVIDO | **RESOLVIDO** | `datetime.now(timezone.utc)` em `laudo_pdf.py`; guarda impede `utcnow` no app |
| B8 | NÃO RESOLVIDO | **RESOLVIDO** | `new_x`/`new_y` e `output()` no lugar de `ln=`/`dest=`. O negrito de DejaVu, que nunca foi negrito real (mesmo TTF), passa a ser regular: visual igual ao que já era |
| B9 | PARCIAL | **RESOLVIDO** | `100.64.0.0/10` bloqueado na validação literal e no DNS (teste de download sem conexão) |
| B10 | NÃO RESOLVIDO | **RESOLVIDO** | `conferente.py` grava `conclusao`; o PDF e o PWA leem a chave nova e aceitam `conclusão` como alias. **Dados já gravados** mantêm a chave antiga e são lidos pelo alias |
| B11 | NÃO RESOLVIDO | **RESOLVIDO** | `:root` e `body` em `@layer base`; `.sr-only` vem do Tailwind; `app.css` recompilado |
| B12 | NÃO RESOLVIDO | **RESOLVIDO** | índice único parcial `(obra_id, bitola_mm) WHERE bitola_mm IS NOT NULL`; a migração aborta com a lista de duplicatas e não apaga dados |
| B13 | NÃO RESOLVIDO | **RESOLVIDO** | intervalo de dia em `America/Sao_Paulo`, convertido para UTC só na consulta (`dashboard/intervalo.py`) |
| B14 | NÃO RESOLVIDO | **RESOLVIDO com ressalva** | a espera total de retentativas é limitada a `EVOLUTION_ORCAMENTO_ESPERA_SEGUNDOS` (padrão 10 s). A thread do `BackgroundTasks` ainda pode ficar ocupada até esse teto somado aos timeouts HTTP (30 s por tentativa). Retentativa assíncrona ou fila segue como melhoria |
| A2 | PARCIAL | sem mudança nesta sprint | código já usa `False` como fallback em `conferente.py`; não alterado, conforme o plano |
| A5, M8 | PARCIAL | sem mudança nesta sprint | fora do plano |
| A1, A3, A4, A6, M1, M9 | NÃO RESOLVIDO no `main` | sem mudança nesta sprint | tratados pela integração (§12); não reverificados aqui |

**Contagem (29 achados, estado na branch):** RESOLVIDO **19** (M2, M3, M4, M5, M6, B1, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12, B13, B14); PARCIAL **4** (A2, A5, M7, M8); NÃO RESOLVIDO **6** (A1, A3, A4, A6, M1, M9, em aberto no `main` mas tratados pela integração, §12). Esses seis não estão contados como resolvidos porque esta sprint não os reverificou.

### 13.3 Verificação

| Verificação | Resultado |
|---|---|
| Suíte completa do backend, PostgreSQL 16 em container descartável novo (porta 55442) | **539 passed, 0 failed, 0 skipped**, 209 s |
| Teste de corrida `test_idempotency_key_em_corrida_grava_uma_unica_evidencia`, 3 execuções | 3 de 3 passam (119 s, 6 s, 10 s; a primeira execução concentra o setup do banco) |
| Migrações em banco novo (porta 55443), execução 1 | 34 aplicadas, exit 0 |
| Migrações em banco novo, execução 2 | 0 pendentes, exit 0 |
| Migração B12 com duplicatas de propósito (porta 55444) | sem duplicata: aplica. Com duplicata: **aborta, exit 1**, mensagem com obra e bitola. Após remover a duplicata: aplica, exit 0; repetição com 0 pendentes |
| `npm run build:css` (pwa) | exit 0 |
| `npm run test` (pwa) | exit 0, 8 testes |
| SSRF (CGNAT literal e por DNS), limite por obra, correlação, espera do WhatsApp | cobertos pelos testes acima; a revisão do diff foi feita por leitura |
| **Não verificado:** tela de conferência e instalação do PWA no navegador; dashboard rodando com NF perto da meia-noite | não executado nesta sprint (sem navegador e sem o dashboard no ar) |

### 13.4 Pendências

1. **Role da `DATABASE_URL` de produção (plano, passo 2):** pendente de resposta do usuário. Se for `postgres` com `BYPASSRLS`, o RLS não protege a API e isso bloqueia a afirmação de isolamento multiempresa. Nada foi alterado em produção.
2. **Bucket público de laudos:** ação operacional do usuário, fora da sprint.
3. **M7 no CI:** incluir `npm run test` e `npm run build:css` em `.github/workflows/testes.yml`.
4. **Ordem da migração `20261114120000_fila_reaper.sql`:** a aplicação em banco novo, na ordem pelo nome, passou. Em produção, validar antes de aplicar (§12.6).
5. **Revisão e merge do PR #3:** aguardando o usuário. Nada foi mesclado no `main`.
6. **Ícones do PWA:** trocar os PNGs provisórios pela arte da marca.
7. **Espera do primeiro teste de corrida** (119 s nesta sprint): observada, não explicada.
