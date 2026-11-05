# Riscos restantes — Sprint 6 (piloto operacional)

**Data:** 2026-11-05 (revisado após o push; base de 2026-11-04)
**Escopo:** piloto controlado com uma construtora, infraestrutura existente,
orçamento adicional R$ 0,00. Branch publicada sem deploy, sem migration remota
e sem alteração de dados reais.

Legenda de impacto: **A** = bloqueia o piloto; **B** = degrada a operação;
**C** = higiene/técnico. Probabilidade: alta/média/baixa.

---

## 1. Bloqueios declarados

| ID | Risco | Prob. | Impacto | Situação em 2026-11-05 | Próximo passo |
|----|-------|-------|---------|------------------------|---------------|
| R1 | Câmera/permissões nunca testadas em aparelho real | alta | A | **Não comprovado.** Só há teste automatizado de contrato; o roteiro físico não foi executado | Executar `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md` com capturas |
| R2 | ADB ausente na máquina de desenvolvimento | alta | A | `preparar_android.py` retornou exit 2 ("ADB NÃO ENCONTRADO") | Instalar `platform-tools` (custo zero) ou usar aparelho com ADB já instalado |
| R3 | Backup/restauração não ensaiados | média | A | Procedimento escrito; **nenhum dump/restore executado** | Ensaio em banco descartável antes do GO |
| R4 | `CORS_ALLOW_ORIGINS` de produção ainda não definido | média | A na publicação | **Piloto local fechado:** `localhost` e `127.0.0.1:8080`, preflight de `POST`/`DELETE` e 21 testes; a API recusa config ambígua no boot | Informar a origem HTTPS exata no ambiente publicado |
| R5 | `NFE_IO_MOCK=1` no ambiente local | alta | A se usado no piloto | Auditoria: AVISO | `NFE_IO_MOCK=0` e token real, ou fluxo manual de NF-e explicitamente aceito |
| R6 | Dashboard sem credencial de banco **ou sem senha de entrada** | média | B (A se exposto) | **Configurado em 2026-11-05:** role `stellspy_dashboard` com LOGIN por senha dedicada, `DASHBOARD_DATABASE_URL` e `DASHBOARD_TENANT_ID` (HML Alfa), senha de entrada de 32 chars; painel sobe e autentica headless. No HEAD `c2cdfd2`, `DASHBOARD_PASSWORD` vazia fazia o painel abrir sem login; **correção local** exige ≥ 12 | Publicar a correção antes de expor o painel; trocar o tenant provisório ao cadastrar a construtora do piloto |

Qualquer R1–R6 aberto no momento da publicação é **NO-GO** conforme
`CHECKLIST_PUBLICACAO.md`.

---

## 2. Riscos operacionais e técnicos

| ID | Risco | Prob. | Impacto | Mitigação implementada | O que ainda falta |
|----|-------|-------|---------|------------------------|-------------------|
| R7 | Queda de rede durante recebimento duplica carga | média | B | `id_cliente` persistido por 4 h + unicidade no banco; retry devolve `criado=false` | Provar em campo (CT-03 do roteiro) |
| R8 | Reenvio de foto duplica evidência | média | B | Chave de idempotência estável por arquivo + `(recebimento_id, sha256)` | Provar em campo (CT-05) |
| R9 | Operador acredita que a operação foi concluída offline | média | B | Estados `pendente/confirmada/falhou` visíveis; texto explícito de que nada conclui sem resposta do servidor | **Não há fila offline**; não prometer suporte offline completo |
| R10 | Rascunho de recebimento expira ou é limpo pelo navegador | média | B | TTL de 4 h, escopo por obra, fallback em memória | Operador deve registrar de novo; não é perda silenciosa |
| R11 | Credencial administrativa vaza para a aplicação | baixa | A | Auditoria bloqueia `DATABASE_URL` com `postgres.*`; dashboard exige `stellspy_dashboard`; migration fail-closed | Revisar env de cada processo no deploy |
| R12 | Papel `auditor` ganha escrita por engano | baixa | A | Matriz global × obra; teste de 10 passos prova 403 em conciliar/decidir | Reexecutar a suíte em toda mudança de RBAC |
| R13 | Dashboard lê outro tenant | baixa | A | Role sem `BYPASSRLS`, sem escrita, presa a `DASHBOARD_TENANT_ID`; 8 testes de isolamento + prova no banco oficial (Alfa vê 1, Beta vê outra, sem contexto 0) | Repetir a prova no host publicado |
| R14 | Rotação da senha da role do dashboard é manual | média | C | Migration 31 aplicada com senha gerada localmente; reexecutar com novo `STELLSPY_DASHBOARD_PASSWORD` é o caminho de rotação | Definir periodicidade e responsável |
| R15 | Senha administrativa do Supabase ainda é a usada no destravamento | média | C | Fora do repositório; auditoria não encontra vazamento | Rotacionar após a janela de homologação |
| R16 | Sem pipeline de CI | alta | C | Comandos de teste documentados; suíte local cobre 31 migrations | Configurar CI quando houver decisão de infraestrutura |
| R17 | Dados sintéticos permanecem no projeto oficial | alta | C | Nada foi removido, por instrução | Decisão do proprietário; remoção exige autorização |
| R18 | iPhone/Safari sem HTTPS interno | alta | B para iPhone | Android tem caminho `adb reverse`; HTTPS exige decisão de domínio | Se o piloto for Android, não bloqueia |
| R19 | Região única / sem HA no Supabase | baixa | B | Backup manual documentado | Aceitar risco ou contratar redundância (fora do orçamento) |
| R20 | Varredura de segredos é heurística | média | C | Detecta JWT `service_role`, PEM, senha em URL, `.env`, atribuição de segredo; exceção explícita `credencial-de-exemplo`; 8 testes do scanner | Não substitui cofre de segredos nem revisão humana |
| R21 | Cold start de ~1 min no Render Free | alta | B | Plano gratuito documentado; serviço dorme após 15 min | Abrir o PWA antes do uso ou aprovar keep-alive (consome a franquia) |
| R22 | Supabase Free pausa após 7 dias de baixa atividade | média | B | Dados preservados; retomada manual em até 1 ano | Uso diário no piloto ou lembrete de retomada |
| R23 | Sem backup automático no Supabase Free | alta | A | Procedimento manual documentado | `pg_dump` antes do piloto e periodicamente; ensaiar restauração |
| R24 | 500 MB de banco, 1 GB de Storage e 5 GB de egress no Free | média | B | Fotos normalizadas; Storage privado | Monitorar volume de evidências e dossiês |
| R25 | Keep-alive consome quase toda a franquia de 750 h | média | C | Um único serviço; 730 h/mês < 750 h | Decisão explícita do proprietário; monitorar consumo |
| R26 | Tenant provisório do dashboard é sintético | baixa | B | `DASHBOARD_TENANT_ID` aponta para a `HML Construtora Alfa`; é variável de ambiente, sem mudança de schema ou role | Trocar pelo UUID da construtora do piloto antes de abrir o painel a ela |

---

## 3. O que **não** está comprovado

- Câmera, permissão do navegador e comportamento de rede em aparelho real.
- Service worker em HTTPS de produção (o teste local usa localhost).
- Restauração de backup e tempo de recuperação.
- Desempenho com volume de campo (fotos grandes, many NFs).
- Comportamento do Supabase sob indisponibilidade parcial (o 503 é testado com
  sessão quebrada, não com queda real do provedor).
- Funcionamento do dashboard com a role `stellspy_dashboard` no projeto remoto
  (o isolamento foi provado no PostgreSQL local).

## 4. Riscos aceitos conscientemente

- **Sem fila offline.** O app é honesto: operação não confirmada aparece como
  falha/pendente. O piloto precisa de conectividade no momento do registro.
- **Sem preço em R$.** O dashboard mede volume e severidade, não valor financeiro.
- **Dossiê não é laudo.** O PDF carrega ressalva explícita.
- **Uma região.** A disponibilidade segue o plano contratado do Supabase.
