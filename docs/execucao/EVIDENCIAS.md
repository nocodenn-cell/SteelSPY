# EVIDÊNCIAS — Sprint de Engenharia 0 (Ambiente e Baseline)

> Documento de **prova**. Cada item traz o comando executado, a saída observada e o que ela autoriza
> concluir. Nenhum resultado aqui é estimado: todos foram produzidos por execução real nesta máquina
> em **2026-11-03**.
>
> Legenda de estado: `PLANEJADO` · `IMPLEMENTADO` · `TESTADO` · `APROVADO` · `BLOQUEADO`

---

## E1 — Disponibilidade do ambiente de execução

**Estado: TESTADO**

### E1.1 Sintoma original

| Tentativa | Resultado |
|-----------|-----------|
| `pwsh -Command "Get-ChildItem -Force"` (×4, turnos anteriores) | `Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(C:\Naturecode\stellSPY)` |
| `pwsh -Command "python --version"` | mesmo erro |

O erro ocorria **antes** de qualquer comando rodar — falha na preparação do sandbox, não no comando.

### E1.2 Diagnóstico autorizado

Procedimento: skill `diagnose-windows-sandbox-acl`, executada uma única vez fora do confinamento.
Script: `C:\Users\aoliv\AppData\Local\Temp\dsh-acl-skill-zJMTJ5\scripts\diagnose-windows-sandbox-acl.ps1`

```
VERDICT=PRECONDITION
OBJECT=C:\Naturecode\stellSPY  OWNER=<usuário>  IS_CURRENT_USER=True
  WRITE_DAC=True  WRITE_OWNER=False
GRANTED C:\Naturecode\stellSPY SID=<usuário>
verification grant: before={writeOwner:false, writeDac:true}
                    after ={writeOwner:true,  writeDac:true}   status=verified
SUMMARY FIXED=0 GRANTED=1 REFUSED=0 RESTORED=0
RECAP nextAction=verify_original_confined_operation
```

**Causa raiz:** faltava `WRITE_OWNER` no diretório raiz do workspace. Sem esse direito, o harness não
conseguia provisionar a concessão de escrita e abortava.

**Reversão disponível** (arquivo de backup criado pelo próprio procedimento):

```
pwsh -NoProfile -File 'C:\Naturecode\dsh-acl-reports\acl-backup-a6d2da9d61d543479b0c37caa17558fa.json.ps1' `
  -Path 'C:\Naturecode\stellSPY' -AllowRoot 'C:\Naturecode\stellSPY' `
  -Restore 'C:\Naturecode\dsh-acl-reports\acl-backup-a6d2da9d61d543479b0c37caa17558fa.json'
```

Relatório completo: `C:\Naturecode\dsh-acl-reports\acl-report-93b21a23c8ef40a6907a0fb0f38669b7.jsonl`

### E1.3 Efeito do reparo

| Operação | Antes | Depois do reparo |
|----------|-------|------------------|
| Qualquer `pwsh` | ❌ falhava na preparação | ✅ **executa** |
| `Get-Location` | — | `C:\Naturecode\stellSPY` |
| `$ExecutionContext.SessionState.LanguageMode` | — | `FullLanguage` |
| `$PSVersionTable.PSVersion` | — | `7.6.9` |
| Escrita em `backend\` (confinado) | — | ❌ **ainda negada** (ver E2) |

### E1.4 Segunda camada: escrita em subpastas continua bloqueada

```
New-Item -ItemType Directory -Path '.\_probe_dir'   → Access to the path 'C:\Naturecode\stellSPY\backend\_probe_dir' is denied.
Set-Content -Path '.\_probe.txt'                    → Access to the path 'C:\Naturecode\stellSPY\backend\_probe.txt' is denied.
```

ACL do `backend` (todas herdadas, nenhuma negação explícita):

```
BUILTIN\Administradores        Allow FullControl
NT AUTHORITY\SYSTEM            Allow FullControl
BUILTIN\Usuários               Allow ReadAndExecute, Synchronize
NT AUTHORITY\Usuários autenticados  Allow Modify, Synchronize
```

ACL da raiz após o reparo (não herdadas):

```
Todos                                   Deny  DeleteSubdirectoriesAndFiles
S-1-4-295149086-610485311               Allow DeleteSubdirectoriesAndFiles, Write, Delete, Synchronize
Damatta\Damatta                         Allow FullControl        ← adicionado pelo reparo
```

**Interpretação:** a concessão de escrita do sandbox (`S-1-4-…`, SID restrito) existe **apenas na
raiz**, sem herança para subpastas. O processo confinado carrega esse SID restrito, e o direito
herdado de "Usuários autenticados" não o satisfaz em `backend\`.

**Classificação:** limite do confinamento, **não** defeito do projeto. Não é contornável por ACL do
workspace — exige execução autorizada fora do confinamento.

---

## E2 — Toolchain disponível

**Estado: TESTADO**

| Ferramenta | Situação | Versão / observação |
|------------|----------|---------------------|
| PowerShell | ✅ | 7.6.9, FullLanguage |
| Python | ✅ | 3.13.15 (`C:\Users\aoliv\AppData\Local\Programs\Python\Python313`) |
| Git | ✅ | 2.55.0.windows.3 |
| Node.js | ✅ | presente |
| npm / pnpm | ✅ | presentes |
| Docker (client) | ✅ | 29.8.1 |
| Docker (server) | ⚠️ | 29.8.1, engine linux — **acessível só fora do confinamento** (named pipe bloqueado) |
| psql | ❌ **ausente** | sem cliente PostgreSQL nativo |
| `.venv` no backend | ❌ **não existia** | dependências não instaladas |
| Dependências globais | ⚠️ | 7 pacotes; só `pillow` relevante |

**Consequência:** o projeto **nunca havia sido executado** neste ambiente.

---

## E3 — Estado do controle de versão

**Estado: TESTADO — achado crítico**

```
git status --porcelain
?? .cursor/   ?? ANALISE_PROJETO.md   ?? PLANO_STELLSPY_2.0.md
?? backend/   ?? dashboard/   ?? docs/   ?? pwa/   ?? supabase/

git rev-parse --abbrev-ref HEAD
fatal: ambiguous argument 'HEAD': unknown revision or path not in the working tree.
```

| Fato | Consequência |
|------|--------------|
| Repositório existe (`.git/HEAD` = `refs/heads/main`) | — |
| **Zero commits** | Não há ponto de restauração |
| **Tudo não rastreado** | Nenhuma alteração é reversível por Git |
| Sem `.gitignore` na raiz | `pwa/node_modules` (1.082 arquivos) seria commitado |

**Risco:** qualquer implementação da Fase 0 sem commit inicial é irreversível. Este é um bloqueio real,
não uma formalidade.

---

## E4 — Baseline de dependências

**Estado: TESTADO**

Criação de ambiente isolado (execução autorizada fora do confinamento):

```
python -m venv .venv                      → venv criado: True
.\.venv\Scripts\python.exe --version      → Python 3.13.15
pip install -r requirements.txt -r requirements-dev.txt
                                          → install exit: 0
pip freeze                                → 33 pacotes
```

Arquivo de congelamento gerado: `backend/baseline_freeze.txt` (33 linhas).

> Observação: `backend/.gitignore` já contém `.venv/`, portanto o ambiente criado não polui o
> repositório.

---

## E5 — Falha de teste reproduzida (defeito real confirmado)

**Estado: TESTADO**

Primeira execução da suíte:

```
pytest exit: 2
ERROR tests/test_relatorio_semanal.py
E   zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key America/Sao_Paulo'
!!! Interrupted: 1 error during collection !!!
```

Causa: `app/services/relatorio_semanal.py:20` executa `ZoneInfo("America/Sao_Paulo")` **em tempo de
import**, e o pacote `tzdata` **não está declarado** em `requirements.txt`.

| Aspecto | Registro |
|---------|----------|
| Previsto na auditoria estática? | Sim (`ANALISE_PROJETO.md`, achado **M6**) |
| Confirmado por execução? | **Sim, agora** |
| Efeito | Suíte inteira não coleta; job de relatório quebraria em ambiente Windows limpo |
| Correção aplicada nesta sprint | **Nenhuma no código** — apenas `pip install tzdata` no `.venv` |

**Isso é evidência de defeito, não correção.** A correção em `requirements.txt` depende de aprovação
(item P-01 de `PROXIMOS_PASSOS.md`).

---

## E6 — Baseline verde após workaround de ambiente

**Estado: TESTADO**

```
$ .\.venv\Scripts\python.exe -m pytest -q
69 passed, 24 warnings in 1.75s
pytest exit: 0

$ .\.venv\Scripts\python.exe -m pytest --collect-only -q
69 tests collected in 0.99s
```

**69 testes coletados = 69 testes aprovados.** Bate exatamente com a previsão estática anterior
(65 funções, 2 parametrizadas com 3 casos cada → 69).

### E6.1 Warnings observados (24)

| Origem | Mensagem | Achado da auditoria |
|--------|----------|---------------------|
| `laudo_pdf.py:314,342,368,409,162` | `The parameter "ln" is deprecated since v2.5.2` | B8 confirmado |
| `laudo_pdf.py:409` | `"dest" parameter is deprecated since v2.2.0 and will be removed` | novo |
| `laudo_pdf.py` (fonte) | — | Texto com problema de encoding na saída do console (`t�cnico`) — apenas exibição de console, não corrupção no PDF |

---

## E7 — Disponibilidade de PostgreSQL para testes da Fase 0

**Estado: TESTADO**

| Verificação | Resultado |
|-------------|-----------|
| `docker info` confinado | ❌ `permission denied … npipe:////./pipe/dockerDesktopLinuxEngine` |
| `docker version` fora do confinamento | ✅ `client=29.8.1 server=29.8.1` |
| Engine | ✅ `os=linux` |
| Imagens PostgreSQL locais | ✅ `postgres:16-alpine`, `postgres:17-alpine`, `postgres:17` |
| Download necessário | **Nenhum** — imagens já presentes |
| `psql` nativo | ❌ ausente (irrelevante se usar container) |

**Consequência:** a estratégia de teste da Fase 0 pode usar **container efêmero com imagem já
presente**, sem custo e sem download. Requer execução autorizada fora do confinamento (named pipe).

⚠️ **Cuidado registrado:** existem containers de **outro projeto** em execução nesta máquina
(`venddi-pg`, pilha `supabase_*_venddi-physical-inventory-*`). Nenhum deles pode ser tocado. O teste
da Fase 0 deve criar container próprio, com nome exclusivo (ex.: `stellspy-test-pg`) e porta isolada.

---

## E8 — O que **não** foi testado

Registro explícito para evitar conclusão indevida:

| Item | Motivo |
|------|--------|
| Rotas HTTP (`/conferir`, `/override`, `/laudo.pdf`) | Não há `TestClient`; exigiria banco |
| Migrações SQL aplicadas | Sem banco disponível no confinamento |
| Isolamento multi-tenant | Fase 0 não iniciada (gate de autorização) |
| Pipeline de evidências | Fase 1 não autorizada |
| RF-DETR / visão computacional | Trilha B, não iniciada |
| Interface PWA | Sem execução de navegador |
| Cobertura de código | `pytest-cov` não instalado; não declarado no projeto |

---

## Índice de evidências

| ID | Assunto | Estado | Verificação |
|----|---------|--------|-------------|
| E1 | Ambiente de execução (ACL) | TESTADO | executado |
| E2 | Toolchain | TESTADO | executado |
| E3 | Controle de versão | TESTADO | executado |
| E4 | Dependências / venv | TESTADO | executado |
| E5 | Defeito `tzdata` | TESTADO | executado |
| E6 | Suíte 69/69 verde | TESTADO | executado |
| E7 | PostgreSQL em container | TESTADO | executado |
| E8 | Limites do que não foi testado | — | declaração |
