# PROGRESS — SteelSPY 2.0

> Atualizado em 2026-11-05. Fonte de verdade do estado de execução contínua.

## Fase atual

**FASE C — Sprint 6: branch publicada, auditoria pós-push e preparação do piloto.**
A `feat/sprint3-operacional` está no GitHub com HEAD `c2cdfd2` (33 commits).
A auditoria do histórico completo encontrou **0 segredos reais** (71 commits,
39 fixtures sintéticas revisadas) e a branch está íntegra (`fsck` limpo, HEAD =
remoto). A suíte fechou em **592 testes de backend** (405 unitários + 187 de
integração, 1 skip de Storage local) e **35 de PWA**. Foi encontrada uma lacuna
real de autenticação no dashboard: sem `DASHBOARD_PASSWORD` ele abria sem login.
A correção local torna a senha obrigatória (≥ 12) e adiciona 6 testes; **ainda
não foi publicada**. O plano de deploy gratuito (Render Free + Supabase Free,
same-origin, HTTPS) está documentado, mas **nada foi publicado**. O piloto real
permanece **NO-GO** por validação física, backup, ambiente do dashboard e
decisão de NF-e/dados. Nenhum deploy, migration remota ou alteração de produção
foi executado.

## Concluído

| Fase | Entrega | Evidência |
|------|---------|-----------|
| Sprint 3 (A) | PWA, auth, pedidos, NF-e, conciliação, recebimento parcial, evidências, dossiê, RBAC/RLS | merge `7e76713` em `origin/main`; suíte 446 passed |
| VC-01 (C) | protótipo de contagem com recusa, laudo e avaliação | commit `d181779`; `docs/vc01/RELATORIO_VC01.md` — **NO-GO** para contagem automática |
| HML (B) | `backend/scripts/hml_staging.py`: diagnóstico read-only, semeadura HML idempotente e prova de isolamento com a role da aplicação | `stellspy_demo`: 12/12 PASS; reexecução sem duplicar |
| Oficial (B) | projeto Supabase confirmado (`sb-project-ref: akvbtceshpsvsuacueaq`) e declarado oficial | cabeçalho do gateway + decisão do proprietário (2026-11-03) |
| Oficial (B) | banco vazio → 30 migrations → role `stellspy_app` → prova RLS | PostgreSQL 16.15 e 17.11 locais: 30/30 aplicadas; HML 12/12 PASS nas duas versões |
| Oficial (B) | Storage privado de evidências (bucket `evidencias`, chave por tenant/obra) | `armazenamento.py` + migração M30; 18 testes unitários + teste real contra o Storage do Supabase local |
| Oficial (B) | diagnóstico read-only e trava do runner contra role operacional | `scripts/diagnostico_supabase.py`, `apply_migrations.validar_role_migracao` |
| Oficial (B) | `DATABASE_URL` da aplicação separada da URL administrativa | `backend/.env.example`, `docs/CHECKLIST_GOLIVE_SUPABASE.md` |
| Sprint 4 (B) | stack Supabase local (`supabase/config.toml`, portas 544xx) com as 30 migrações e bucket privado | PG 17.11; 20 tabelas com RLS + FORCE; `evidencias public=false` |
| Sprint 4 (B) | suíte de integração inteira contra o banco do Supabase local com a role operacional | **177 passed** (RLS multiempresa, auth/sessão/CSRF/RBAC, pedidos, NF-e, recebimento parcial, evidências, dossiê) |
| Sprint 4 (B) | suíte completa do backend | **476 passed** (inclui Storage real e E2E API → bucket privado → download) |
| Sprint 5 (prep) | contratos executáveis de dataset e métricas, sem modelo | `backend/exp_vc02/` + 21 testes; `docs/sprint5/PLANO_SPRINT5.md` |
| Sprint 5 (prep) | suíte completa após a preparação | **497 passed** (495 no CI + 2 marcados `supabase_local`) |
| Sprint 4 (B) | prova HML no Supabase local | diagnóstico + semeadura + **12/12 PASS** com `stellspy_app` |
| Sprint 4 (B) | compatibilidade do runner com admin não-superuser | M15 verifica atributos em vez de `ALTER ROLE` (no Supabase `postgres` tem BYPASSRLS, mas não é superuser) |
| Destravamento (B) | verificador de configuração sem expor segredos | `scripts/verificar_env_supabase.py`: 1 bloqueio (senha admin), 2 avisos; `.env` confirmado no `.gitignore` |
| Destravamento (B) | diagnóstico deixa de quebrar com URL-modelo | `problema_na_url_postgres` valida antes do parser; 17 testes do diagnóstico verdes |
| Destravamento (B) | identidade e serviços remotos confirmados (read-only) | `/auth/v1/settings`, `/rest/v1/` e `/storage/v1/bucket` → 200 com `sb-project-ref: akvbtceshpsvsuacueaq`; buckets remotos: `[]` |
| Destravamento (B) | rede do pooler e ausência da role operacional | DNS + TCP `aws-0-us-east-2.pooler.supabase.com:5432` OK; login `stellspy_app.<ref>` → `user not found in the database` |
| Destravamento (B) | configuração local corrigida | senha da role gerada com 43 caracteres; `DATABASE_URL` aponta para pooler real:5432; `EVIDENCIAS_STORAGE=supabase` |
| Destravamento (B) | schema remoto ainda vazio | PostgREST devolve `PGRST205` para `schema_migrations`, `construtoras`, `obras` e `evidencias`; as 30 migrations serão inicialização aditiva, não alteração de dados existentes |
| Destravamento (B) | configuração local aprovada | `verificar_env_supabase.py` → 0 bloqueios, 2 avisos; URL administrativa com senha percent-encoded |
| Destravamento (B) | projeto remoto identificado no diagnóstico | `akvbtceshpsvsuacueaq`, pooler `aws-0-us-east-2`, TCP OK; conexão parou em autenticação |
| Destravamento (B) | autenticação administrativa recusada | pooler de sessão (5432) e de transação (6543) devolvem `password authentication failed`; nenhuma escrita remota |
| Destravamento (B) | regravação segura da senha | `scripts/configurar_senha_admin.py` lê no prompt oculto, percent-encoda e testa a conexão; 3 testes |
| Destravamento (B) | validadores recusam senha sem codificação | `@`, `:`, `/`, `?`, `#`, `[`, `]` exigem percent-encoding; 26 testes dos helpers verdes |
| Validação local (B) | 30 migrations do zero em PostgreSQL 16.15 | suíte de integração **177 passed** (recria schema e aplica 30/30); suíte completa **511 passed, 2 skipped** |
| Validação local (B) | 30 migrations do zero em PostgreSQL 17.11 isolado | container descartável em 55433: `apply_migrations.py` → **30 aplicadas**; 30 versões únicas; role `stellspy_app` (`super=f bypassrls=f createrole=f createdb=f login=t`); 23 tabelas, 20 RLS + 20 FORCE + 20 políticas; `storage` ausente (M30 no-op) |
| Validação local (B) | isolamento RLS com a role operacional no PG 17 | sem `app.tenant_id`: 0 linhas; tenant A vê só A; tenant B vê só B; B não enxerga obra de A |
| Validação local (B) | Storage real contra o Supabase local | `pytest -m supabase_local` → **2 passed** (upload/leitura/duplicado/remoção + API → bucket privado → download) |
| Remoto (B) | configuração e conexão administrativa aprovadas | `verificar_env_supabase.py` → 0 bloqueios, 2 avisos; `diagnostico_supabase.py` conecta como `postgres.<ref>` ao projeto `akvbtceshpsvsuacueaq` (PG 17.11) |
| Remoto (B) | migrations aplicadas no projeto oficial | `apply_migrations.py --env-file .env` → **30 aplicadas** (0 → 30/30, 16:51 UTC); reexecução → **0 pendentes** |
| Remoto (B) | role operacional criada e utilizável | `stellspy_app` com `super=f bypassrls=f createrole=f createdb=f login=t`; login por `DATABASE_URL` OK; sem contexto de tenant vê 0 construtoras |
| Remoto (B) | RLS/FORCE/políticas no schema oficial | 23 tabelas em `public`, **20 com RLS + 20 FORCE + 20 políticas**; `tenant_sem_rls=[]` |
| Remoto (B) | HML com duas construtoras sintéticas | **12/12 PASS**: sem contexto 0 usuários; A vê só A; B vê só B; update/insert cruzados bloqueados; pedido e NF-e de A invisíveis para B |
| Remoto (B) | HML idempotente | segunda execução com o mesmo prefixo manteve os mesmos IDs, 3 usuários e 2 construtoras; **12/12 PASS** de novo |
| Remoto (B) | Storage oficial privado | bucket `evidencias` (`public=false`, 12 MiB); ciclo real upload/leitura/duplicado/remoção → **1 passed**; rota pública não entrega o objeto |
| Remoto (B) | E2E HTTP no banco oficial | login sintético → upload **201** → download normalizado e original **200**; bytes originais idênticos e SHA-256 normalizado/original conferem; cross-tenant **404** |
| Remoto (B) | suíte completa após as correções | **514 passed, 2 skipped** |
| Sprint 5 (op) | correções de integração PWA × API × banco | CSRF na conferência por chave, rotas alinhadas ao RBAC, rascunho de `id_cliente`, chave de idempotência por foto, cache v5, erros de rede claros |
| Sprint 5 (op) | fluxo completo obra → pedido → NF-e → recebimento → foto → conciliação → dossiê | `test_fluxo_completo_de_recebimento_ponta_a_ponta`: retry sem duplicar, binding tenant/obra/recebimento, hash no download, vizinho 404 |
| Sprint 5 (op) | dashboard deixa de reutilizar a credencial da API | `DASHBOARD_DATABASE_URL` + `diagnostico_conexao`; role `stellspy_app` sem contexto → 0 obras e mensagem explícita |
| Sprint 5 (op) | testes do contrato do PWA | Vitest **16 passed** (CSRF, erro de rede, `conferirNfe`, upload idempotente, chaves por arquivo) |
| Sprint 5 (op) | suíte backend após as correções | **517 passed, 2 deselected** (`supabase_local`), schema recriado + 30 migrations |
| Sprint 5 (op) | roteiro manual em celular real com câmera | `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md`; **execução física pendente** |
| Sprint 6 (1) | dashboard deixa de usar credencial de back-office | migration `20261104170000_dashboard_role.sql`: role `stellspy_dashboard` (`NOBYPASSRLS`, `NOINHERIT`, SELECT em 5 tabelas, `NOLOGIN` sem senha); `DASHBOARD_TENANT_ID` explícito |
| Sprint 6 (1) | isolamento por construtora provado em banco real | `test_dashboard_rls.py`: 8 testes (atributos, grants, A/B, sem contexto = 0, escrita negada, credencial admin recusada) |
| Sprint 6 (2) | operação do PWA com estado honesto | `pwa/js/operacoes.js` + faixa na tela (`pendente`/`confirmada`/`falhou`); 10 testes Vitest |
| Sprint 6 (2) | rascunho sobrevive a reload e a fechar o navegador | `pwa/js/rascunho.js`: localStorage por obra, TTL 4 h, tolerância de relógio; 9 testes Vitest |
| Sprint 6 (2) | idempotência de recebimento e foto já coberta | `uq_recebimentos_id_cliente`, `uq_evidencias_idempotencia`, `(recebimento_id, sha256)`; retry testado no E2E |
| Sprint 6 (3) | preparação de Android por ADB | `backend/scripts/preparar_android.py` + 9 testes; execução local: **ADB ausente (exit 2)** — nada aprovado |
| Sprint 6 (4) | dez passos do piloto em teste único | `test_piloto_percorre_os_dez_passos_ate_a_consulta_autorizada`: auth → obra → pedido → NF-e → recebimento parcial → foto/hash → divergência → decisão → PDF → auditoria sem escrita |
| Sprint 6 (5) | CORS com origens exatas e boot fail-fast | `app/cors.py` + 21 testes; `*`, `null`, caminho, query e credencial embutida são recusados |
| Sprint 6 (5) | CORS do piloto fechado, inclusive escrita | `.env` local com `localhost`/`127.0.0.1:8080`; preflight de `POST` e `DELETE` liberado; smoke com `Origin` no app real; auditoria `OK` |
| Sprint 6 (5) | auditoria de configuração e segredos | `scripts/auditar_publicacao.py`: `.env` local → **0 bloqueios, 5 avisos**; varredura do Git sem segredo real; 17 testes |
| Sprint 6 (5) | runbook, backup e GO/NO-GO documentados | `docs/sprint6/CHECKLIST_PUBLICACAO.md`, `DEPLOY_HOMOLOGACAO.md`, `PROCEDIMENTO_BACKUP_RESTAURACAO.md`, `RELATORIO_RISCOS.md` |
| Sprint 6 | suítes finais | backend **570 passed, 2 deselected** (180 s, 31 migrations); PWA **35 passed** (4 arquivos) |
| Pós-push (2026-11-05) | branch publicada e íntegra | `origin/feat/sprint3-operacional` = `c2cdfd2`; 33 commits em `bce0155..c2cdfd2`; `git fsck --full` exit 0 |
| Pós-push (2026-11-05) | histórico sem segredo real | `scripts/auditar_historico.py`: **0 bloqueios** nos 33 commits e em 71 do histórico; 31/39 sintéticos revisados; 8 testes do scanner |
| Pós-push (2026-11-05) | dashboard falha fechado sem senha | `dashboard/auth.py`: `DASHBOARD_PASSWORD` obrigatória (≥ 12), comparação em tempo constante; 6 testes; **correção local, não publicada** |
| Pós-push (2026-11-05) | CORS confirmado | 21 testes; `*`, `null`, caminho, query, credencial embutida e porta inválida recusados; same-origin dispensa CORS |
| Pós-push (2026-11-05) | suítes completas | backend **592 passed** (405 + 187 integração), 1 skip de Storage local; PWA **35 passed** |
| Pós-push (2026-11-05) | plano de deploy gratuito | `docs/sprint6/PLANO_DEPLOY_GRATUITO.md`: Render Free same-origin + Supabase Free, HTTPS, R$ 0,00; **nada executado** |
| Pós-push (2026-11-05) | GO/NO-GO revisado | `docs/sprint6/RELATORIO_AUDITORIA_POS_PUSH.md`: **NO-GO** para piloto real; 13 portões com estado |

## Pendente

- Instalar `platform-tools`/ADB e executar o roteiro manual em celular real
  (`docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md`): login, recebimento parcial,
  retry sem duplicar, câmera, upload com queda de rede, recarga/fechamento do
  navegador, papéis e isolamento. `preparar_android.py` falhou aqui com exit 2
  (ADB ausente); Android via `adb reverse` tem caminho de custo zero; iPhone
  exige HTTPS.
- Aplicar a migration 31 no projeto oficial com `STELLSPY_DASHBOARD_PASSWORD` e
  configurar `DASHBOARD_DATABASE_URL` + `DASHBOARD_TENANT_ID` +
  `DASHBOARD_PASSWORD` onde o dashboard for publicado. A role da aplicação
  continua sem `BYPASSRLS`.
- Publicar a correção local de autenticação do dashboard: no HEAD `c2cdfd2`,
  `DASHBOARD_PASSWORD` vazia fazia o painel abrir sem login.
- Definir `CORS_ALLOW_ORIGINS` de produção **apenas se** o PWA ficar em outra
  origem; no deploy same-origin planejado, a lista fica vazia (21 testes).
- Executar o deploy gratuito de `docs/sprint6/PLANO_DEPLOY_GRATUITO.md` somente
  após autorização: Render Free (API + PWA na mesma origem), Supabase Free,
  HTTPS, sem cartão e sem custo adicional.
- Ensaiar backup e restauração em banco descartável
  (`docs/sprint6/PROCEDIMENTO_BACKUP_RESTAURACAO.md`) antes do GO.
- Revisar os 4 avisos da auditoria de publicação (`NFE_IO_MOCK=1`,
  `SUPABASE_DB_ADMIN_URL` no `.env`, dashboard não configurado,
  `service_role` presente) e transformar em decisão registrada.
- Decidir o destino dos dados sintéticos HML no projeto oficial: permanecem duas
  construtoras `hml-*`, 3 usuários e uma evidência. A limpeza automática pode ser
  bloqueada pela FK de evidências; qualquer remoção exige autorização explícita.
- Rotacionar a senha administrativa usada no destravamento, por higiene, depois
  de concluída a janela de homologação.
- Sprint 5: coletar e anonimizar fotografias do recebimento real; depois anotar,
  treinar e avaliar — nenhum modelo entra no produto sem os portões de
  `exp_vc02` (métricas + validação humana).
- Fases D (inteligência de auditoria), E (documental), F (offline), G (comercial).

## Bloqueios

| Bloqueio | O que falta |
|----------|-------------|
| Deploy | fora de escopo por instrução; branch publicada, mas nada foi publicado em ambiente |
| PWA em aparelho real | câmera e fluxo de campo não exercitados; ADB ausente nesta máquina |
| Backup | procedimento escrito, nenhum dump/restore executado antes do GO |
| Dashboard | migration 31 não aplicada no oficial; `DASHBOARD_PASSWORD` ainda opcional no HEAD publicado |
| Publicação | `CORS_ALLOW_ORIGINS` de produção (se PWA separado), `DASHBOARD_*` e `NFE_IO_MOCK=0` ainda não definidos |
| Piloto real | validação física, backup, ambiente do dashboard e decisão de NF-e/dados abertos — **NO-GO** |
| VC-01 em campo | fotografias do cenário real de recebimento e GPU (RTX 4070 não presente nesta máquina) |
| Sprint 5 dados | ≥ 60 obras / ≥ 600 fotos rotuladas; sem isso, não há métrica honesta |

## Último commit de entrega

A branch `feat/sprint3-operacional` foi publicada em 2026-11-04 com **33
commits** (`bce0155..c2cdfd2`), HEAD `c2cdfd2` — dashboard com role de leitura,
PWA com rascunho/estado, preparação Android, teste dos dez passos, CORS/auditoria
e correção do CORS local. A auditoria pós-push de 2026-11-05 gera um commit
**local** com a correção de autenticação do dashboard, o scanner de histórico,
testes e documentos; ele **não foi enviado** ao remoto. Detalhe em
`docs/sprint6/RELATORIO_AUDITORIA_POS_PUSH.md` §10.

## Próxima ação automática

1. Autorizar a publicação do commit local da auditoria (dashboard fail-closed,
   scanner de histórico, testes e documentos). Nada foi enviado.
2. Ensaiar backup/restauração em banco descartável antes do GO.
3. Instalar ADB e executar o roteiro manual em celular real, anexando capturas —
   câmera e retry com queda de rede são os pontos que nenhum teste automatizado
   cobre. Android: `adb reverse` + `http://localhost:8080`; iPhone: HTTPS.
4. Definir o modo NF-e (`NFE_IO_MOCK=0` com token ou fluxo manual aceito) e
   decidir o destino dos dados HML sintéticos.
5. Aplicar a migration 31 no projeto oficial e configurar o dashboard com
   `DASHBOARD_PASSWORD` obrigatória.
6. Autorizar e executar o deploy de `docs/sprint6/PLANO_DEPLOY_GRATUITO.md`;
   smoke test com dados sintéticos.
7. Sprint 5: coletar e anonimizar fotografias reais; nenhum modelo entra no
   produto sem os portões de `exp_vc02`.

Nenhuma operação destrutiva, push ou deploy é autorizada sem pedido explícito.
