# Procedimento de backup e restauração — piloto

**Estado:** documentado, **não executado**. Nenhum dump, restauração ou remoção
foi feito nesta sprint. O procedimento precisa de um ensaio em banco descartável
antes do piloto; sem esse ensaio, o critério de backup é **NO-GO**.

**Escopo:** dados do PostgreSQL do projeto oficial e objetos do bucket privado de
evidências. Não cobre outros projetos (Venddi, Jinlong, FABRYON, GEO Portal).

---

## 1. O que precisa ser copiado

| Ativo | Onde vive | Como copiar | Observação |
|-------|-----------|-------------|------------|
| Tabelas `public` | PostgreSQL `akvbtceshpsvsuacueaq` | `pg_dump` formato custom | inclui dados e schema |
| `schema_migrations` | idem | junto do dump | permite saber a posição da trilha |
| Roles (`stellspy_app`, `stellspy_dashboard`) | cluster, não no banco | recriadas pelas migrations | `pg_dump` de banco **não** inclui roles |
| Bucket `evidencias` | Supabase Storage | painel/S3 API ou download por objeto | privado; `storage_key` no banco aponta para o objeto |
| Segredos | cofre do proprietário | fora do repositório | nunca no dump nem no Git |

**Backup automático/PITR depende do plano contratado.** Confirme no painel do
Supabase antes de prometer restauração a ponto no tempo. Se o plano não oferecer,
o único caminho é o dump manual abaixo.

---

## 2. Backup lógico (documentação; executar só com autorização)

Pré-requisitos no cliente:

- `pg_dump`/`pg_restore` na mesma versão principal do servidor (PG 17.x).
- `SUPABASE_DB_ADMIN_URL` disponível no ambiente, **nunca** em histórico de shell
  nem em arquivo versionado.

```bash
# Fora do repositório; diretório com permissão restrita.
pg_dump "$SUPABASE_DB_ADMIN_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=stellspy-$(date -u +%Y%m%dT%H%M%SZ).dump

sha256sum stellspy-*.dump
```

- `--no-owner --no-privileges`: o dono no destino pode não existir; as roles e
  grants são recriados pelas migrations.
- Não use `--clean` no dump; a decisão de apagar é do ensaio de restauração.
- Registre: data/hora UTC, tamanho, SHA-256, versão do PG e posição em
  `schema_migrations`.

### Evidências

- O dump do banco **não** contém os bytes das fotos. Copie o bucket separadamente
  pelo painel ou pela API S3 do Supabase, preservando os caminhos
  `tenant/obra/...` que aparecem em `evidencias.storage_key`.
- Registre a quantidade de objetos e o hash de uma amostra; sem isso não há como
  provar que a cópia corresponde ao banco.

---

## 3. Ensaio de restauração (obrigatório antes do piloto)

Destino: banco **descartável** local (container), nunca o projeto oficial.

1. Criar banco vazio e as roles:
   - aplicar as migrations com `backend/scripts/apply_migrations.py` no banco
     descartável **não** serve como passo prévio ao `pg_restore` completo, porque
     o dump já contém o schema. Escolha um dos dois caminhos e registre qual:
     - **A. Restauração completa:** banco vazio → `pg_restore` do dump → recriar
       roles separadamente (script SQL de roles, sem dados) → validar RLS.
     - **B. Dados sobre schema novo:** banco vazio → migrations (31/31) →
       `pg_restore --data-only` → validar RLS.
   - O caminho B é o que mais se parece com uma recuperação operacional; o A é o
     que prova que o dump está íntegro.
2. Restaurar:
   ```bash
   pg_restore --dbname "$DESTINO" --no-owner --no-privileges --exit-on-error dump.dump
   ```
3. Conferir contagens mínimas: `construtoras`, `obras`, `usuarios`,
   `pedidos_compra`, `recebimentos`, `evidencias`, `nfe_logs`, `conciliacoes`.
4. Provar RLS com a role `stellspy_app`: sem `app.tenant_id` vê 0 linhas; tenant A
   não vê B; `stellspy_dashboard` só lê as 5 tabelas do dashboard.
5. Medir o tempo de restauração e registrar. Esse número define a janela de
   indisponibilidade aceitável no piloto.

**Critério de aprovação do ensaio:** contagens conferem, RLS passa, nenhuma
credencial foi impressa, tempo registrado.

---

## 4. Restauração em produção (somente com autorização explícita)

1. Parar a API e o PWA (evitar escrita durante a restauração).
2. Confirmar que o dump e o hash são os do registro do ensaio.
3. Restaurar em banco novo quando o plano permitir; trocar a `DATABASE_URL` para
   o banco restaurado é reversível. Restaurar por cima do banco atual é
   destrutivo e exige aprovação específica.
4. Reaplicar roles/senhas e validar login de cada papel.
5. Religar os serviços e repetir o smoke test do checklist de publicação.
6. Registrar incidente, causa, dados perdidos (se houver) e horário.

Nunca execute `DROP DATABASE`, `TRUNCATE` ou remoção de bucket como atalho de
recuperação. Dados de homologação remotos só saem com autorização do proprietário.
