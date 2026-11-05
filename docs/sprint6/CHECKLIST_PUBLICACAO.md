# Checklist de publicação — piloto SteelSPY

**Estado:** preparado em 2026-11-04, revisado após o push em 2026-11-05.
A branch `feat/sprint3-operacional` está publicada no GitHub com HEAD
`c2cdfd2`; **nada deste checklist de deploy foi executado**: não houve deploy,
migration remota nem alteração de dados. Ele descreve a ordem segura para quando
o proprietário autorizar.

Auditoria de apoio: [`RELATORIO_AUDITORIA_POS_PUSH.md`](RELATORIO_AUDITORIA_POS_PUSH.md)
· Plano de deploy: [`PLANO_DEPLOY_GRATUITO.md`](PLANO_DEPLOY_GRATUITO.md).

**Contrato mínimo:** API FastAPI + PostgreSQL (Supabase oficial
`akvbtceshpsvsuacueaq`), PWA estático em HTTPS, dashboard Streamlit opcional.
Orçamento adicional R$ 0,00 — usa apenas a infraestrutura já contratada.

---

## 1. Portões antes de publicar

| # | Portão | Como verificar | Evidência esperada |
|---|--------|----------------|--------------------|
| 1 | Suíte backend verde | `cd backend && ..\.venv\Scripts\python.exe -m pytest -q -m "not supabase_local"` | 0 falhas; schema recriado com **31 migrations** |
| 2 | Suíte PWA verde | `cd pwa && npm test` | 0 falhas |
| 3 | Auditoria de configuração | `cd backend && ..\.venv\Scripts\python.exe scripts\auditar_publicacao.py` | **0 bloqueios**; avisos revisados item a item |
| 4 | CORS com origens exatas | `CORS_ALLOW_ORIGINS` preenchido, sem `*`, sem caminho, sem `null` | Piloto local: 2 origens (`localhost` e `127.0.0.1:8080`); preflight de `POST` e `DELETE` liberado; auditoria `OK` |
| 5 | Credencial da API é operacional | usuário da `DATABASE_URL` = `stellspy_app.<ref>` | auditoria: `DATABASE_URL OK` |
| 6 | Dashboard com menor privilégio | `DASHBOARD_DATABASE_URL` = role `stellspy_dashboard`; `DASHBOARD_TENANT_ID` = UUID da construtora do piloto; `DASHBOARD_PASSWORD` definida (≥ 12) | `test_dashboard_rls.py` + `test_dashboard_auth.py` + auditoria sem bloqueio |
| 7 | Segredo de sessão forte | `PWA_SESSION_SECRET` ≥ 32 caracteres, fora do Git | auditoria: `OK` |
| 8 | Cookie coerente com HTTPS | `PWA_COOKIE_SECURE=1`; `SameSite=None` só se PWA e API estiverem em domínios diferentes | auditoria: `OK` |
| 9 | Nenhum segredo versionado | `cd backend && ..\.venv\Scripts\python.exe scripts\auditar_historico.py --range=--all` | **0 bloqueios** em 71 commits; 39 sintéticos revisados |
| 10 | PWA sem configuração de teste | `pwa/index.html` com `"apiBaseUrl": ""` | commit limpo |
| 11 | Backup verificável | `PROCEDIMENTO_BACKUP_RESTAURACAO.md` executado em ensaio | hash, tamanho e contagem de linhas registrados |
| 12 | Validação física registrada | `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md` com capturas | **pendente enquanto não houver execução real** |
| 13 | Branch publicada íntegra | `git rev-parse HEAD` = `git ls-remote origin …`; `git fsck --full` | `c2cdfd2` nos dois; fsck exit 0; 33 commits |
| 14 | Autenticação do dashboard | `DASHBOARD_PASSWORD` obrigatória (≥ 12) | correção local + `test_dashboard_auth.py`; **ausente no HEAD `c2cdfd2`** |

---

## 2. Variáveis por processo

O mesmo `.env` local serve ao desenvolvimento; em produção cada processo recebe
**somente** o que precisa.

### API (processo da aplicação)

| Variável | Obrigatória | Observação |
|----------|-------------|------------|
| `DATABASE_URL` | sim | role `stellspy_app.<ref>`, pooler sessão 5432, sujeita a RLS |
| `PWA_SESSION_SECRET` | sim | ≥ 32 caracteres |
| `PWA_COOKIE_SECURE` | sim | `1` em HTTPS |
| `CORS_ALLOW_ORIGINS` | sim, se o PWA estiver em outra origem | lista exata; piloto local = `http://localhost:8080,http://127.0.0.1:8080` |
| `EVIDENCIAS_STORAGE` | sim | `supabase` no piloto remoto |
| `EVIDENCIAS_BUCKET` | com Storage | bucket privado `evidencias` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | com Storage | **somente servidor**; nunca no PWA |
| `SKIP_API_KEY` | sim | sempre `0` |
| `NFE_IO_TOKEN` / `NFE_IO_MOCK` | conforme integração | `NFE_IO_MOCK=1` só em ensaio, nunca no piloto real |

**Nunca** no processo da API: `SUPABASE_DB_ADMIN_URL`, `STELLSPY_APP_PASSWORD`,
`STELLSPY_DASHBOARD_PASSWORD`, `DASHBOARD_DATABASE_URL`.

### Executor de migrations (execução pontual)

- `SUPABASE_DB_ADMIN_URL` (`postgres.<ref>`, pooler sessão).
- `STELLSPY_APP_PASSWORD` (≥ 12) e, para a role do dashboard,
  `STELLSPY_DASHBOARD_PASSWORD` (≥ 12).
- O runner recusa rodar como `stellspy_app` ou `stellspy_dashboard`.

### Dashboard Streamlit

- `DASHBOARD_DATABASE_URL` (role `stellspy_dashboard`, só leitura).
- `DASHBOARD_TENANT_ID` (UUID da construtora).
- `DASHBOARD_PASSWORD` (obrigatória, ≥ 12, dedicada; sem ela o painel não abre).
- `PYTHONPATH=backend`.

### PWA

- Arquivo estático em HTTPS. O único ajuste é `apiBaseUrl` no `index.html`,
  preenchido no artefato publicado — **não** no commit.

---

## 3. Ordem de publicação (não executada)

1. Congelar escrita nova; avisar o piloto.
2. Executar o ensaio de backup e registrar hash/tamanho.
3. Aplicar as migrations com o runner administrativo:
   `python scripts/apply_migrations.py --env-file .env`.
   A nova migration cria a role `stellspy_dashboard` como `NOLOGIN` se
   `STELLSPY_DASHBOARD_PASSWORD` não for fornecida — falha fechada.
4. Provar a role do dashboard:
   `python scripts/diagnostico_supabase.py` e um `SELECT` no tenant do piloto.
   Sem `BYPASSRLS`, sem escrita, sem acesso a outros tenants.
5. Publicar a API com as variáveis da seção 2.
6. Publicar o PWA em HTTPS com `apiBaseUrl` apontando para a API.
7. Publicar o dashboard (se autorizado) em URL interna/protegida.
8. Smoke test: `/health`, login de cada papel, `/auth/obras`, uma consulta de
   pedido, um recebimento **em dado sintético**, download de foto e dossiê.
9. Observar 30 minutos: 5xx, 401/403 inesperados, 503 de banco, erros de CORS.

---

## 4. GO / NO-GO

| Critério | GO | NO-GO | Estado em 2026-11-05 |
|----------|----|-------|----------------------|
| Auditoria de publicação | 0 bloqueios | qualquer bloqueio | **GO** — 0 bloqueios, 4 avisos revisados |
| Histórico Git | 0 segredo real | `.env`, token ou senha real | **GO** — 0 bloqueios em 71 commits |
| Testes | backend e PWA verdes | falha ou teste pulado sem justificativa | **GO** — 592 backend + 35 PWA; 1 skip de Storage local |
| Integridade da branch | HEAD = remoto, fsck limpo | divergência ou corrupção | **GO** — `c2cdfd2`, 33 commits |
| Validação física | roteiro executado com capturas | sem execução real | **NO-GO** |
| Backup | ensaio de restauração concluído | sem ensaio ou sem hash | **NO-GO** |
| CORS | origens exatas, HTTPS | vazio (se PWA separado), `*`, HTTP em produção | **GO** same-origin; **NO-GO** se separar sem origem HTTPS exata |
| Credenciais | app e dashboard separadas, menor privilégio | admin/owner na aplicação | **GO** |
| Autenticação do dashboard | senha obrigatória ≥ 12 | painel abre sem senha | **NO-GO no `c2cdfd2`**; correção local pronta |
| Dados | construtora/obra sintética ou autorizada | dado real sem autorização escrita | **NO-GO** até decisão |
| Reversão | commit anterior identificado e backup disponível | sem caminho de volta | **GO parcial** — commit identificado; backup pendente |

**Critério de parada:** qualquer item NO-GO interrompe a publicação. Não existe
"publicar e corrigir depois" para isolamento, credencial ou backup.

**Veredito atual:** **NO-GO para piloto real**; o código está limpo em segredos e
verde, mas faltam validação física, backup, autenticação do dashboard publicada,
ambiente oficial e decisão de NF-e/dados.

---

## 5. Reversão

1. Republicar o artefato do commit anterior (API e PWA).
2. Não reverter migrations por `DROP`: a trilha é aditiva. Se uma migration
   causar erro, publicar uma correção para a frente.
3. Se houver corrupção de dados, restaurar do backup conforme
   `PROCEDIMENTO_BACKUP_RESTAURACAO.md` — com autorização explícita.
4. Registrar hora, commit, sintoma e ação no relatório do piloto.
