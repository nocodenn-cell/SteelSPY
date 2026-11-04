# Riscos restantes — Sprint 6 (piloto operacional)

**Data:** 2026-11-04
**Escopo:** piloto controlado com uma construtora, infraestrutura existente,
orçamento adicional R$ 0,00. Sem push, deploy ou alteração de dados reais.

Legenda de impacto: **A** = bloqueia o piloto; **B** = degrada a operação;
**C** = higiene/técnico. Probabilidade: alta/média/baixa.

---

## 1. Bloqueios declarados

| ID | Risco | Prob. | Impacto | Situação em 2026-11-04 | Próximo passo |
|----|-------|-------|---------|------------------------|---------------|
| R1 | Câmera/permissões nunca testadas em aparelho real | alta | A | **Não comprovado.** Só há teste automatizado de contrato; o roteiro físico não foi executado | Executar `docs/sprint5/ROTEIRO_TESTE_MANUAL_MOBILE.md` com capturas |
| R2 | ADB ausente na máquina de desenvolvimento | alta | A | `preparar_android.py` retornou exit 2 ("ADB NÃO ENCONTRADO") | Instalar `platform-tools` (custo zero) ou usar aparelho com ADB já instalado |
| R3 | Backup/restauração não ensaiados | média | A | Procedimento escrito; **nenhum dump/restore executado** | Ensaio em banco descartável antes do GO |
| R4 | `CORS_ALLOW_ORIGINS` de produção ainda não definido | média | A na publicação | **Piloto local fechado:** `localhost` e `127.0.0.1:8080`, preflight de `POST`/`DELETE` e 21 testes; a API recusa config ambígua no boot | Informar a origem HTTPS exata no ambiente publicado |
| R5 | `NFE_IO_MOCK=1` no ambiente local | alta | A se usado no piloto | Auditoria: AVISO | `NFE_IO_MOCK=0` e token real, ou fluxo manual de NF-e explicitamente aceito |
| R6 | Dashboard sem credencial configurada | alta | B | `DASHBOARD_DATABASE_URL` ausente; role de menor privilégio pronta e testada | Definir URL da role `stellspy_dashboard` + `DASHBOARD_TENANT_ID` |

Qualquer R1–R5 aberto no momento da publicação é **NO-GO** conforme
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
| R13 | Dashboard lê outro tenant | baixa | A | Role sem `BYPASSRLS`, sem escrita, presa a `DASHBOARD_TENANT_ID`; 8 testes de isolamento | Validar no ambiente publicado |
| R14 | Rotação da senha da role do dashboard é manual | média | C | Migration aceita nova senha via `STELLSPY_DASHBOARD_PASSWORD` | Definir periodicidade e responsável |
| R15 | Senha administrativa do Supabase ainda é a usada no destravamento | média | C | Fora do repositório; auditoria não encontra vazamento | Rotacionar após a janela de homologação |
| R16 | Sem pipeline de CI | alta | C | Comandos de teste documentados; suíte local cobre 31 migrations | Configurar CI quando houver decisão de infraestrutura |
| R17 | Dados sintéticos permanecem no projeto oficial | alta | C | Nada foi removido, por instrução | Decisão do proprietário; remoção exige autorização |
| R18 | iPhone/Safari sem HTTPS interno | alta | B para iPhone | Android tem caminho `adb reverse`; HTTPS exige decisão de domínio | Se o piloto for Android, não bloqueia |
| R19 | Região única / sem HA no Supabase | baixa | B | Backup manual documentado | Aceitar risco ou contratar redundância (fora do orçamento) |
| R20 | Varredura de segredos é heurística | média | C | Detecta JWT `service_role`, PEM, senha em URL, `.env`, atribuição de segredo; exceção explícita `credencial-de-exemplo` | Não substitui cofre de segredos nem revisão humana |

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
