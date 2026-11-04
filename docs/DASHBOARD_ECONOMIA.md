# Dashboard de economia (Streamlit)

## Como executar

```bash
# 1. Instalar dependências
pip install -r dashboard/requirements.txt

# 2. Configurar variáveis (o dashboard NÃO usa a credencial da API)
# DASHBOARD_DATABASE_URL — obrigatório, credencial de back-office (ex.: owner)
# DASHBOARD_PASSWORD — opcional (tela de login)
#
# A `DATABASE_URL` da API usa `stellspy_app`, sujeita a RLS: sem contexto de
# tenant ela vê zero obras, o que é correto para a API e inútil para o
# dashboard. O diagnóstico na inicialização recusa essa credencial em vez de
# exibir gráficos vazios.

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
- A role da aplicação (`stellspy_app`) continua **sem** `BYPASSRLS`; o dashboard nunca deve reutilizá-la
- Cache **`@st.cache_data`** (TTL 120–300 s) para reduzir carga no banco ao navegar filtros
- Se a conexão não atravessar tenants, a tela para com mensagem explícita (usuário conectado e 0 obras), em vez de mostrar painel vazio

## Checklist produção (sugestão)

- [ ] Dashboard publicado em URL interna ou protegida (ex.: `https://dashboard.seudominio.com`)
- [ ] `DASHBOARD_PASSWORD` definido se exposto à internet
- [ ] Documentação para o cliente: como interpretar scatter (excesso/falta vs diagonal) e pizza (volume por status)

## Interpretação rápida

| Visual | Leitura |
|--------|---------|
| Scatter | Pontos **acima** da diagonal: volume recebido maior que o planejado na especificação; **abaixo**: menor |
| Pizza | Onde está o volume físico (m) por severidade — não é “valor financeiro” |
| Taxa VERDE | Proporção de linhas de item sem alerta crítico naquele recorte |
