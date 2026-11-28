-- AUDITORIA SOMENTE LEITURA — obras com modo_aprendizado = TRUE (P-11.2)
--
-- Não contém UPDATE, DELETE nem DDL. A transação é marcada como READ ONLY e
-- termina com ROLLBACK. Não seleciona api_key, CNPJ nem dados de contato.
--
-- Como rodar (com um usuário somente leitura no banco de produção):
--   psql "$URL_PRODUCAO_LEITURA" -f docs/execucao/AUDITORIA_MODO_APRENDIZADO.sql
--
-- Cada bloco abaixo responde uma pergunta do P-11.2. As colunas podem ser exportadas
-- para CSV com \copy se preferir analisar em planilha.

BEGIN;
SET TRANSACTION READ ONLY;

-- 1) Quantas obras estão com TRUE, e quantas com FALSE.
SELECT
  count(*)                                    AS obras_total,
  count(*) FILTER (WHERE modo_aprendizado)    AS obras_modo_aprendizado_true,
  count(*) FILTER (WHERE NOT modo_aprendizado) AS obras_modo_aprendizado_false
FROM obras;

-- 2) Por obra com TRUE: conferências, rebaixamentos e divergências abertas.
--    "rebaixada" = severidade técnica VERMELHO, mas status operacional diferente de VERMELHO.
--    Registros gravados antes da severidade técnica existir não têm o campo e ficam de fora
--    de "rebaixadas" (ver coluna sem_severidade_tecnica).
SELECT
  o.id                                                                    AS obra_id,
  o.nome                                                                  AS obra_nome,
  o.created_at::date                                                      AS criada_em,
  count(n.id)                                                             AS conferencias,
  count(n.id) FILTER (WHERE n.xml_data->>'severidade_tecnica' = 'VERMELHO'
                       AND n.status_conferencia <> 'VERMELHO')            AS rebaixadas_vermelho_para_amarelo_ou_verde,
  count(n.id) FILTER (WHERE n.xml_data IS NOT NULL
                       AND n.xml_data->>'severidade_tecnica' IS NULL)     AS sem_severidade_tecnica,
  count(n.id) FILTER (WHERE n.status_conferencia = 'VERMELHO')            AS vermelhos_abertos,
  count(n.id) FILTER (WHERE n.status_conferencia = 'AMARELO')             AS amarelos_abertos,
  count(n.id) FILTER (WHERE n.override_info IS NOT NULL)                  AS com_override,
  max(n.processado_em)::date                                              AS ultima_conferencia
FROM obras o
LEFT JOIN nfe_logs n ON n.obra_id = o.id
WHERE o.modo_aprendizado
GROUP BY o.id, o.nome, o.created_at
ORDER BY conferencias DESC, o.nome;

-- 3) Divergências ainda não resolvidas em obras com TRUE, por tipo de motivo.
--    "Não resolvida" = status VERMELHO ou AMARELO, sem override.
SELECT
  o.id AS obra_id,
  o.nome AS obra_nome,
  d.tag AS divergencia,
  count(DISTINCT n.id) AS nfs
FROM obras o
JOIN nfe_logs n ON n.obra_id = o.id
JOIN nfe_itens i ON i.nfe_log_id = n.id
CROSS JOIN LATERAL jsonb_array_elements_text(i.divergencias) AS d(tag)
WHERE o.modo_aprendizado
  AND n.status_conferencia IN ('VERMELHO', 'AMARELO')
  AND n.override_info IS NULL
GROUP BY o.id, o.nome, d.tag
ORDER BY o.nome, nfs DESC;

-- 4) Impacto: NFs que o modo de aprendizado deixou passar, nos últimos 90 dias.
--    São as que mudariam de AMARELO para VERMELHO se a obra passasse a FALSE.
SELECT
  o.id AS obra_id,
  o.nome AS obra_nome,
  count(n.id) AS nfs_rebaixadas_90d
FROM obras o
JOIN nfe_logs n ON n.obra_id = o.id
WHERE o.modo_aprendizado
  AND n.processado_em >= NOW() - INTERVAL '90 days'
  AND n.xml_data->>'severidade_tecnica' = 'VERMELHO'
  AND n.status_conferencia <> 'VERMELHO'
GROUP BY o.id, o.nome
ORDER BY nfs_rebaixadas_90d DESC;

ROLLBACK;
