# CHANGELOG

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
O projeto **não segue versionamento semântico ainda** — não há tag nem release.

> **Princípio:** este changelog registra apenas o que **efetivamente mudou** no repositório e no
> ambiente. Intenção, plano e análise não entram aqui.

---

## [Não lançado] — 2026-11-03 — Sprint de Engenharia 0

### Adicionado — documentação

- `docs/execucao/STATUS_EXECUCAO.md` — painel de estado por fase
- `docs/execucao/CHANGELOG.md` — este arquivo
- `docs/execucao/DECISOES_TECNICAS.md` — 8 ADRs (ambiente, venv, tzdata, PostgreSQL, versionamento)
- `docs/execucao/RELATORIO_TESTES.md` — baseline 69/69 e mapa de lacunas
- `docs/execucao/EVIDENCIAS.md` — 8 evidências executadas com saída de comando
- `docs/execucao/PROXIMOS_PASSOS.md` — 12 ações priorizadas com gates
- `docs/execucao/MATRIZ_GO_NO_GO.md` — revisão com gates reais (§14)

### Adicionado — artefatos de ambiente (não versionáveis)

- `backend/.venv/` — ambiente isolado, Python 3.13.15, 33 pacotes *(já coberto por `backend/.gitignore`)*
- `backend/baseline_freeze.txt` — congelamento das 33 dependências do baseline
- `C:\Naturecode\dsh-acl-reports\acl-report-93b21a23c8ef40a6907a0fb0f38669b7.jsonl` — relatório do
  diagnóstico de permissões *(fora do repositório)*
- `C:\Naturecode\dsh-acl-reports\acl-backup-a6d2da9d61d543479b0c37caa17558fa.json` + `.ps1` — backup e
  script de reversão do reparo de ACL *(fora do repositório)*

### Alterado — ambiente (fora do repositório)

- Permissões de `C:\Naturecode\stellSPY`: adicionada entrada de controle total para o usuário atual,
  porque faltava o direito de alterar o proprietário (`WRITE_OWNER`). Reversível pelos arquivos de
  backup acima. **Nenhum arquivo do projeto foi modificado.**
- Instalado `tzdata` **somente dentro do `.venv`** (workaround — ver ADR-003).

### Corrigido

- **Nada no código de produto.**

### Não alterado (confirmado)

- `backend/app/**` — nenhuma linha modificada
- `backend/tests/**` — nenhuma linha modificada
- `backend/requirements.txt` — **não** alterado (falta `tzdata`; correção pendente de aprovação)
- `supabase/migrations/**` — nenhuma migração criada ou executada
- `pwa/**`, `dashboard/**` — intocados
- `docs/2.0/**`, `docs/roboflow/**`, `docs/comercial/**` — intocados nesta sprint

---

## Registro de defeitos encontrados (não corrigidos)

| ID | Defeito | Severidade | Origem | Correção |
|----|---------|-----------|--------|----------|
| D-TZ | `tzdata` ausente em `requirements.txt` — suíte não coleta | Alta | execução | P-01 |
| D-VC | Repositório sem nenhum commit | **Crítica** | execução | P-02 |
| D-FP | `fpdf2`: `ln=` e `dest=` depreciados | Média | execução | Fase 0 |
| D-ENV | Sandbox não permite escrita em subpastas do workspace | Operacional | execução | ADR-001 |

---

## Histórico anterior (anterior a esta sprint)

| Data | Entregável | Natureza |
|------|-----------|----------|
| 2026-11-03 | `ANALISE_PROJETO.md` | análise estática — 14 achados |
| 2026-11-03 | `PLANO_STELLSPY_2.0.md` + `docs/2.0/*` (6 docs) | planejamento |
| 2026-11-03 | `docs/roboflow/*` (5 docs) | estudo de viabilidade |
| 2026-11-03 | `docs/execucao/*` (6 docs) | preparação de execução |
| 2026-11-03 | `docs/comercial/*` (6 docs) | preparação comercial |

> Nenhum desses pacotes alterou código de produto. Este é o primeiro registro com **execução real**.
