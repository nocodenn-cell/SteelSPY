# Relatório — Sprint 6: piloto operacional

**Data:** 2026-11-04
**Missão:** preparar o SteelSPY para um piloto controlado com uma construtora,
usando a infraestrutura existente e orçamento adicional de R$ 0,00.
**Restrições cumpridas:** nenhum push, deploy, operação destrutiva, remoção de
dados de homologação, exposição de credencial ou alteração em produção.

---

## 1. Resultado em uma linha

Todas as cinco etapas foram implementadas e cobertas por testes automatizados.
A suíte fechou em **570 testes de backend** (2 deselected) e **35 de PWA**. O
piloto **não está liberado para GO** por três bloqueios que dependem de execução
física ou de decisão do proprietário: câmera em aparelho real, ensaio de
backup/restauração e configuração das origens de CORS/NF-e no ambiente de
publicação. Nada foi publicado.

---

## 2. Etapa 1 — Segurança do dashboard

**Problema:** o painel podia ser apontado para uma credencial de back-office
(superusuário ou com `BYPASSRLS`), enxergando mais de uma construtora.

**Solução de menor privilégio:**

- `supabase/migrations/20261104170000_dashboard_role.sql` cria
  `stellspy_dashboard` com `NOSUPERUSER`, `NOBYPASSRLS`, `NOINHERIT`,
  `NOCREATEDB`, `NOCREATEROLE`, `NOLOGIN` por padrão e `SELECT` apenas em
  `construtoras, obras, nfe_logs, nfe_itens, especificacoes`. A senha só é
  aplicada quando `STELLSPY_DASHBOARD_PASSWORD` chega pelo runner — nenhum
  segredo no repositório. A migration é *fail-closed*: recusa role
  pré-existente com `rolsuper` ou `rolbypassrls` e senha com menos de 12
  caracteres.
- `dashboard/app.py` deixou de cair em `DATABASE_URL`: exige
  `DASHBOARD_DATABASE_URL` e `DASHBOARD_TENANT_ID`.
- `dashboard/diagnostico.py` recusa credencial superusuário, `BYPASSRLS` ou com
  escrita em `obras`, e mostra construtora + obras visíveis.
- `dashboard/leitura.py` separa a leitura (sem pandas) para ser testável;
  `queries.py` permanece como wrapper fino.
- `apply_migrations.py` injeta as duas senhas de role e impede que
  `stellspy_dashboard` execute DDL.

**Testes:** `test_dashboard_rls.py` (8 testes em banco real) prova atributos da
role, grants, isolamento A/B, zero linhas sem contexto, escrita negada e recusa
de credencial administrativa.

---

## 3. Etapa 2 — Resiliência do PWA

| Cenário | Comportamento implementado | Evidência |
|---------|----------------------------|-----------|
| Queda de rede no recebimento | `id_cliente` persistido antes do envio; retry devolve `criado=false` | unicidade `uq_recebimentos_id_cliente`; E2E da Sprint 5 reexecutado |
| Recarga da página | rascunho em `localStorage` por obra, TTL de 4 h, tolerância de +60 s de relógio | `pwa/js/rascunho.js` + 9 testes |
| Fechamento do navegador | rascunho sobrevive ao fechamento da aba (não é `sessionStorage`) | idem |
| Foto reenviada | chave de idempotência estável por arquivo + `(recebimento_id, sha256)` | `uq_evidencias_idempotencia`; teste de upload repetido |
| Estado da operação | faixa visível com `pendente`, `confirmada` ou `falhou`, com horário | `pwa/js/operacoes.js` + 10 testes |
| Rede caiu | operação sem resposta do servidor fica `falhou`/`pendente`, nunca "concluída" | idem |

**Limite explícito:** não existe fila offline. O app não promete operar sem
conexão; ele promete não mentir sobre o estado. Essa frase está no roteiro
mobile e no relatório de riscos (R9).

---

## 4. Etapa 3 — Ambiente mobile

- `backend/scripts/preparar_android.py` verifica ADB, lista dispositivos,
  valida `adb reverse` para 8000/8080 e orienta câmera/permissões; 9 testes
  unitários cobrem os caminhos de sucesso e falha.
- Execução nesta máquina: **exit 2 — "ADB NÃO ENCONTRADO"**. Portanto **nenhum
  teste de aparelho real foi aprovado**. Android via `adb reverse` continua
  sendo o caminho de custo zero; iPhone exige HTTPS.
- Roteiro físico atualizado em
  `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md` com CT-03 (retry), CT-03b
  (reload/fechamento) e CT-05 (fotos e estados).

---

## 5. Etapa 4 — Fluxo de piloto

Um único teste em banco real percorre os dez passos:
`backend/tests/integration/test_pedidos.py::test_piloto_percorre_os_dez_passos_ate_a_consulta_autorizada`.

| # | Passo | O que o teste comprova |
|---|-------|------------------------|
| 1 | Autenticação | login do engenheiro, `papel_global` correto e CSRF |
| 2 | Construtora/obra autorizadas | `/auth/obras` devolve só a obra do tenant, com ações `gerenciar_pedido` e `exportar_dossie` |
| 3 | Consulta ao pedido | pedido `PC-PILOTO` visível na obra |
| 4 | Associação da NF-e | vínculo da NF-e ao pedido; `/nfe` lista o documento |
| 5 | Registro do recebimento | 800 m recebidos contra 1.000 m faturados → `parcial` |
| 6 | Fotos | upload 201; download com o mesmo SHA-256 |
| 7 | Divergência | item marcado `VERMELHO`, severidade técnica propagada |
| 8 | Conciliação | fonte de verdade física = recebimento |
| 9 | Dossiê PDF | 200, `%PDF`, `X-Dossie-Id`, `no-store` |
| 10 | Consulta autorizada | auditor lê pedido, recebimento, dossiê e PDF; escrita devolve 403 |

---

## 6. Etapa 5 — Preparação para publicação

- **CORS:** `app/cors.py` valida origens exatas no boot e derruba a aplicação
  com `*`, `null`, esquema inválido, caminho, query ou credencial embutida.
  16 testes. `CORS_ALLOW_ORIGINS` vazio continua permitido (mesma origem).
- **Auditoria de segredos:** `backend/scripts/auditar_publicacao.py` varre
  arquivos versionados e o `.env`: JWT com `service_role`, chave PEM, URL de
  produção com senha, `.env` versionado, atribuições de segredo e variáveis
  críticas. Resultado no repositório: **0 bloqueios, 5 avisos**; 17 testes.
  A exceção `credencial-de-exemplo` cobre fixtures sintéticas do próprio teste.
- **Documentos entregues:**
  `CHECKLIST_PUBLICACAO.md` (variáveis por processo, passos, GO/NO-GO),
  `DEPLOY_HOMOLOGACAO.md` (runbook sem execução),
  `PROCEDIMENTO_BACKUP_RESTAURACAO.md` (dump/restore e critérios de aceite) e
  `RELATORIO_RISCOS.md` (R1–R20).
- **Critério GO:** R1–R5 fechados; qualquer um aberto é **NO-GO**.

---

## 7. Evidência das suítes finais

```
backend: 570 passed, 2 deselected, 245 warnings in 180.09s
         schema recriado + 31 migrations aplicadas
PWA:     35 passed em 4 arquivos
         (operacoes 10, rascunho 9, api 11, telas_recebimento 5)
```

Os 2 testes deselectados são os marcados `supabase_local`, que exigem a stack
Supabase local e não fazem parte do gate padrão.

---

## 8. Commits locais

Organizados por entrega; nenhum foi enviado ao remoto.

| Grupo | Commit | Conteúdo |
|-------|--------|----------|
| 1 | `be28e00` | Dashboard de menor privilégio: migration 31, runner, dashboard, testes de isolamento, docs |
| 2 | `772d1ff` | PWA resiliente: rascunho, estados de operação, tela de recebimento, Vitest, roteiro |
| 3 | `78c92fb` | Preparação Android: script e testes |
| 4 | `5127fe8` | Teste dos dez passos do piloto |
| 5 | `70745e3` | CORS, auditoria de publicação, checklist/runbook/backup, PROGRESS e este relatório |

---

## 9. Riscos restantes

O detalhamento está em `RELATORIO_RISCOS.md`. Os que impedem o GO hoje:

1. **R1/R2 — aparelho real:** câmera, permissões e rede móvel não exercitados;
   ADB ausente nesta máquina.
2. **R3 — backup:** procedimento escrito, nenhum restore executado.
3. **R4 — CORS:** origem exata do PWA ainda não definida.
4. **R5 — NF-e:** `NFE_IO_MOCK=1` no ambiente local.
5. **R6 — dashboard:** `DASHBOARD_DATABASE_URL` e `DASHBOARD_TENANT_ID` não
   configurados onde o painel será publicado; a migration 31 ainda não foi
   aplicada no projeto oficial.

Riscos aceitos conscientemente: sem fila offline, sem valor financeiro no
dashboard, dossiê não é laudo, região única.

---

## 10. O que não foi feito (por restrição ou por bloqueio)

- Nenhum push, deploy ou publicação.
- Nenhuma migration aplicada no projeto oficial; o remoto segue com 30.
- Nenhum dado de homologação removido.
- Nenhum teste de aparelho real aprovado.
- Nenhuma credencial exibida ou gravada no repositório.
