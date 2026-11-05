# Plano de deploy gratuito — API + PWA com HTTPS

**Estado:** proposto e auditado em 2026-11-05. **Nada foi executado:** sem conta,
sem deploy, sem domínio, sem migration remota e sem alteração de ambiente.
Orçamento adicional: **R$ 0,00**.

---

## 1. Arquitetura recomendada

**Um único Web Service Free no Render**, servindo a API FastAPI **e** o PWA
estático na mesma origem HTTPS (`https://<servico>.onrender.com`):

```
celular/desktop
     │ HTTPS (onrender.com, TLS gerenciado)
     ▼
Render Free — uvicorn app.main:app
     ├── /            → pwa/index.html + assets + sw.js (StaticFiles)
     ├── /auth, /pedidos, /evidencias, /correlacoes, /health → FastAPI
     └── pooler Supabase (5432, sslmode=require) → Postgres/Storage oficiais
```

Por que mesma origem:

- **não há CORS** a configurar (`CORS_ALLOW_ORIGINS` vazio é seguro);
- cookie de sessão fica `SameSite=Lax` e `Secure`, sem depender de cookie de
  terceiros — Safari/ITP e bloqueios de terceiros deixam de ser risco;
- câmera e service worker funcionam em HTTPS na mesma origem do app;
- um único serviço cabe nas 750 h/mês do Render Free.

O dashboard Streamlit **não** entra nesse deploy: ele acessa o Postgres direto e
é opcional. Para o piloto, rode-o localmente/VPN com a role
`stellspy_dashboard` e `DASHBOARD_PASSWORD` obrigatória (ver §7).

### Mudança de código necessária antes do deploy (não executada)

`backend/app/main.py` hoje não serve o PWA. O deploy same-origin exige montar
`pwa/` **depois** dos routers e do `/health`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_PWA = Path(__file__).resolve().parents[2] / "pwa"
app.mount("/", StaticFiles(directory=_PWA, html=True), name="pwa")
```

O PWA usa roteamento por hash (`#/obra`, `#/recebimento`), então não precisa de
fallback de SPA. O service worker é registrado em `./sw.js` e usa caminhos
relativos — funciona no mesmo host. Antes de publicar, cobrir com teste:
`/` devolve 200 e o HTML, `/manifest.json` e `/sw.js` têm `Content-Type`
correto, e as rotas da API continuam respondendo (a montagem em `/` não pode
sombrear `/health` nem os routers).

Também servir `sw.js` com `Cache-Control: no-cache` (ou `max-age=0`), para que
uma correção do app não fique presa no cache do service worker.

---

## 2. Limites gratuitos conferidos em 2026-11-05

| Serviço | Limite gratuito | Consequência para o piloto |
|---------|------------------|----------------------------|
| **Render Free Web Service** | 750 h/instância/mês por workspace; dorme após **15 min** sem tráfego; acorda em ~1 min; 0,1 CPU / 512 MB; sem disco persistente; sem shell/one-off jobs; SMTP de saída bloqueado; HTTPS e domínio custom inclusos; **sem cartão** | Um serviço ligado 24/7 consome ~730 h/mês — cabe, mas sem folga para um segundo serviço sempre ativo. Primeira requisição após ociosidade demora ~1 min. Fotos **precisam** ir para o Supabase Storage (disco local é efêmero). |
| **Supabase Free** | 500 MB de banco; 1 GB de Storage; 5 GB de egress; 2 projetos ativos; pausa após **7 dias de baixa atividade**; retomada preserva dados | Uso diário do piloto evita a pausa. Se ficar uma semana parado, retomar no painel (até 1 ano). Monitorar banco e fotos: 1 GB de Storage limita o volume de evidências. |
| **PWA estático** | Servido pelo próprio Render no plano acima, sem custo extra de instância | Não precisa de GitHub Pages/Cloudflare Pages. Se separado, vira outra origem e reintroduz CORS/cookie de terceiros. |
| **Koyeb Free (alternativa)** | 1 instância 512 MB / 0,1 vCPU; dorme após 1 h; regiões Frankfurt/Washington; “hobby, não produção” | Fallback se o Render não atender. Sleep de 1 h é pior para campo e a documentação desaconselha produção. |
| **GitHub Actions** | Minutos gratuitos em repositório público | Usado apenas para teste/keep-alive opcional; não hospeda a API. |

Fora do plano: planos pagos, domínio próprio, banco pago, IP fixo, HA. Nenhum
deles é necessário para o piloto.

---

## 3. Ordem de execução (quando autorizada)

1. **Congelar** escrita nova e registrar o commit a publicar: hoje `0f5579b`
   (publicado, inclui a correção de autenticação do dashboard).
2. **Backup manual** do banco oficial (`pg_dump`/procedimento
   `PROCEDIMENTO_BACKUP_RESTAURACAO.md`) e registrar hash/tamanho.
3. **Conferir a migration 31**: já aplicada no projeto oficial em 2026-11-05
   (31/31). Reexecutar o runner é no-op; a senha da role do dashboard só muda
   com `STELLSPY_DASHBOARD_PASSWORD` e autorização explícita.
4. **Criar o Web Service** no Render a partir do repositório/branch autorizado:
   - Root Directory: raiz do repositório;
   - Build: `pip install -r backend/requirements.txt -c backend/constraints.txt`;
   - Start: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`;
   - Health Check Path: `/health`;
   - Python: fixar a versão suportada (ex.: `PYTHON_VERSION=3.12`) para não
     quebrar dependências por uma subida silenciosa.
5. **Configurar variáveis** (§4) como secrets do Render. Nada de `.env`
   versionado.
6. **Publicar** e aguardar `/health` → `{"status":"ok"}`.
7. **Smoke test** (§6) com dados sintéticos.
8. **Instalar o PWA** no Android via HTTPS e executar o roteiro de campo
   (`docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md`).
9. **Observar** 30 min: 5xx, 401/403 inesperados, 503 de banco, erros de CORS
   (não deve haver CORS no same-origin), latência e memória.
10. **Registrar** URL, commit, horário e resultados no relatório do piloto.

---

## 4. Variáveis por processo no Render

Somente o processo da API. O dashboard não roda nesse serviço.

| Variável | Valor no piloto | Observação |
|----------|------------------|------------|
| `DATABASE_URL` | `postgresql+psycopg2://stellspy_app.<ref>:<senha>@aws-0-<região>.pooler.supabase.com:5432/postgres?sslmode=require` | role operacional, sujeita a RLS; **nunca** `postgres.<ref>` |
| `PWA_SESSION_SECRET` | ≥ 32 caracteres aleatórios | `openssl rand -hex 32`; fora do Git |
| `PWA_COOKIE_SECURE` | `1` | HTTPS |
| `PWA_COOKIE_SAMESITE` | `lax` | same-origin; `none` só se separar PWA e API |
| `CORS_ALLOW_ORIGINS` | vazio | same-origin não precisa de CORS; se separar, lista exata HTTPS |
| `SKIP_API_KEY` | `0` | nunca desligar autenticação no piloto |
| `NFE_IO_MOCK` | `0` | com `NFE_IO_TOKEN` real, ou fluxo manual aceito por escrito |
| `NFE_IO_TOKEN` | token real, se integração ativa | server-side |
| `EVIDENCIAS_STORAGE` | `supabase` | disco do Render é efêmero |
| `EVIDENCIAS_BUCKET` | `evidencias` | bucket privado |
| `SUPABASE_URL` | `https://akvbtceshpsvsuacueaq.supabase.co` | projeto oficial |
| `SUPABASE_SERVICE_ROLE_KEY` | chave real | **somente servidor**; nunca no PWA nem em log |
| `LAUDO_STORAGE_BUCKET` | `laudos` | opcional |
| `PYTHON_VERSION` | `3.12` (ou a suportada no dia) | reprodutibilidade |

**Proibido no processo da API:** `SUPABASE_DB_ADMIN_URL`,
`STELLSPY_APP_PASSWORD`, `STELLSPY_DASHBOARD_PASSWORD`,
`DASHBOARD_DATABASE_URL`, `DASHBOARD_TENANT_ID`, `DASHBOARD_PASSWORD`.

---

## 5. PWA

- Manter `apiBaseUrl: ""` no `index.html` **do artefato** (same-origin).
- HTTPS é obrigatório para câmera e service worker; `onrender.com` já fornece.
- Conferir `Content-Type: application/manifest+json` (ou `application/json`) e
  `application/javascript` em `/sw.js`.
- O cache versionado do service worker deve apontar para os assets corretos;
  validar atualização após um redeploy (fechar/abrir e confirmar versão nova).
- Não colocar `SUPABASE_SERVICE_ROLE_KEY`, `NFE_IO_TOKEN` nem senha no
  JavaScript do PWA.

---

## 6. Smoke test mínimo (dados sintéticos)

1. `GET /health` → 200.
2. `GET /` → HTML do PWA; `GET /manifest.json` e `GET /sw.js` → 200.
3. Login de cada papel (operador, fiscal/auditor, gestor) e `GET /auth/obras`.
4. Consulta de pedido por chave, uma NF-e sintética.
5. Recebimento parcial + foto; conferir hash no download.
6. Download de dossiê PDF; conferir `Content-Disposition`.
7. Cross-tenant: usuário da construtora A recebe **404** para obra de B.
8. Recarregar o PWA com rede instável: rascunho sobrevive; nada é confirmado
   sem resposta do servidor.

---

## 7. Dashboard (fora do deploy público)

- Rodar local/VPN: `PYTHONPATH=backend streamlit run dashboard/app.py`.
- `DASHBOARD_DATABASE_URL` = role `stellspy_dashboard` (SELECT em 5 tabelas).
- `DASHBOARD_TENANT_ID` = UUID da construtora do piloto.
- `DASHBOARD_PASSWORD` **obrigatória** (≥ 12, dedicada): sem ela o painel falha
  fechado. Não reutilizar a senha da role do banco nem a da API.
- Se um dia for publicado, usar HTTPS + autenticação de rede (VPN/proxy) e
  reavaliar rate limiting; a senha compartilhada sozinha não é MFA.

---

## 8. Cold start, keep-alive e pausa do Supabase

**Render:** após 15 min sem tráfego, o serviço dorme e a primeira requisição
demora ~1 min. Opções:

- **Aceitar o cold start** e orientar o operador a abrir o PWA alguns minutos
  antes do uso. Mais simples e sem risco de consumir horas.
- **Keep-alive** com GitHub Actions (repositório público) chamando `/health` a
  cada 10 min. Mantém o serviço acordado (~730 h/mês < 750 h), mas consome
  quase toda a franquia e não deixa margem para um segundo serviço. Não é
  garantia contratual do provedor; monitorar o consumo.
- **Pago** (fora do orçamento).

**Supabase:** uso diário evita a pausa por 7 dias de baixa atividade. Se o
piloto ficar parado, retomar no painel; os dados são preservados. Não criar
credencial de banco em GitHub Actions só para “acordar” o banco — isso amplia
a superfície de segredo. Preferir retomada manual registrada no runbook.

---

## 9. Riscos específicos do plano gratuito

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Cold start de ~1 min | B (primeira impressão no campo) | abrir antes do uso ou keep-alive aprovado |
| 0,1 CPU / 512 MB | B (PDF/fotos lentos) | testar com foto real; limitar concorrência; monitorar |
| 750 h/mês compartilhadas | B | um único serviço; não publicar dashboard como segundo serviço sempre ativo |
| Supabase pausa após 7 dias | B | uso diário ou retomada manual; aviso ao proprietário |
| 500 MB de banco / 1 GB de Storage / 5 GB de egress | B | monitorar; foto normalizada; dossiês não replicados |
| Sem backup automático no Free | A | `pg_dump` manual antes do piloto e periodicamente |
| Logs efêmeros e sem shell | C | logs no Render; não depender de disco local |
| Sem SLA / reinício a qualquer momento | B | retry idempotente já implementado; backup |
| Keep-alive consome a franquia | C | decisão explícita do proprietário; monitorar |

---

## 10. Critérios de GO para este deploy

- [ ] Autorização escrita para publicar e para aplicar a migration 31.
- [ ] Backup manual com hash/tamanho registrados.
- [ ] Branch/commit de deploy identificado e auditado (0 bloqueios).
- [ ] Variáveis conferidas: sem admin URL, sem `service_role` no PWA,
      `SKIP_API_KEY=0`, `NFE_IO_MOCK=0`, cookie `Secure`.
- [ ] `/health`, login, consulta, foto e dossiê aprovados em smoke sintético.
- [ ] Roteiro físico em Android aprovado (câmera + retry).
- [ ] Dashboard com senha obrigatória (se publicado) ou fora da internet.
- [ ] Plano de retomada do Supabase e de backup periódico aceitos.

Enquanto qualquer item acima estiver aberto, o piloto real permanece **NO-GO**
(ver `RELATORIO_AUDITORIA_POS_PUSH.md` e `CHECKLIST_PUBLICACAO.md`).

---

## 11. Reversão

1. Republicar o deploy anterior no Render (rollback para os dois últimos
   deploys) ou o commit anterior.
2. Migrations são aditivas: não usar `DROP`; corrigir para a frente.
3. Se houver corrupção, restaurar o dump manual — com autorização explícita.
4. Registrar hora, commit, sintoma e ação.

---

## Fontes consultadas (2026-11-05)

- Render — Deploy for Free: https://render.com/docs/free
- Supabase — Pricing: https://supabase.com/pricing
- Supabase — Project Pausing: https://supabase.com/docs/guides/platform/free-project-pausing
- Koyeb — Instances: https://www.koyeb.com/docs/reference/instances
- Cloudflare Pages — Limits: https://developers.cloudflare.com/pages/platform/limits/
