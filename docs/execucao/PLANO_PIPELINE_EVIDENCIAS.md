# PLANO DO PIPELINE DE EVIDÊNCIAS — Fase 1

> **Status de verificação:** análise estática. **Nada implementado, nada executado.**
> Shell indisponível na sessão (`SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)`).
> Este documento é **plano + critérios de aceite**, não código.

---

## 1. O que existe hoje (evidência verificada)

| Item | Estado | Evidência |
|------|--------|-----------|
| Upload de arquivo | **inexistente** | `grep -E 'UploadFile\|File\(\|multipart'` em `backend/app` → 0 ocorrências de upload |
| `python-multipart` em `requirements.txt` | **ausente** | `requirements.txt` tem 7 linhas, nenhuma é multipart |
| Tabela de arquivos | **inexistente** | 7 tabelas, nenhuma de evidência |
| Storage de imagem | **inexistente** | `laudo_storage.py` só sobe PDF |
| Hash de imagem | **inexistente** | nenhuma referência a `sha256` em `backend/app` |
| Fila genérica | **inexistente** | só `fila_nfe` (XML) |
| `foto_url` (substituto atual) | existe | `conferencia.py:47` — URL de terceiro, baixada pelo servidor em `laudo_pdf.py:139` |

**Consequência:** a Fase 1 não é "adicionar upload a um sistema que já tem arquivos". É construir o
pipeline inteiro. Por isso o escopo é fechado e tem critérios de aceite explícitos.

---

## 2. Contrato de upload

### 2.1 Endpoint

```
POST /recebimentos/{recebimento_id}/evidencias
Content-Type: multipart/form-data
Auth: cookie de sessão (obra) OU X-API-KEY
```

| Campo | Tipo | Obrigatório | Regra |
|-------|------|-------------|-------|
| `arquivo` | binário | sim | 1 arquivo por request (simplicidade > lote) |
| `tipo` | texto | sim | `material` \| `etiqueta` \| `nfe` \| `lacre` \| `documento` |
| `id_cliente` | UUID | sim | gerado no dispositivo; chave de idempotência |
| `capturada_em` | ISO-8601 | não | metadado do dispositivo; **não é confiável** |
| `descricao` | texto (≤ 500) | não | observação do fiscal |

### 2.2 Validação (na ordem, tudo antes de gravar)

| # | Regra | Motivo | Erro |
|---|-------|--------|------|
| V1 | `Content-Length` ≤ 12 MB | Evitar abuso | `413` |
| V2 | **Magic bytes** conferem com o MIME declarado | `Content-Type` é mentira fácil | `415` |
| V3 | Extensão na allowlist (`.jpg .jpeg .png .webp .heic .pdf`) | Poliglota | `415` |
| V4 | Decodifica como imagem (ou PDF) válido | Arquivo corrompido | `422` |
| V5 | Dimensões ≤ 12.000 px no maior lado | *Decompression bomb* | `422` |
| V6 | Pixels totais ≤ 50 MP | Idem | `422` |
| V7 | Rejeitar se já existe `(recebimento_id, sha256)` | Idempotência | `200` (não erro) |

> **V2 é obrigatório.** Um arquivo `.exe` renomeado para `.jpg` com `Content-Type: image/jpeg` passa
> em qualquer validação que só olhe o header HTTP. Verificar assinatura real:
> JPEG `FF D8 FF`, PNG `89 50 4E 47`, WEBP `RIFF....WEBP`, HEIC `ftypheic`, PDF `%PDF-`.

### 2.3 Re-encode defensivo

Antes de subir, re-codificar a imagem (Pillow) — não subir o binário original do usuário:

| Ação | Justificativa |
|------|---------------|
| Remover todo EXIF | GPS de canteiro é dado sensível; orientação vai para coluna própria |
| Limitar lado maior a 4.096 px | Custo de storage/inferência |
| Converter para JPEG q=85 (ou manter PDF) | Consistência e previsibilidade |
| Calcular `sha256` **do resultado** | O hash representa o que guardamos, não o que recebemos |
| Guardar o hash do **original** também | Prova de integridade do que o cliente enviou |

Duas hashes, dois propósitos:

| Hash | Coluna | Propósito |
|------|--------|-----------|
| Original | `sha256_original` | Integridade/prova pericial |
| Armazenado | `sha256` | Dedupe e idempotência |

---

## 3. Storage privado

### 3.1 Layout

```
{tenant_id}/{obra_id}/{recebimento_id}/{sha256}.jpg
```

| Decisão | Valor | Motivo |
|---------|-------|--------|
| Bucket | `evidencias` (novo), **privado** | `laudos` hoje é público — não repetir o erro |
| Criptografia | SSE do provedor (Supabase/S3) + HTTPS | Requisito de segurança |
| Versionamento | desligado | Arquivo é imutável (o nome é o hash) |
| URL pública | **proibida** | Só URL assinada de curta duração |
| TTL da URL assinada | **300 s** | Suficiente para exibir; curto para vazar |
| Tamanho máximo do objeto | 12 MB | Espelha V1 |

### 3.2 Regra de ouro

> O frontend **nunca** recebe uma URL de bucket. Recebe
> `GET /evidencias/{id}/url` → `{ url_assinada, expira_em }`, e só depois de passar na autorização.

### 3.3 Migração do `foto_url` legado

`nfe_logs.foto_url` continua funcionando (campo de texto). Na Fase 1 ele é **depreciado**, não
removido: o laudo passa a preferir a evidência vinculada e usa `foto_url` apenas como fallback.
Remoção só na Fase 2+, depois de confirmar que nenhum cliente envia o campo.

---

## 4. Metadados da imagem

| Coluna | Tipo | Por que existe |
|--------|------|----------------|
| `id` | UUID | — |
| `tenant_id` | UUID NOT NULL | RLS |
| `recebimento_id` | UUID NOT NULL | Vínculo |
| `sha256` | CHAR(64) NOT NULL | Dedupe/idempotência |
| `sha256_original` | CHAR(64) | Prova do original |
| `storage_key` | TEXT NOT NULL | Localização |
| `mime` | TEXT NOT NULL | Render correto |
| `bytes` | INT NOT NULL | Custo e limite |
| `largura`, `altura` | INT | Inferência e layout |
| `orientacao` | SMALLINT | EXIF removido → precisa persistir |
| `origem` | TEXT | `camera` \| `galeria` \| `upload` \| `integracao` |
| `tipo` | TEXT | Semântica do documento |
| `capturada_em` | TIMESTAMPTZ | Metadado do cliente (**não confiável**) |
| `recebida_em` | TIMESTAMPTZ DEFAULT NOW() | **Verdade do servidor** |
| `exif_removido` | BOOLEAN | Prova de conformidade |
| `criado_por` | UUID → usuarios | Autor |
| `removido_em` | TIMESTAMPTZ | Tombstone de expurgo |

**Regra temporal:** toda métrica de negócio usa `recebida_em`. `capturada_em` serve para auditoria e
detecção de fraude (ex.: foto "capturada" antes do recebimento existir).

---

## 5. Fila assíncrona

### 5.1 Generalizar, não duplicar

Hoje existe `fila_nfe` com o padrão correto (`FOR UPDATE SKIP LOCKED`). A Fase 1 **não copia** essa
tabela: cria `fila_trabalho` genérica e mantém `fila_nfe` como está (compatibilidade), migrando-a na
Fase 2.

| Coluna | Uso |
|--------|-----|
| `id` | UUID |
| `tenant_id` | RLS |
| `tipo` | `inferencia` \| `ocr` \| `pdf` \| `whatsapp` \| `email` \| `erp_sync` |
| `payload` | JSONB |
| `status` | `pendente` \| `processando` \| `concluido` \| `falha` |
| `tentativas` | INT, máx 5 |
| `proxima_tentativa` | TIMESTAMPTZ |
| `claimed_em` | TIMESTAMPTZ — **novo, e é o que falta hoje** |
| `ultimo_erro` | TEXT |

### 5.2 O que o código atual **não** tem e a Fase 1 exige

| Lacuna (já identificada na auditoria) | Efeito | Correção |
|--------------------------------------|--------|----------|
| Sem `claimed_em` | Linha fica `processando` para sempre se o worker morrer | Coluna + reaper |
| `buscar_xml` fora do `try` | Exceção deixa linha órfã | `try/finally` por item |
| Sem tratamento de `JSONDecodeError` | Worker cai com resposta 200 não-JSON | Capturar e tratar como falha transitória |

**Reaper (obrigatório):**

```sql
-- ILUSTRATIVO
UPDATE fila_trabalho
   SET status = 'pendente', claimed_em = NULL, tentativas = tentativas + 1
 WHERE status = 'processando'
   AND claimed_em < NOW() - INTERVAL '10 minutes';
```

### 5.3 Backoff

`1 min → 5 min → 15 min → 60 min → falha` (5 tentativas). Erros 4xx definitivos **não** reintentam —
mesma heurística já usada em `whatsapp_evolution.py:129` (`_deve_reintentar_http`), que deve ser
extraída para `app/utils/retry.py` e reutilizada (não reimplementada).

---

## 6. Idempotência

| Operação | Chave | Resultado em duplicata |
|----------|-------|------------------------|
| Upload | `(recebimento_id, sha256)` | `200` com a evidência existente (não `409`) |
| Upload por sync | `(obra_id, id_cliente)` | mesma evidência; `id_cliente` repetido é absorvido |
| Processamento | `(evidencia_id, tipo, versao_modelo, hash_parametros)` em `inferencias` | devolve resultado já calculado |
| Conferência | `(obra_id, chave_acesso, tipo)` | ver A4 do diagnóstico — **corrigir na Fase 0** |

**Semântica explícita:** duplicata não é erro. `409` só quando o `id_cliente` existe com **conteúdo
diferente** — nesse caso é bug do cliente ou adulteração, e merece registro.

---

## 7. Histórico de processamento

Tabela `evidencia_eventos` — *append-only*, nunca `UPDATE`, nunca `DELETE`:

| Coluna | Conteúdo |
|--------|----------|
| `evidencia_id` | FK |
| `tipo` | `recebida` \| `validada` \| `rejeitada` \| `enfileirada` \| `processada` \| `revisada` \| `expurgada` \| `acessada` |
| `detalhe` | JSONB |
| `autor_id` | UUID (NULL = sistema) |
| `criado_em` | TIMESTAMPTZ |

Registrar **acesso** (`acessada`) parece excesso, mas é o que permite responder "quem viu a foto desta
obra" — pergunta que aparece em auditoria de construtora com investidor.

---

## 8. Retenção e exclusão (LGPD)

| Situação | Regra |
|----------|-------|
| Retenção padrão | 24 meses após o encerramento do recebimento |
| Retenção contratual | Configurável por tenant (12–60 meses) em `construtoras.retencao_meses` |
| Expurgo | Job mensal: apaga objeto no storage → `removido_em` na linha → evento `expurgada` |
| Tombstone | Linha **permanece** com `removido_em` (prova de que existiu e quando sumiu) |
| Direito de exclusão (LGPD) | Apaga objeto + `sha256` + `storage_key`; mantém `id`, `recebido_em`, `removido_em` |
| Bloqueio legal | `construtoras.bloqueio_expurgo` — suspende expurgo durante disputa |
| Nota fiscal | **nunca** expurgada pela política de imagem (obrigação fiscal de 5 anos) |

**Cuidado crítico:** expurgar a imagem não pode quebrar o laudo já emitido. O PDF é cópia; a imagem é
prova. Se o laudo referencia a imagem, a política de retenção da imagem deve ser **igual ou maior** que
a do PDF.

---

## 9. Controle de acesso às evidências

| Cenário | Autorização |
|---------|-------------|
| Fiscal vê foto da sua obra | ✅ se vinculado via `obra_usuarios` |
| Engenheiro vê qualquer obra do tenant | ✅ |
| Auditor vê (somente leitura) | ✅, com registro de acesso |
| Usuário de outro tenant | ❌ `404` (não `403`) |
| Link assinado expirado | ❌ `403` |
| Link assinado compartilhado no WhatsApp | ⚠️ funciona até expirar (300 s) — risco aceito e documentado |
| Acesso via API key de integração | ✅ escopo mínimo; nunca listagem em massa |

**Não vazar existência:** recurso de outro tenant responde `404`, não `403`. `403` confirma que o
recurso existe — informação útil para atacante.

---

## 10. Modelo de ameaças do upload

| Ameaça | Vetor | Controle |
|--------|-------|----------|
| Execução de código | arquivo poliglota | V2 magic bytes + re-encode |
| *Decompression bomb* | PNG 60.000 × 60.000 | V5/V6 + limite de memória no decode |
| Exaustão de disco | envio em massa | quota por tenant (ex.: 5 GB) + rate limit |
| SSRF | (hoje) `foto_url` | eliminado quando a imagem é nossa; A1 corrigido na Fase 0 |
| Fraude de evidência | foto reciclada de outro recebimento | `sha256` UNIQUE por recebimento |
| Vazamento de PII | rosto/placa no canteiro | EXIF strip + política de retenção + opção de *blur* |
| Acesso indevido | URL pública | bucket privado + URL assinada |

---

## 11. Critérios de aceite da Fase 1

| ID | Critério | Evidência |
|----|----------|-----------|
| AC1.1 | Upload de JPEG válido cria 1 evidência e 1 objeto | teste de integração + inspeção do bucket |
| AC1.2 | Reenvio idêntico → `200`, **1** evidência, **1** objeto | teste |
| AC1.3 | `.exe` renomeado para `.jpg` → `415` | teste |
| AC1.4 | Imagem 20.000 px → `422` | teste |
| AC1.5 | EXIF com GPS removido (verificado no binário salvo) | teste de bytes |
| AC1.6 | URL do bucket direta → `403`/`404` | teste |
| AC1.7 | URL assinada expira em ≤ 300 s | teste |
| AC1.8 | Tenant A não acessa evidência de B → `404` | teste |
| AC1.9 | Worker morto no meio → reaper devolve a `pendente` em ≤ 10 min | teste com `claimed_em` forjado |
| AC1.10 | Expurgo remove objeto e mantém tombstone | teste |
| AC1.11 | Laudo continua gerando após expurgo da imagem | teste |
| AC1.12 | `evidencia_eventos` cobre o ciclo completo | consulta do histórico |
| AC1.13 | Nenhuma PII em log (path com UUID, sem nome de arquivo do usuário) | revisão de log |

---

## 12. Esforço

| Bloco | dd |
|-------|-----|
| Contrato + validação + re-encode (V1–V7) | 3 |
| Storage privado + URL assinada | 2 |
| Migração `evidencias` + `evidencia_eventos` | 2 |
| `fila_trabalho` + reaper + worker | 3 |
| Idempotência (3 níveis) + testes | 2 |
| Retenção + expurgo + tombstone | 2 |
| Controle de acesso + registro de acesso | 2 |
| PWA: captura e envio com progresso | 2 |
| Testes de aceite AC1.1–AC1.13 | 3 |
| **Total** | **21 dd** (+30% → **~27 dd**) |

---

## 13. O que **não** entra na Fase 1

| Fora | Motivo |
|------|--------|
| Inferência de visão computacional | Trilha B; só consome evidência pronta |
| OCR | Depende de modelo; Fase 3 |
| Upload em lote | 1 arquivo por request é suficiente e mais simples de tornar idempotente |
| Sincronização offline completa | Fase 5; mas `id_cliente` **nasce agora** (não dá para retrofitar) |
| CDN de imagem | Sem ganho no piloto |
| Processamento de vídeo | Fora de escopo |
| Migrar `laudos` de público para privado | Recomendado, mas é correção de segurança (Fase 0), não desta fase |
