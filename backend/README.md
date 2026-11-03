# stellSPY — Backend (API de auditoria NF-e)

API FastAPI que compara a NF-e com a especificação da obra e decide
**VERDE / AMARELO / VERMELHO** por item, gerando laudo em PDF.

---

## Requisitos

| Item | Versão de referência |
|------|----------------------|
| Python | **3.13.x** (testado em 3.13.15) |
| Sistema | Windows ou Linux |
| Banco | PostgreSQL (Supabase) — só necessário para rodar a API, **não** para os testes |

---

## Instalação reproduzível (comando oficial)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
```

Em Linux/macOS, troque o caminho do interpretador por `.venv/bin/python`.

> **O `-c constraints.txt` não é opcional se você quer reprodutibilidade.**
> Sem ele, o `pip` resolve as faixas de `requirements.txt` e pode trazer uma
> combinação nunca testada — foi assim que a API parou de subir em 2026-11-03
> (ver `docs/execucao/EVIDENCIAS.md`, E10 e E12).

### As três camadas de dependência

| Arquivo | Papel |
|---------|-------|
| `requirements.txt` | **Dependências diretas** com faixas de compatibilidade |
| `requirements-dev.txt` | Dependências de teste (`-r requirements.txt` + pytest) |
| `constraints.txt` | **Versões efetivamente testadas**, inclusive transitivas |

Regra de faixa: pacotes `0.x` quebram no *minor* (teto no próximo minor);
pacotes `>=1.x` quebram no *major* (teto no próximo major).

### Para subir uma versão

1. Alterar `constraints.txt`.
2. Recriar o `.venv` do zero.
3. Rodar a suíte inteira.
4. Ajustar as faixas em `requirements*.txt` se necessário.
5. Registrar em `docs/execucao/CHANGELOG.md`.

Não edite o número e continue usando o ambiente antigo: o teste passa e a
instalação limpa quebra.

---

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Estado atual: **82 testes aprovados**. A suíte **não** precisa de banco.

---

## Rodar a API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- Documentação interativa: <http://localhost:8000/docs>
- Saúde: `GET /health` → `{"status": "ok"}`

### Variáveis de ambiente

O projeto **não carrega `.env` automaticamente**. Use uma das opções:

```powershell
# a) arquivo de ambiente do próprio uvicorn
.\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env

# b) exportar na sessão
$env:DATABASE_URL = "postgresql+psycopg2://..."
```

Modelo completo de configuração: [`.env.example`](.env.example).

> Sem `DATABASE_URL`, `app/db.py` cai silenciosamente no padrão
> `postgres:postgres@localhost:5432/postgres`. Em produção, sempre defina.

---

## Jobs

```powershell
# Fila de retentativa de XML (agendar a cada 1–5 min)
.\.venv\Scripts\python.exe -m app.fila_worker_main

# Relatório semanal CSV + e-mail
.\.venv\Scripts\python.exe -m app.relatorio_semanal_main
```

---

## Estrutura

```
app/
  main.py              FastAPI: CORS, /health, inclusão dos routers
  db.py                engine e sessão SQLAlchemy (sync)
  auth_obra.py         X-API-KEY ou cookie de sessão
  pwa_session.py       cookie HMAC-SHA256
  routers/             auth_pwa, conferencia
  domain/conferente.py núcleo de normalização e matching
  services/            NF-e, PDF, WhatsApp, SMTP, fila, relatórios
  utils/               chave NF-e (módulo 11), validação de URL
tests/                 82 testes
```

Migrações SQL ficam em [`../supabase/migrations/`](../supabase/migrations/).
Documentação de arquitetura e decisões em [`../docs/`](../docs/).
