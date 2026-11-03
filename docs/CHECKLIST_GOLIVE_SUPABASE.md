# Checklist — Go-live Supabase + variáveis de ambiente

Trilha escolhida: colocar **banco + API** prontos para o piloto antes do PWA. Siga na ordem; marque cada item.

---

## 1. Projeto Supabase

- [ ] Confirme que está no projeto certo (ex.: **spysteel** — veja **Settings → General → Project ID**).
- [ ] Anote a **URL** do projeto: `https://<PROJECT_REF>.supabase.co` (útil para `SUPABASE_URL` e Storage).

---

## 2. Migrações SQL (schema)

No **SQL Editor**, rode **na ordem** os ficheiros em `supabase/migrations/` (ou use Supabase CLI: `supabase db push` com o projeto ligado):

1. `20260410120000_core_schema.sql`
2. `20260410200000_nfe_logs_foto_url.sql`
3. `20260410210000_nfe_itens_resumo_devolucao.sql`
4. `20260410230000_nfe_logs_laudo_storage.sql`
5. `20260410240000_obras_api_key_idempotencia.sql`

**Verificação rápida:**

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'obras' AND column_name = 'api_key';
-- deve retornar 1 linha

SELECT constraint_name FROM information_schema.table_constraints
WHERE table_name = 'nfe_logs' AND constraint_type = 'UNIQUE';
-- deve incluir a unicidade obra+chave
```

---

## 3. Dados mínimos para um teste

- [ ] **Obra:** pelo menos uma linha em `obras` com `cnpj_destinatario` (14 dígitos), políticas desejadas e **`api_key`** preenchida (a migração gera para as existentes; novas obras recebem default).
- [ ] **Especificação:** pelo menos uma linha em `especificacoes` para essa `obra_id` (bitola, marca, qtd planejada em metros).

**Obter a API Key da obra para o PWA/cURL:**

```sql
SELECT id, nome, api_key FROM obras;
```

Guarde a `api_key` em lugar seguro (1Password, etc.). **Não** commite no Git.

---

## 4. Storage (opcional, laudo em cache)

- [ ] Crie o bucket **`laudos`** (ou o nome em `LAUDO_STORAGE_BUCKET`).
- [ ] Torne o bucket **público** para leitura **ou** ajuste depois para URLs assinadas (MVP: público é mais simples).
- [ ] Preencha `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` (Settings → API → **service_role** — só no servidor).

Se não configurar Storage, o `GET /laudo.pdf` ainda **funciona**: devolve o PDF inline.

---

## 5. `DATABASE_URL` na API

- [ ] **Settings → Database** → connection string (use **pooler** em produção se a Supabase recomendar; formato `postgresql+psycopg2://...` como em `backend/.env.example`).
- [ ] Teste local: `cd backend && uvicorn app.main:app --reload` com `.env` carregado (ou export manual).

---

## 6. Variáveis de ambiente em produção

Copie de `backend/.env.example` e defina no painel do host (Render, Fly, etc.):

| Variável | Obrigatório piloto? | Notas |
|----------|---------------------|--------|
| `DATABASE_URL` | Sim | String Postgres do Supabase |
| `SKIP_API_KEY` | Sim → **0** ou vazio | Nunca `1` em produção |
| `CORS_ALLOW_ORIGINS` | Sim quando houver PWA | Origem exata, ex. `https://app.steelspy.com.br` |
| `NFE_IO_TOKEN` | Sim se não usar mock | Sem token a API não busca NF real |
| `NFE_IO_MOCK` | Só dev | `1` só para demo sem NFe.io |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | Não | Só se quiser cache do PDF no Storage |
| `LAUDO_STORAGE_BUCKET` | Não | Default `laudos` |

---

## 7. Smoke test (após deploy ou local)

Substitua `BASE`, `OBRA_ID`, `CHAVE44`, `API_KEY`:

```bash
curl -s -X POST "$BASE/conferir" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: $API_KEY" \
  -d "{\"obra_id\":\"$OBRA_ID\",\"chave_acesso\":\"$CHAVE44\"}"
```

- [ ] Resposta JSON com `status`, `nfe_log_id` (ou `PENDENTE` se XML indisponível).
- [ ] `GET $BASE/conferir/<nfe_log_id>/laudo.pdf` com o mesmo header `X-API-KEY` → PDF ou redirect.

---

## 8. Segurança

- [ ] **Não** commitar `.env` nem `service_role` no repositório.
- [ ] Chave **anon/publishable** do Supabase é para **cliente** (JS no browser); a API Python usa **`DATABASE_URL`** e, se aplicável, **`SUPABASE_SERVICE_ROLE_KEY`** só no servidor.
- [ ] Rotacione qualquer chave que tenha vazado em chat/issue.

---

## Próximo passo (outra trilha)

Quando este checklist estiver verde, a trilha **PWA mínimo** chama o mesmo `POST /conferir` com `X-API-KEY` e a origem já listada em `CORS_ALLOW_ORIGINS`.
