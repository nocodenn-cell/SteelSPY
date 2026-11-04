# Dashboard de economia (Streamlit)

## Como executar

```bash
# 1. Instalar dependências
pip install -r dashboard/requirements.txt

# 2. Configurar variáveis (o dashboard NÃO usa a credencial da API)
# DASHBOARD_DATABASE_URL — obrigatório: conexão da role stellspy_dashboard
# DASHBOARD_TENANT_ID    — obrigatório: UUID da construtora do piloto
# DASHBOARD_PASSWORD     — opcional (tela de login)
#
# A role `stellspy_dashboard` é criada pela migração
# 20261104170000_dashboard_role.sql: LOGIN só quando
# STELLSPY_DASHBOARD_PASSWORD está definida no executor de migrações; SELECT
# apenas em construtoras, obras, nfe_logs, nfe_itens e especificacoes; sujeita
# a RLS/FORCE (sem BYPASSRLS). A transação declara app.tenant_id com
# DASHBOARD_TENANT_ID, então o painel vê **uma** construtora.
#
# A `DATABASE_URL` da API usa `stellspy_app`, que tem escrita: não serve para o
# painel. Credencial de superusuário ou com BYPASSRLS é recusada na
# inicialização, com a correção dita na tela.

# 3. Na raiz do repositório
set PYTHONPATH=backend
streamlit run dashboard/app.py
```

Linux/macOS: `export PYTHONPATH=backend`

## KPIs exibidos

- **Itens analisados** (total de linhas em `nfe_itens` no período)
- **Taxa VERDE** (% de itens com status VERDE sobre o total)
- **Metros estimados totais** — conversão kg→m / barras conforme o núcleo `conferente`
- **Metros VERDES** — soma de metros estimados apenas para itens VERDE

## Gráficos

- Barras: distribuição por status
- Barras empilhadas: status por bitola (mm)
- Scatter: **planejado × recebido** (quando `qtd_planejada_metros` existe na especificação), com diagonal de referência
- Pizza: share de volume (m) por status
- Linha: NF-e processadas por dia (**datas em UTC** no eixo)

## Limitações (documentadas na UI)

- Não há preço por tonelada → **sem** estimativa em R$
- Metros são **estimativas** técnicas (kg/m via convenção ABNT no motor)
- Eixo temporal do gráfico de volume diário em **UTC** (não `America/Sao_Paulo`), salvo evolução futura

## Segurança

- Login opcional via `DASHBOARD_PASSWORD` (comparação de digest com `hmac.compare_digest` no app)
- Acesso **direto ao Postgres** com `DASHBOARD_DATABASE_URL` — credencial distinta da API, restringir rede / VPN em produção
- Menor privilégio: role `stellspy_dashboard` com **SELECT em cinco tabelas**, `NOBYPASSRLS`, `NOSUPERUSER`, `NOINHERIT`. Sem `usuarios`, `sessoes`, `evidencias`, `recebimentos` ou `fila_nfe`
- A credencial do painel é presa a **um** tenant (`DASHBOARD_TENANT_ID`); outra construtora não aparece, mesmo que exista no banco
- Credencial de superusuário, com `BYPASSRLS` ou com escrita é **recusada** na inicialização, com a correção dita na tela — sem painel vazio enganoso
- A role da aplicação (`stellspy_app`) nunca deve ser reutilizada no painel: ela tem escrita
- Cache **`@st.cache_data`** (TTL 120–300 s) para reduzir carga no banco ao navegar filtros
- Testes de isolamento: `backend/tests/integration/test_dashboard_rls.py` (role mínima, sem tenant = zero obras, tenant A × B, escrita negada)

## Checklist produção (sugestão)

- [ ] `STELLSPY_DASHBOARD_PASSWORD` definida **no executor de migrações** (sem ela a role fica `NOLOGIN`)
- [ ] `DASHBOARD_DATABASE_URL` com a role `stellspy_dashboard`, nunca owner/superuser
- [ ] `DASHBOARD_TENANT_ID` com o UUID da construtora do piloto
- [ ] Dashboard publicado em URL interna ou protegida (ex.: `https://dashboard.seudominio.com`)
- [ ] `DASHBOARD_PASSWORD` definido se exposto à internet
- [ ] Documentação para o cliente: como interpretar scatter (excesso/falta vs diagonal) e pizza (volume por status)

## Interpretação rápida

| Visual | Leitura |
|--------|---------|
| Scatter | Pontos **acima** da diagonal: volume recebido maior que o planejado na especificação; **abaixo**: menor |
| Pizza | Onde está o volume físico (m) por severidade — não é “valor financeiro” |
| Taxa VERDE | Proporção de linhas de item sem alerta crítico naquele recorte |
