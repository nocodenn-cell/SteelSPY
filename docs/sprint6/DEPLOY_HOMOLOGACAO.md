# Runbook de publicação — homologação do piloto

**Estado:** documentado, **não executado**. Não houve deploy, push nem alteração
no projeto oficial nesta sprint. Este arquivo só descreve o caminho quando o
proprietário autorizar.

**Topologia mínima de custo zero** (usa a infraestrutura já existente):

```
Celular ──HTTPS──> PWA estático
                      │  apiBaseUrl
                      ▼
                   API FastAPI ──pooler 5432──> Supabase oficial
                      │
                      └── Storage privado (evidências)

Back-office ──VPN/URL interna──> Dashboard Streamlit ──role stellspy_dashboard──> Supabase
```

PWA, API e dashboard podem ficar na mesma origem ou em subdomínios distintos.
Se forem origens diferentes, o CORS e o cookie precisam ser explícitos.

---

## 1. Pré-requisitos

- [ ] Checklist `docs/sprint6/CHECKLIST_PUBLICACAO.md` com todos os portões GO.
- [ ] Ensaio de backup/restauração concluído e registrado.
- [ ] Commit de referência identificado (o que será publicado e o anterior).
- [ ] Certificado HTTPS válido para o domínio do PWA.
- [ ] `CORS_ALLOW_ORIGINS` com a origem exata do PWA.
- [ ] Segredos no cofre do provedor, nunca em arquivo do repositório.

---

## 2. API

1. Empacotar o código do commit aprovado (`backend/`), sem `.env`.
2. Configurar o processo com apenas as variáveis da seção "API" do checklist.
3. Subir com `uvicorn app.main:app --host 0.0.0.0 --port 8000` atrás de proxy TLS.
4. Verificar no boot:
   - `/health` → `{"status":"ok"}`;
   - nenhum `RuntimeError` de `CORS_ALLOW_ORIGINS`;
   - log sem string de conexão, senha ou token.
5. Conferir que o processo **não** recebeu `SUPABASE_DB_ADMIN_URL` nem as senhas
   de role.

`PWA_COOKIE_SECURE=1` é obrigatório em HTTPS. Se PWA e API estiverem em domínios
diferentes, `PWA_COOKIE_SAMESITE=none` **exige** `Secure=1`; caso contrário, o
navegador descarta o cookie e o login parece "não persistir".

---

## 3. PWA

1. Publicar `pwa/` como estático em HTTPS (mesma origem da API é o caminho mais
   simples e não precisa de CORS).
2. Preencher `apiBaseUrl` no `index.html` **do artefato**, não no commit:
   `{"apiBaseUrl": "https://api.seudominio.com"}`.
3. Confirmar que `sw.js` é servido com `Content-Type: application/javascript` e
   que o cache versionado não prende a versão anterior.
4. Abrir no celular e validar: login, lista de obras, uma consulta de pedido.
   Câmera só funciona em HTTPS ou localhost — este é o ponto que o teste físico
   precisa cobrir.

---

## 4. Dashboard (opcional)

1. Publicar em URL interna/VPN. A senha `DASHBOARD_PASSWORD` (≥ 12,
   dedicada) é **obrigatória**: sem ela o painel falha fechado.
2. Variáveis: `DASHBOARD_DATABASE_URL` (role `stellspy_dashboard`),
   `DASHBOARD_TENANT_ID`, `DASHBOARD_PASSWORD`, `PYTHONPATH=backend`.
3. O dashboard **não** recebe `DATABASE_URL`, `SUPABASE_DB_ADMIN_URL` nem chave
   `service_role`.
4. Abrir a tela: o diagnóstico precisa mostrar a construtora e as obras visíveis.
   Se aparecer "credencial recusada", a role está errada — não afrouxe RLS.

---

## 5. Migrations

- Executar uma única vez, com o runner administrativo, **antes** de subir a API
  nova quando houver migration pendente.
- Trilha atual: **31 arquivos** em `supabase/migrations/`; a última cria a role
  `stellspy_dashboard`.
- A migration da role é fail-closed: sem `STELLSPY_DASHBOARD_PASSWORD`, a role
  permanece `NOLOGIN` e o dashboard não conecta.
- Reexecutar o runner é seguro: migrations já aplicadas são puladas por
  `schema_migrations`.

---

## 6. Verificação pós-publicação

| Verificação | Esperado |
|-------------|----------|
| `GET /health` | 200 `ok` |
| Login de engenheiro, fiscal e auditor | 200; `/auth/obras` só com obras vinculadas |
| Construtora vizinha | 404 em pedido/recebimento/evidência por id |
| Recebimento com retry | uma única entrada (`criado=false` no reenvio) |
| Foto com reenvio | uma única evidência (`criada=false`) |
| Download de foto | bytes conferem com `X-Conteudo-Sha256`; `no-store` |
| Dossiê PDF | 200, `%PDF`, `X-Dossie-Id` |
| Dashboard | construtora e obras do tenant; nenhuma obra de outro tenant |
| Auditoria de configuração | `auditar_publicacao.py` → 0 bloqueios |

---

## 7. Reversão

1. Republicar API e PWA do commit anterior (procedimento reversível).
2. Não desfazer migration com `DROP`/`ALTER` destrutivo; publicar correção
   aditiva.
3. Restauração de dados segue
   `docs/sprint6/PROCEDIMENTO_BACKUP_RESTAURACAO.md` e exige autorização.
4. Registrar horário, commit, sintoma e ação.
