# SteelSpy — Contexto do Projeto

## Visão geral

Sistema de auditoria de conformidade de materiais de construção na entrada da obra (NF-e × especificação). Hoje o núcleo é **aço (vergalhão)**; a arquitetura evolui para **cimento** e **blocos** no mesmo fluxo (categoria + `atributos_especificos` JSONB).

## Stack

- **Backend:** FastAPI (Python 3.11+), SQLAlchemy + SQL texto onde aplicável
- **Banco:** PostgreSQL (Supabase)
- **Integrações:** NFe.io (XML), Evolution API (WhatsApp), SMTP (relatório)
- **Frontend:** PWA vanilla (`pwa/`), Tailwind buildado (`pwa/assets/app.css`)
- **Dashboard:** Streamlit (`dashboard/`)
- **Worker:** fila de retentativa (`app.services.fila_retentativa`)

## Estrutura de diretórios (raiz)

```
backend/app/
  main.py                 # FastAPI
  routers/              # auth_pwa, conferencia
  domain/conferente.py  # Normalização aço, matching por bitola, status agregado
  services/             # nfe_io, conferencia_persist, normalizacao_cimento, comparador_cimento, …
  utils/
supabase/migrations/    # Schema versionado
pwa/                    # PWA
dashboard/              # Streamlit
docs/                   # Documentação auxiliar
```

## Modelos de dados (principais)

### `obras`

- `id`, `nome`, `cnpj_destinatario`, `aceita_similar`, `margem_tolerancia_float`, `modo_aprendizado`
- Colunas operacionais: `api_key`, `whatsapp_destino`, e-mails / idempotência de relatório (conforme migrações recentes)

### `especificacoes`

- Base (aço): `material_tipo`, `bitola_mm`, `marca_exigida`, `qtd_planejada_metros`
- Extensão multi-material: `categoria_material` (`'aco' | 'cimento' | 'bloco'`), `atributos_especificos` (JSONB: `tipo`, `fck_mpa`, `slump_mm`, `dimensoes`, etc.)

### `normalizacao_materiais`

Tabela de fatores por categoria / “nome” (ex.: tipo de cimento ou dimensão de bloco), `unidade_origem` → `unidade_destino`, `fator_conversao`, `parametros` JSONB.

### `nfe_logs` / `nfe_itens`

Conferência persistida, `status_conferencia`, itens com `especificacao_id`, divergências.

## Regras de negócio críticas

1. **Pior status:** um item VERMELHO puxa a NF para VERMELHO (agregação em `conferente.py`).
2. **Aço:** matching principal por **bitola**; quantidade em **metros** após normalizar kg/barras.
3. **Cimento (módulo novo):** normalização sacos ↔ m³, kg ↔ m³; divergências: tipo CP, FCK, validade, quantidade (ver `comparador_cimento.py`).
4. **Idempotência** de relatório semanal e **fallback** WhatsApp (`obra.whatsapp_destino` → env global) conforme serviços existentes.

## Variáveis de ambiente

- Obrigatórias: `DATABASE_URL`, `NFE_IO_TOKEN`, `PWA_SESSION_SECRET`, `CORS_ALLOW_ORIGINS`
- Opcionais: Evolution API, SMTP, relatório, dashboard

## Próximos passos (produto)

- [ ] Integrar categoria **cimento** no pipeline de `conferente` (detecção + matching além de bitola)
- [ ] Módulo **blocos** (normalização + regras)
- [ ] Testes de integração NF-e de exemplo por categoria
- [ ] CI/CD, testes frontend

## Comandos úteis

```bash
# API
cd backend && uvicorn app.main:app --reload

# Worker (se aplicável)
python -m app.fila_worker_main

# Dashboard
set PYTHONPATH=backend && streamlit run dashboard/app.py

# PWA estática
cd pwa && python -m http.server 8080

# CSS PWA
cd pwa && npm run build:css
```

## Documentação da API

- Swagger: `http://localhost:8000/docs`
