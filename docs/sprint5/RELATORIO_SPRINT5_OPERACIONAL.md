# Sprint 5 — Operação de campo e validação do MVP

**Data:** 2026-11-04
**Base:** Sprint 4 homologada no Supabase oficial `akvbtceshpsvsuacueaq`.
**Escopo desta entrega:** fechar as integrações entre PWA, API e banco no fluxo
obra → pedido → NF-e → conferência → evidências → divergências → dossiê, e provar
o caminho com testes reais. Sem deploy, sem push, sem tocar dados de clientes.

---

## 1. O que estava quebrado e foi corrigido

| # | Defeito | Efeito em campo | Correção |
|---|---------|-----------------|----------|
| 1 | `conferirNfe` chamava `fetch` direto, sem CSRF e sem tratar 401 | Tela de conferência por chave ficava em "não conectou" com sessão de usuário | Passou a usar o cliente comum `chamar()`; CSRF e 401 tratados como nas demais telas |
| 2 | Rota `conferir` exigia `ver_recebimento`, mas a API exige `criar_recebimento` | Tela abria para quem não podia executar e falhava no primeiro envio | Rota e item de menu alinhados à ação real do endpoint |
| 3 | Rota `pedido` exigia `gerenciar_pedido` | Fiscal não conseguia abrir o pedido para contar a carga | Detalhe do pedido passou a exigir `ver_recebimento`; escrita continua protegida |
| 4 | Rota `fotos` exigia `anexar_evidencia` | Auditoria não abria a tela para ver/baixar a prova | Rota exige `ver_evidencia`; controles de upload só aparecem para quem pode anexar |
| 5 | `id_cliente` do recebimento vivia só na memória da tela | Reload após perda de resposta criava uma segunda entrada | Rascunho persistido em `sessionStorage` por obra; limpo só após resposta do servidor |
| 6 | Chave de idempotência da foto era `uuid4()` novo a cada toque | Retry de upload criava evidência duplicada | Chave estável por arquivo dentro da tela; mapa isolado por recebimento |
| 7 | Falha de rede aparecia como `Failed to fetch` | Operador não sabia se a carga tinha sido registrada | `ErroApi` status 0 com texto em português dizendo que a operação não foi confirmada |
| 8 | Service worker usava cache-first puro | Correção de JS ficava presa no celular até limpar cache | Cache versionado (`v5`) + `stale-while-revalidate` para a casca |
| 9 | Dashboard reutilizava `DATABASE_URL` da API | Com RLS, listava zero obras e parecia banco vazio | `DASHBOARD_DATABASE_URL` separada; diagnóstico para com mensagem explícita quando a credencial não atravessa tenants |

Nenhuma funcionalidade crítica depende de mock: os testes de integração usam
PostgreSQL real com a role `stellspy_app`, RLS e `FORCE ROW LEVEL SECURITY`.

---

## 2. Fluxo completo coberto por teste

`backend/tests/integration/test_pedidos.py::test_fluxo_completo_de_recebimento_ponta_a_ponta`

1. Engenharia cria fornecedor e pedido (`PC-E2E`).
2. Engenharia vincula a NF-e ao pedido.
3. Fiscal registra a contagem da carga no portão.
4. Servidor calcula `completo` para a entrega e `atendido` para o pedido.
5. Reenvio com o mesmo `id_cliente` devolve o mesmo recebimento (`criado=false`).
6. Fiscal envia foto com `idempotency_key`.
7. Reenvio da mesma foto devolve a mesma evidência (`criada=false`).
8. Banco confirma `tenant_id`, `obra_id`, `recebimento_id` e autor corretos.
9. Download confere `X-Conteudo-Sha256` e o SHA-256 dos bytes; resposta é `no-store`.
10. Fiscal concilia a NF-e (`VERDE`).
11. Fiscal não exporta dossiê (403); engenharia exporta JSON e PDF.
12. Dossiê contém recebimento, evidência, cobertura e transições.
13. Construtora vizinha recebe 404 para pedido, recebimento, evidência e conteúdo.

---

## 3. Testes adicionados

### PWA (`pwa/js/*.test.js`, Vitest)

- CSRF em escrita, ausência em leitura, `credentials: include`.
- Falha de rede vira `ErroApi` status 0 com mensagem clara.
- `conferirNfe` envia CSRF e mantém o fluxo legado por `X-API-KEY`.
- `enviarEvidencia` carrega `idempotency_key`, `recebimento_id`, tipo/origem/captura.
- Listagens desembrulham `{itens}` uma única vez.
- `criarChavesDeEnvio`: mesma chave no retry, chaves distintas entre arquivos e
  entre entregas diferentes.

### Backend

- `test_dashboard_rls.py`: `stellspy_app` sem contexto vê 0 obras, sem
  superusuário e sem `BYPASSRLS`; credencial de back-office atravessa tenants.
- `test_fluxo_completo_de_recebimento_ponta_a_ponta`: caminho completo descrito acima.

---

## 4. Critérios de aceite

| Critério | Estado | Evidência |
|----------|--------|-----------|
| Nenhuma funcionalidade crítica depende de mocks | Atendido | integração com PostgreSQL real + role operacional |
| Recebimento completo de ponta a ponta | Atendido na API e contrato do PWA | teste E2E backend |
| Erros claros ao operador | Atendido | mensagens em português; falha de rede deixa de ser "Failed to fetch" |
| Uma construtora não acessa dados de outra | Atendido | RLS/FORCE + 404 cross-tenant no E2E |
| Evidências privadas e verificáveis | Atendido | binding tenant/obra/recebimento + SHA-256 no upload e download |
| Testes automatizados passam | Ver seção 5 | suíte backend e Vitest |
| Dispositivo real permanece pendente até execução física | Registrado | `ROTEIRO_TESTE_MANUAL_MOBILE.md` |

---

## 5. Resultados de teste

- Backend: `pytest -q -m "not supabase_local"` → **517 passed, 2 deselected**
  (137 s). O schema é recriado do zero e as **30 migrations** são aplicadas antes
  da suíte; os testes usam PostgreSQL real com a role `stellspy_app` e RLS/FORCE.
  Os 2 testes `supabase_local` (Storage real) ficam fora desta execução e já
  foram validados na Sprint 4.
- PWA: `npm test` → **16 passed** (2 arquivos, Vitest 2.1.9).

Comandos:

```powershell
# backend (na pasta backend)
..\.venv\Scripts\python.exe -m pytest -q -m "not supabase_local"

# PWA (na pasta pwa)
npm test
```

---

## 6. Bloqueios e pendências que permanecem

1. **Celular real / câmera:** roteiro pronto, execução física pendente. Exige
   Android com `adb reverse` (caminho de custo zero) ou HTTPS para iPhone.
2. **HTTPS em homologação:** sem domínio/certificado, iPhone não libera câmera e
   service worker; não contratar serviço — decisão do proprietário.
3. **`CORS_ALLOW_ORIGINS`:** precisa das origens exatas antes de qualquer deploy.
4. **Dashboard:** requer credencial de back-office (`DASHBOARD_DATABASE_URL`);
   a role da aplicação continua sem `BYPASSRLS` por decisão de segurança.
5. **Dados sintéticos remotos:** permanecem no projeto oficial; nenhuma remoção
   foi executada.
6. **Deploy/push:** fora de escopo por instrução; todos os commits são locais.

---

## 7. Commits locais desta entrega

| Hash | Assunto | Conteúdo |
|------|---------|----------|
| `45a190c` | `fix(pwa): falha de rede nao duplica recebimento nem evidencia` | Rascunho por `id_cliente`, chave estável por foto, erro de rede com status 0, `/conferir` com CSRF, rotas por ação correta, cache do service worker v4 → v5 |
| `8e6f803` | `fix(dashboard): exige credencial de back-office em vez de afrouxar RLS` | `DASHBOARD_DATABASE_URL`, falha explícita sem `BYPASSRLS`, diagnóstico em módulo sem pandas, teste de integração |
| `392cf19` | `test(e2e): cobre recebimento completo ate o dossie em PDF` | Fluxo ponta a ponta com hash, vínculo tenant/obra/recebimento, 403 do fiscal e 404 do outro tenant |
| este commit | `docs(sprint5): registra operacao de campo, roteiro mobile e testes` | Roteiro manual, este relatório, checklist de go-live e `PROGRESS.md` |

Todos são locais: **nenhum push, nenhum deploy**. Nenhuma migração foi criada ou
aplicada e nenhum dado remoto foi alterado nesta sprint.

Ressalva de registro: o corpo de `45a190c` diz "service worker v6"; o valor real
no código é `steelspy-v5` (a versão anterior era `v4`). O código está correto — o
erro é só de redação no commit, corrigido aqui em vez de reescrever história.
