# RELATÓRIO DE TESTES — Baseline Executável

> **Data:** 2026-11-03 · **Ambiente:** Windows, PowerShell 7.6.9, Python 3.13.15, venv isolado
> **Natureza:** execução real. Todos os números abaixo foram produzidos por `pytest`, não estimados.

---

## 1. Resultado

```
$ backend> .\.venv\Scripts\python.exe -m pytest -q
69 passed, 24 warnings in 1.75s

$ backend> .\.venv\Scripts\python.exe -m pytest --collect-only -q
69 tests collected in 0.99s
```

| Métrica | Valor | Estado |
|---------|-------|--------|
| Testes coletados | **69** | TESTADO |
| Testes aprovados | **69** | TESTADO |
| Testes falhando | **0** | TESTADO |
| Testes ignorados | 0 | TESTADO |
| Duração | 1,75 s | TESTADO |
| Warnings | 24 (todos de deprecação) | TESTADO |
| Cobertura de código | **não medida** | BLOQUEADO (sem `pytest-cov`) |
| Testes de HTTP | **0** | BLOQUEADO (sem `TestClient` no projeto) |
| Testes de banco | **0** | BLOQUEADO (sem infra de teste de DB) |

**Interpretação:** o núcleo de domínio está saudável e não regrediu. O que **não** existe é verificação
de borda — exatamente onde a auditoria identificou os defeitos de severidade alta.

---

## 2. Pré-condição necessária (defeito encontrado)

A suíte **não rodava** no estado do repositório:

```
ERROR tests/test_relatorio_semanal.py
E   zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key America/Sao_Paulo'
!!! Interrupted: 1 error during collection !!!
pytest exit: 2
```

| Item | Detalhe |
|------|---------|
| Causa | `app/services/relatorio_semanal.py:20` — `ZoneInfo("America/Sao_Paulo")` em tempo de import |
| Pacote faltante | `tzdata`, **não declarado** em `requirements.txt` |
| Efeito | suíte inteira não coleta (0 de 69 executados) |
| Contorno aplicado | `pip install tzdata` **apenas no `.venv`** |
| Correção de código | **não aplicada** — aguarda aprovação (P-01) |

> Este é o achado **M6** da auditoria estática, agora **confirmado por execução**. Deixa de ser
> hipótese.

---

## 3. Composição da suíte (verificada estaticamente + confirmada por coleta)

| Arquivo | Funções | Área |
|---------|---------|------|
| `test_conferente.py` | 13 (→15 casos) | domínio: bitola, marca, quantidade, multimaterial |
| `test_cimento_modulo.py` | 8 | normalização e comparador de cimento |
| `test_whatsapp_evolution.py` | 7 | retry, backoff, destino |
| `test_relatorio_semanal.py` | 7 | janela, CSV, idempotência, SMTP |
| `test_auth_obra.py` | 3 | API key |
| `test_chave_nfe.py` | 3 | DV módulo 11 |
| `test_conferencia_multimaterial.py` | 4 | cimento/bloco no pipeline |
| `test_mensagem_fiscal.py` | 4 | textos por status |
| `test_pwa_session.py` | 4 | cookie HMAC |
| `test_url_seguras.py` | 4 | SSRF / redirect |
| `test_auth_acesso.py` | 2 | cookie × header |
| `test_divergencias_pdf.py` | 2 | geração de PDF |
| `test_laudo_pdf.py` | 2 | contexto e marca d'água |
| `test_nfe_io.py` | 2 | adapter NF-e |
| **Total** | **65 funções → 69 casos** | |

---

## 4. Cobertura por camada (qualitativa)

| Camada | Coberta? | Observação |
|--------|----------|------------|
| `app/domain/conferente.py` | ✅ boa | regras centrais com casos de borda |
| `app/services/comparador_cimento.py` | ✅ boa | tipo, FCK, validade, quantidade |
| `app/services/comparador_bloco.py` | ⚠️ parcial | via `test_conferencia_multimaterial` |
| `app/utils/chave_nfe.py` | ✅ | DV e formato |
| `app/utils/url_seguras.py` | ✅ | SSRF e redirect |
| `app/pwa_session.py` | ✅ | assinatura, expiração |
| `app/services/nfe_io.py` | ⚠️ parcial | só o adapter, sem HTTP real |
| `app/services/laudo_pdf.py` | ⚠️ parcial | gera bytes, não valida conteúdo |
| `app/services/relatorio_semanal.py` | ✅ | CSV e idempotência |
| `app/services/email_smtp.py` | ⚠️ parcial | mock de SMTP |
| `app/routers/conferencia.py` | ❌ **zero** | `/conferir`, `/override`, PDFs |
| `app/routers/auth_pwa.py` | ❌ **zero** | login, sessão, logout |
| `app/services/fila_retentativa.py` | ❌ **zero** | módulo de maior risco |
| `app/services/conferencia_persist.py` | ❌ **zero** | persistência da conferência |
| `app/services/nfe_persistencia.py` | ❌ **zero** | itens da NF |
| `app/services/laudo_storage.py` | ❌ **zero** | upload de PDF |
| `app/auth_obra.py` | ⚠️ parcial | só `verificar_api_key_obra` |
| `dashboard/` | ❌ **zero** | — |
| `pwa/` | ❌ **zero** | `npm test` existe, sem testes |

---

## 5. Warnings (24) — todos de deprecação

| Arquivo:linha | Mensagem | Ação |
|---------------|----------|------|
| `laudo_pdf.py:162, 314, 342, 368` | `parameter "ln" is deprecated since v2.5.2` | Trocar por `new_x`/`new_y` (Fase 0, baixo risco) |
| `laudo_pdf.py:409` | `"dest" parameter is deprecated since v2.2.0 and will be removed` | Trocar por `pdf.output()` |
| `email_smtp.py` / outros | — | nenhum além dos acima |

**Risco real:** `requirements.txt` usa `fpdf2>=2.8.0` **sem teto**. A remoção de `dest=` numa versão
futura quebraria a geração de PDF na produção sem aviso. É o risco **M5** da auditoria.

---

## 6. Como reproduzir

```powershell
cd C:\Naturecode\stellSPY\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install tzdata      # workaround temporário (P-01)
.\.venv\Scripts\python.exe -m pytest -q
```

Congelamento do ambiente obtido: `backend/baseline_freeze.txt` (33 pacotes).

> **Nota de execução:** no modo confinado do sandbox, a escrita em `backend\` é negada (ver
> `EVIDENCIAS.md` §E1.4). Estes comandos exigem execução autorizada fora do confinamento.

---

## 7. Suíte proposta para a Fase 0 (ainda não implementada)

| Grupo | Testes | Estado |
|-------|--------|--------|
| Isolamento entre tenants (I1–I6) | 6 | PLANEJADO |
| Mutação de RLS (remover policy → falhar) | 1 | PLANEJADO |
| RBAC — matriz 36 células | 36 (parametrizados) | PLANEJADO |
| Contrato das 8 rotas (snapshot) | 8 | PLANEJADO |
| Migrações aplicadas do zero + idempotência | 2 | PLANEJADO |
| Reaper de fila | 2 | PLANEJADO |
| Compatibilidade `POST /conferir` | 1 | PLANEJADO |

**Meta:** 69 → ~125 casos, mantendo os 69 atuais verdes (critério AC0.2).

---

## 8. Veredito deste relatório

| Pergunta | Resposta |
|----------|----------|
| O código atual funciona? | **Sim** — 69/69 |
| O repositório roda out-of-the-box? | **Não** — falta `tzdata` (confirmado) |
| A base de testes é confiável para refatorar? | **Só para o domínio.** Bordas sem cobertura |
| Pode iniciar a Fase 0? | **Ainda não** — ver `MATRIZ_GO_NO_GO.md` (G-04 e G-05 fechados) |
