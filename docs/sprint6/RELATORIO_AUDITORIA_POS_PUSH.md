# Auditoria pós-push e preparação do piloto

**Data:** 2026-11-05
**Branch auditada:** `feat/sprint3-operacional`
**Correção publicada em:** `0f5579b` (autenticação do dashboard e migration 31);
a auditoria original cobriu `c2cdfd266e8db61d19de343ac46cda7e7cf0618e`
**Remoto:** `origin` = `https://github.com/nocodenn-cell/SteelSPY`
**Escopo:** 38 commits publicados (`bce0155..0f5579b`), histórico completo,
dashboard, CORS, suítes de teste e plano de deploy gratuito.
**Restrições cumpridas:** nenhum deploy, nenhuma operação destrutiva, nenhum
segredo reproduzido. A migration 31 foi aplicada com autorização específica em
2026-11-05.

---

## 1. Veredito

| Dimensão | Resultado |
|----------|-----------|
| Credenciais no histórico publicado | **Limpo** — 0 bloqueios |
| `service_role` / credencial administrativa exposta | **Não** |
| Arquivos `.env` versionados | **Nenhum** |
| CORS | **Fechado por origem exata**; 21 testes |
| Menor privilégio do dashboard no banco | **Comprovado** (role só leitura, RLS, 8 testes) e **aplicado no projeto oficial** em 2026-11-05 |
| Autenticação do dashboard | **Lacuna encontrada, corrigida e publicada** em `0f5579b`; senha obrigatória (≥ 12) |
| Ambiente do dashboard | **Configurado e validado** no banco oficial (role com login, tenant HML Alfa, senha de 32 chars, boot headless) |
| Suítes | **593 backend + 35 PWA verdes** (após a migration 31) |
| Integridade da branch | **OK** — HEAD local = remoto, `git fsck` limpo |
| Prontidão para piloto real | **NO-GO** pelos portões operacionais listados em §8 |

**Não há indício de credencial exposta.** Não é necessário acionar contenção ou
rotação de emergência. A única credencial administrativa mencionada está no
`.env` local, ignorado pelo Git, e a auditoria a sinaliza como aviso de higiene.

---

## 2. Integridade da branch publicada

| Evidência | Comando | Resultado |
|-----------|---------|-----------|
| HEAD local = remoto | `git rev-parse HEAD origin/feat/sprint3-operacional` | iguais após o push de `0f5579b` |
| Commits no intervalo | `git log --oneline bce0155..HEAD \| wc -l` | **38** |
| Objetos íntegros | `git fsck --full` | exit 0, nenhuma corrupção |
| Árvore publicada | `git status --short` | limpa |
| `main` | branch separada | não foi tocada |

Os 33 commits originais vão de `d181779` (protótipo VC-01) a `c2cdfd2`
(registro da correção de CORS). Em 2026-11-05, o push `c2cdfd2..0f5579b`
publicou **5** commits: correção de autenticação do dashboard, scanner de
histórico, marcação de fixture, migration 31/auditoria e bookkeeping. A lista
completa está em §10.

---

## 3. Auditoria de segredos no histórico

### Método

Foi criado `backend/scripts/auditar_historico.py`, somente leitura, que percorre
as **linhas adicionadas** por cada commit (não só a árvore atual) e as
mensagens de commit. Ele procura:

- arquivos `.env` (exceto `.env.example`);
- URLs PostgreSQL com usuário e senha;
- blocos de chave privada PEM;
- JWT com papel `service_role` ou `anon`;
- atribuições de variáveis sensíveis (`DATABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`, `PWA_SESSION_SECRET`, `NFE_IO_TOKEN`, etc.);
- prefixos de token conhecidos (`ghp_`, `github_pat_`, `xox*`, `AKIA`, `sk-`,
  `AIza`).

A saída **mascara** o segredo e classifica cada achado como `BLOQUEADO` ou
`SINTÉTICO`. Fixtures de teste e modelos de documentação (`[SENHA]`, `<host>`,
f-strings) só são aceitos quando o valor é comprovadamente fictício.

### Resultado

| Varredura | Commits | Linhas adicionadas | Bloqueios | Sintéticos |
|-----------|---------|--------------------|-----------|------------|
| 33 commits publicados (`bce0155..c2cdfd2`) | 33 | 10.688 | **0** | 31 |
| Histórico completo (`--all`) | 71 | 78.828 | **0** | 39 |
| Após os dois commits locais desta auditoria | 35 no intervalo / 73 no total | 11.998 / 80.138 | **0** | 37 / 45 |
| Após o push `0f5579b` (histórico completo) | 76 | 80.246 | **0** | 46 |

Os 46 achados sintéticos são:

- fixtures em `backend/tests/*` com senhas fictícias (`s3cr3t`, `segredo`,
  `antiga`, `%40` etc.) ou marcadas com `# credencial-de-exemplo`;
- modelos em `backend/.env.example` e `docs/` (`[SENHA_APP]`, `<região>`,
  `<HOST_POOLER>`, `[REF]`);
- f-strings de teste (ex.: `f"{OWNER}:{SENHA}@{HOST}/{banco}"`), que não contêm
  valor literal;
- um comando de docstring antigo com `user:senha@host:porta/banco`.

Nenhum valor real foi impresso pela ferramenta. O próprio scanner é coberto por
8 testes em `backend/tests/test_auditar_historico.py`, incluindo um repositório
git descartável com `.env`, JWT `service_role`, URL com senha e mensagem de
commit — e a asserção de que a saída não reproduz o segredo.

### Verificações complementares

| Verificação | Resultado |
|-------------|-----------|
| `.env` em qualquer commit do histórico | **Nenhum** |
| Arquivos versionados com nome sensível | Apenas `backend/.env.example` (placeholders) |
| `SUPABASE_SERVICE_ROLE_KEY` no código | Somente `os.getenv(...)`/nome da variável; **nenhum valor** |
| JWT com papel `service_role`/`anon` literal | **Nenhum**; scanner classificaria como bloqueio |
| Chave privada PEM | **Nenhuma** |
| Token com prefixo conhecido | **Nenhum** |
| URL administrativa `postgres.<ref>` em código/docs | Apenas modelos e instruções; nenhum valor real |
| Segredo real em mensagem de commit | **Nenhum** |

**Conclusão:** o histórico publicado está limpo. Não há credencial
administrativa nem `service_role` exposta.

---

## 4. Permissões do dashboard (menor privilégio)

### Banco

A migration `20261104170000_dashboard_role.sql` cria `stellspy_dashboard` com:

- `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`;
- `SELECT` apenas em `construtoras`, `obras`, `nfe_logs`, `nfe_itens` e
  `especificacoes`;
- nenhum `INSERT`/`UPDATE`/`DELETE`, nenhum grant em sequências e nenhum
  `ALTER DEFAULT PRIVILEGES`;
- `LOGIN` somente quando `STELLSPY_DASHBOARD_PASSWORD` (≥ 12) é fornecida ao
  runner; sem ela, a role nasce `NOLOGIN` (falha fechada).

O painel abre a transação com `set_config('app.tenant_id', ..., true)` e
`DASHBOARD_TENANT_ID`; sem tenant, o RLS devolve zero linhas. Os 8 testes de
`backend/tests/integration/test_dashboard_rls.py` provam, em PostgreSQL real:
atributos da role, grants, ausência de contexto = 0 obras, tenant A × B,
escrita negada e recusa de credencial de back-office.

**Aplicado no projeto oficial em 2026-11-05:** migration 31 aplicada pelo runner
(`31/31`), role com `super=f bypassrls=f inherit=f createdb=f createrole=f
login=t`, SELECT apenas nas 5 tabelas, 0 UPDATE e 0 default privileges. Com o
pooler, o usuário é `stellspy_dashboard.<ref>`; a auditoria foi corrigida para
aceitar esse formato (antes exigia o nome exato e bloqueava a configuração
válida). Provas no banco remoto: Alfa vê 1 obra e a própria construtora, Beta vê
1 obra distinta, sem contexto 0, `INSERT` em `obras` e `SELECT` em `pedidos`
negados.

### Autenticação — lacuna encontrada

No HEAD publicado (`c2cdfd2`), `dashboard/app.py::_check_password` fazia:

```python
pwd = os.getenv("DASHBOARD_PASSWORD", "").strip()
if not pwd:
    return True          # painel abre sem login
```

Isso é aceitável apenas em máquina local isolada. Se o dashboard fosse exposto
à internet nesse estado, qualquer pessoa com a URL leria os dados do tenant.

**Correção publicada em `0f5579b`:**

- novo módulo `dashboard/auth.py`, sem dependência de Streamlit;
- `DASHBOARD_PASSWORD` passa a ser **obrigatória**, com mínimo de **12**
  caracteres e valor dedicado (não reutiliza a senha da role do banco nem a da
  API);
- senha ausente/curta → painel exibe erro e **não renderiza dados**;
- comparação em tempo constante (`hmac.compare_digest` sobre digests SHA-256);
- 6 testes em `backend/tests/test_dashboard_auth.py`, incluindo a garantia de
  que a mensagem de recusa não reproduz o valor.

**Risco residual:** a lacuna de autenticação está fechada no HEAD publicado
(`0f5579b`), que exige senha de 12+ caracteres. A senha compartilhada também não
é MFA; para exposição pública, prefira VPN/proxy autenticado e avalie rate
limiting.

---

## 5. CORS

`backend/app/cors.py` valida a lista no boot e **derruba o processo** se houver
configuração ambígua. São recusados:

- `*` (incompatível com `allow_credentials=True`);
- `null`;
- esquema diferente de `http`/`https`;
- origem sem host, com usuário/senha embutidos, com caminho, query ou fragmento;
- porta inválida.

Configuração aplicada quando há origens:

- `allow_origins` = lista exata, normalizada (sem duplicatas);
- `allow_credentials=True`;
- métodos `GET`, `POST`, `DELETE`, `OPTIONS` (o `DELETE` desfaz correlação no PWA);
- headers `Content-Type`, `X-CSRF-Token`, `X-API-KEY`;
- headers expostos `X-Conteudo-Sha256`, `X-Dossie-Id`, `Content-Disposition`;
- `max_age=600`.

Evidência: **21 testes** em `backend/tests/test_cors.py` (origem permitida com
credenciais, preflight de `POST` e `DELETE`, origem não autorizada, config
vazia, headers expostos, wildcard derrubando o boot) e smoke anterior no app
real com `Origin` local. O `.env.example` publicado deixa
`CORS_ALLOW_ORIGINS` vazio: isso é **seguro** para o deploy same-origin, mas
exige a origem HTTPS exata se o PWA for separado da API.

---

## 6. Testes e integridade

| Suíte | Comando | Resultado |
|-------|---------|-----------|
| Backend (sem integração) | `pytest -q -m "not supabase_local"` | **406 passed, 187 skipped, 2 deselected** |
| Integração (PostgreSQL real + 31 migrations) | `pytest tests/integration -q` | **187 passed, 1 skipped** |
| Total backend | `pytest tests -q` | **593 passed, 2 skipped**; os skips são os testes de Storage do Supabase local |
| PWA | `npm test` | **35 passed** (4 arquivos) |
| Foco desta auditoria | dashboard auth + CORS + publicação + histórico | **59 passed** |

O PostgreSQL de teste foi iniciado localmente (`stellspy-pg`, porta 55432) para
a suíte de integração; nenhum banco remoto foi tocado. O schema foi recriado
pelas 31 migrations.

Observação: `git fsck --full` exit 0; HEAD local e remoto idênticos antes das
mudanças desta auditoria.

---

## 7. Plano de deploy gratuito

Documento completo: [`PLANO_DEPLOY_GRATUITO.md`](PLANO_DEPLOY_GRATUITO.md).

Resumo:

- **um** Web Service Free no Render servindo FastAPI **e** o PWA na mesma origem
  HTTPS (`onrender.com`);
- Supabase Free oficial (`akvbtceshpsvsuacueaq`, role `stellspy_app`) para banco e
  Storage;
- dashboard **não** publicado no piloto (local/VPN);
- mudança de código necessária antes: montar `pwa/` com `StaticFiles` e servir
  `sw.js` sem cache;
- limites conferidos: Render 750 h/mês, dorme após 15 min, 0,1 CPU/512 MB, sem
  cartão; Supabase 500 MB de banco, 1 GB de Storage, 5 GB de egress, pausa após
  7 dias de baixa atividade;
- keep-alive é opcional e consome quase toda a franquia; cold start de ~1 min é
  o principal custo operacional;
- **nada foi criado ou publicado**.

---

## 8. GO / NO-GO para piloto real

| # | Critério | Estado em 2026-11-05 | Decisão |
|---|----------|----------------------|---------|
| 1 | Histórico sem segredo real | 0 bloqueios em 76 commits | **GO** |
| 2 | Integridade da branch | HEAD = remoto (`0f5579b`), 38 commits, fsck limpo | **GO** |
| 3 | Suítes backend/PWA | 593 + 35 verdes (após a migration 31) | **GO** |
| 4 | CORS local/same-origin | exato, 21 testes, sem wildcard | **GO** |
| 5 | CORS de produção (se PWA separado) | origem HTTPS ainda não definida | **NO-GO** até definir |
| 6 | Dashboard — banco | role de leitura, RLS, 8 testes + prova no projeto oficial | **GO** |
| 7 | Dashboard — autenticação | correção publicada em `0f5579b`; senha obrigatória ≥ 12, 6 testes e boot headless | **GO** |
| 8 | Dashboard — ambiente oficial | migration 31 aplicada (31/31); role com login, tenant HML Alfa e senha de 32 chars; boot headless OK | **GO local**; falta host publicado |
| 9 | Validação física (câmera/rede) | roteiro não executado; ADB ausente | **NO-GO** |
| 10 | Backup/restauração | procedimento escrito, nenhum ensaio | **NO-GO** |
| 11 | NF-e real | `NFE_IO_MOCK=1` no `.env` local | **NO-GO** até `NFE_IO_MOCK=0` ou fluxo manual aceito |
| 12 | Deploy | plano pronto, nada executado (por instrução) | **N/A** |
| 13 | Dados do piloto | construtora/obra sintética ou autorizada | **NO-GO** até decisão escrita |
| 14 | Reversão | commit anterior identificável; backup pendente | **GO parcial** |

**Veredito:** **NO-GO para um piloto real hoje.** O código publicado está limpo
em segredos e verde em testes, e o dashboard já tem banco e ambiente validados.
Faltam os portões operacionais 7 e 9–11 e 13. O avanço seguro é: publicar a
correção de autenticação do dashboard, executar backup/restauração, validar em
aparelho real, decidir NF-e e só então autorizar o deploy descrito em
`PLANO_DEPLOY_GRATUITO.md`.

---

## 9. Riscos e próximos passos

| Risco | Gravidade | Mitigação |
|-------|-----------|-----------|
| Dashboard do `c2cdfd2` autenticava sem senha | **Fechado** | correção publicada em `0f5579b`; não implantar o commit anterior |
| Cold start de ~1 min no Render Free | Média | abrir antes do uso ou keep-alive aprovado |
| Supabase pausa após 7 dias ocioso | Média | uso diário ou retomada manual registrada |
| 500 MB de banco / 1 GB de Storage / 5 GB de egress | Média | monitorar volume de fotos e dossiês |
| Sem backup automático no Free | **Alta** | dump manual antes do piloto e periódico |
| Sem rate limiting no login do dashboard | Média | VPN/proxy autenticado; senha longa e dedicada |
| TLS até o banco não é forçado pelo app | Baixa | usar `?sslmode=require` na `DATABASE_URL` de produção |
| Scanner de segredos é heurístico | Baixa | não substitui cofre/revisão humana |
| Senha administrativa do Supabase ainda é a do destravamento | Baixa | rotacionar após a homologação |
| Dados HML sintéticos no projeto oficial | Baixa | decisão do proprietário; remoção exige autorização |

**Próximos passos, em ordem:**

1. ~~Publicar a correção de autenticação~~ — feito em 2026-11-05
   (`c2cdfd2..0f5579b`).
2. Autorizar e executar o ensaio de backup/restauração em banco descartável.
3. Executar o roteiro mobile em Android real (câmera, retry, recarga, papéis).
4. Decidir o modo NF-e do piloto (`NFE_IO_MOCK=0` + token ou fluxo manual).
5. Trocar `DASHBOARD_TENANT_ID` (hoje HML Alfa) pelo tenant da construtora do
   piloto e repetir o diagnóstico no host publicado.
6. Autorizar o deploy seguindo `PLANO_DEPLOY_GRATUITO.md`; smoke test sintético.
7. Registrar URL, commit, horário, backup e resultados no relatório do piloto.

---

## 10. Commits publicados

Intervalo `bce0155..c2cdfd2` (33 commits, ordem cronológica):

```
d181779 feat(vc01): protótipo de contagem de vergalhões com recusa e avaliação
6c2476e feat(hml): ferramenta de homologação com dados sintéticos e prova de isolamento
1fbf8d2 feat(supabase): storage privado, diagnóstico e bootstrap do projeto oficial
9ea5292 fix(supabase): role idempotente para admin nao-superuser e Storage homologado
4d14300 docs(progress): homologacao local da Sprint 4 no Supabase
37727b7 test(storage): E2E real da API com o bucket privado do Supabase
ad22f31 feat(vc02): contratos de dataset e metricas para a Sprint 5
99fe5f9 docs(progress): registra o commit da preparacao da Sprint 5
e7f76c1 docs(progress): separa entrega de bookkeeping no registro de commit
33b7e44 test(ci): marca testes do Supabase local e exclui no CI
a73106d docs(progress): registra o commit da exclusao explicita no CI
6263fb0 fix(diagnostico): valida URL-modelo e verifica env sem expor segredos
c44b116 docs(progress): registra o commit do destravamento
7ebfc2f docs(progress): registra schema remoto vazio e bloqueio unico
b6527e9 feat(migrations): le .env e recusa URL-modelo antes de conectar
35a5ca3 fix(config): exige percent-encoding na senha e grava sem expor
09d784b docs(progress): registra autenticacao administrativa recusada
36680f6 docs(progress): registra revalidacao local das 30 migrations
684fa06 fix(diagnostico): lista migrations pendentes sem schema_migrations
ef0fe4c fix(hml): compara migrations pelo nome completo e filtra RLS por tenant
4cbc47b docs(progress): homologa o Supabase oficial e registra evidencias remotas
45a190c fix(pwa): falha de rede nao duplica recebimento nem evidencia
8e6f803 fix(dashboard): exige credencial de back-office em vez de afrouxar RLS
392cf19 test(e2e): cobre recebimento completo ate o dossie em PDF
c920931 docs(sprint5): registra operacao de campo, roteiro mobile e testes
be28e00 fix(dashboard): usa role de leitura presa ao tenant em vez de credencial admin
772d1ff feat(pwa): preserva rascunho e expõe estado real de cada envio
78c92fb feat(mobile): prepara execucao Android por ADB com falha explicita
5127fe8 test(piloto): cobre os dez passos ate a consulta do responsavel
70745e3 feat(publicacao): valida CORS exato e audita segredos versionados
811d013 docs(progress): registra hashes da Sprint 6
fd52e0a fix(cors): libera DELETE do PWA e fecha as origens do piloto local
c2cdfd2 docs(progress): registra correcao do CORS do piloto
```

**Commits publicados em 2026-11-05 (`c2cdfd2..0f5579b`):**

- `6bf1c01` — `fix(dashboard): exige senha no painel e audita o historico publicado`
- `5b68c85` — `test(publicacao): marca fixture do scanner como exemplo sintetico`
- `5bc7d15` — `docs(progress): registra hashes da auditoria pos-push`
- `be4c1c8` — `feat(dashboard): aplica a migration 31 e valida a role de leitura`
- `0f5579b` — `docs(progress): registra o commit da migration 31`

O push `c2cdfd2..0f5579b` foi autorizado explicitamente pelo proprietário;
nenhum PR, merge ou tag foi criado. Commits de bookkeeping posteriores não
alteram a entrega registrada em `0f5579b`.

---

## 11. O que não foi feito

- Nenhum PR, merge ou tag.
- Nenhum deploy, conta em provedor, domínio ou certificado.
- Nenhuma operação destrutiva, `DROP` ou limpeza de dados. A única alteração
  remota foi a migration 31, autorizada em 2026-11-05; nenhum dado foi tocado.
- Nenhuma rotação de credencial (não houve exposição que a exigisse).
- Nenhum segredo foi lido, impresso, copiado ou incluído neste relatório.
