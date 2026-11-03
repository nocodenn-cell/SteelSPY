# STATUS DE EXECUÇÃO — stellSPY 2.0

> **Atualizado em:** 2026-11-03 · **Sprint:** Engenharia 0 (ambiente + baseline)
> **Regra deste documento:** distinguir sempre `PLANEJADO` · `IMPLEMENTADO` · `TESTADO` ·
> `APROVADO` · `BLOQUEADO`. Nada é marcado como concluído sem evidência em `EVIDENCIAS.md`.

---

## 1. Resumo executivo

| Pergunta | Resposta |
|----------|----------|
| O ambiente de execução funciona? | **Sim** — reparado e testado |
| Existe baseline executável? | **Sim** — 69/69 testes, 1,75 s |
| O repositório roda out-of-the-box? | **Não** — falta `tzdata` |
| Existe controle de versão utilizável? | **Não** — zero commits |
| A Fase 0 está autorizada? | **Não** — gate fechado |
| Código de produto alterado? | **Não** — nenhuma linha |

**Conclusão:** o projeto está **melhor do que a análise estática sugeria** (o núcleo funciona: 69/69) e
**mais frágil do que parecia** (não há um único commit). Antes de escrever a primeira linha da Fase 0,
é preciso versionar o que existe.

---

## 2. Fases do roadmap

| Fase | Escopo | Estado | Evidência |
|------|--------|--------|-----------|
| **Pré-0** | Ambiente, baseline, revisão de arquitetura | `TESTADO` | `EVIDENCIAS.md` E1–E8 |
| **Fase 0** | Fundação SaaS (tenant, RBAC, RLS, testes) | `PLANEJADO` + `BLOQUEADO` (G-06) | `PLANO_EXECUCAO_FASE0.md` |
| **Fase 1** | Pipeline de evidências | `PLANEJADO` + `BLOQUEADO` (G-06) | `PLANO_PIPELINE_EVIDENCIAS.md` |
| **Fase 2** | Pedidos e NF-e | `PLANEJADO` | `PLANO_STELLSPY_2.0.md` |
| **Fase 3** | Ocorrências e retenção | `PLANEJADO` | idem |
| **Fase 4** | Visão computacional | `PLANEJADO` + `BLOQUEADO` (gate comercial) | `RFDETR_EXPERIMENT_PROTOCOL.md` |
| **Comercial** | 10 entrevistas | `BLOQUEADO` — 0/10 | `DECISAO_GO_NO_GO_COMERCIAL.md` |

---

## 3. Detalhamento da Sprint 0

### 3.1 Ambiente

| Item | Estado | Detalhe |
|------|--------|---------|
| Diagnóstico de ACL | `TESTADO` | `WRITE_OWNER=false` → concedido; verificado |
| Reversão do reparo | `IMPLEMENTADO` | backup + comando de rollback em `C:\Naturecode\dsh-acl-reports\` |
| Execução de comandos | `TESTADO` | PowerShell 7.6.9, FullLanguage |
| Escrita em subpastas (confinado) | `BLOQUEADO` | limite do sandbox; exige execução autorizada |
| Docker | `TESTADO` | 29.8.1, engine linux; acessível fora do confinamento |
| PostgreSQL para testes | `TESTADO` | imagens `postgres:16-alpine` / `17-alpine` já locais |
| `psql` nativo | `BLOQUEADO` | ausente — irrelevante com container |

### 3.2 Baseline

| Item | Estado | Detalhe |
|------|--------|---------|
| `.venv` criado | `IMPLEMENTADO` | Python 3.13.15, 33 pacotes |
| Dependências declaradas instaladas | `TESTADO` | `pip install` exit 0 |
| Congelamento | `IMPLEMENTADO` | `backend/baseline_freeze.txt` |
| Suíte executada | `TESTADO` | **69/69 aprovados** |
| Cobertura medida | `BLOQUEADO` | `pytest-cov` não declarado |
| Testes de HTTP | `BLOQUEADO` | nenhum `TestClient` no projeto |
| Testes de banco | `BLOQUEADO` | sem fixture de DB |

### 3.3 Defeitos confirmados por execução

| ID | Defeito | Antes (auditoria) | Agora |
|----|---------|-------------------|-------|
| D-TZ | `tzdata` ausente quebra coleta | hipótese (M6) | **CONFIRMADO** |
| D-FP | `fpdf2` `ln=` e `dest=` depreciados | hipótese (B8) | **CONFIRMADO** (24 warnings) |
| D-VC | Repositório sem commits | não previsto | **NOVO — crítico** |
| D-ENV | `WRITE_OWNER` ausente no workspace | não previsto | **NOVO — resolvido** |

### 3.4 Achados que mudam o plano

| # | Achado | Impacto |
|---|--------|---------|
| 1 | **Zero commits no Git** | Sem ponto de restauração; toda implementação é irreversível até ADR-005 ser aprovada |
| 2 | `tzdata` quebra a suíte | O repositório não é executável out-of-the-box — contradiz o `README` inexistente e o `docs/` |
| 3 | Sandbox não permite escrita em subpastas | Todo trabalho de implementação exigirá aprovação por comando |
| 4 | Imagens PostgreSQL já presentes | Fase 0 pode testar RLS de verdade **sem custo e sem download** |
| 5 | 69/69 verdes | O núcleo está saudável — preservá-lo é viável, não heroico |

---

## 4. O que NÃO foi feito (e por quê)

| Não feito | Motivo | Gate |
|-----------|--------|------|
| Criar `.gitignore` | Exige autorização (ADR-005) | G-04 |
| Commit inicial | Idem | G-04 |
| Corrigir `requirements.txt` (`tzdata`) | Mudança de produto antes da aprovação | P-01 |
| Escolher role de aplicação / RLS | Fase 0 não autorizada | G-06 |
| Implementar upload | Fase 1 não autorizada | G-06 |
| Instalar `rfdetr` | Trilha B não iniciada; gate de licença não existe | G-07 |
| Qualquer chamada à Roboflow | Gate de privacidade não documentado | G-08 |
| Escrever testes novos | Dependem de código da Fase 0 | G-06 |

---

## 5. Estado dos entregáveis desta sprint

| Documento | Estado | Conteúdo real |
|-----------|--------|---------------|
| `STATUS_EXECUCAO.md` | `IMPLEMENTADO` | este arquivo |
| `CHANGELOG.md` | `IMPLEMENTADO` | mudanças efetivas |
| `DECISOES_TECNICAS.md` | `IMPLEMENTADO` | 8 ADRs |
| `MATRIZ_GO_NO_GO.md` | `IMPLEMENTADO` | revisão com gates reais |
| `RELATORIO_TESTES.md` | `IMPLEMENTADO` | 69/69 + lacunas |
| `EVIDENCIAS.md` | `IMPLEMENTADO` | 8 evidências executadas |
| `PROXIMOS_PASSOS.md` | `IMPLEMENTADO` | 12 ações priorizadas |

---

## 6. Veredito da sprint

| Critério da missão | Resultado |
|--------------------|-----------|
| A. Verificar ambiente | ✅ `TESTADO` — reparado com procedimento autorizado |
| B. Obter baseline executável | ✅ `TESTADO` — 69/69, com ressalva de `tzdata` |
| C. Revisar arquitetura e migrações | ✅ `IMPLEMENTADO` — em `PLANO_EXECUCAO_FASE0.md` §2 |
| D. Confirmar plano de migração | ⏸️ **aguarda aprovação** |
| E. Validar critérios de aceite | ✅ `IMPLEMENTADO` — AC0.1–AC0.10, AC1.1–AC1.13 |
| F. Relatório de GO/NO-GO | ✅ **NO-GO para a Fase 0 neste momento** — 2 gates fechados |

**Próxima decisão necessária:** autorizar ADR-005 (`.gitignore` + commit inicial) e P-01
(`tzdata` no `requirements.txt`). São 2 ações pequenas que destravam todo o resto.
