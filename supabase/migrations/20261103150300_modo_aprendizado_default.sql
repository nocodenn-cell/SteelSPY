-- Fase 0 / M24 — Novas obras nascem fora do modo de aprendizado
--
-- Achado A2 do diagnóstico: `modo_aprendizado` vinha TRUE por padrão, então
-- toda obra criada "com os defaults" rebaixava VERMELHO para AMARELO — e o
-- produto nunca bloqueava nada. A severidade técnica agora é preservada em
-- campo próprio (M24 é ortogonal a isso), mas o padrão operacional continua
-- sendo uma escolha de produto.
--
-- Decisão: o padrão passa a ser FALSE. Quem quiser implantação assistida liga
-- explicitamente, por obra, com prazo — em vez de o produto nascer sem
-- bloqueio e ninguém perceber.
--
-- REVERSÍVEL com uma linha:
--   ALTER TABLE obras ALTER COLUMN modo_aprendizado SET DEFAULT TRUE;
--
-- Obras já existentes NÃO são alteradas: quem está em modo de aprendizado
-- continua nele.

ALTER TABLE obras ALTER COLUMN modo_aprendizado SET DEFAULT FALSE;

COMMENT ON COLUMN obras.modo_aprendizado IS
  'TRUE = rebaixa o status operacional de VERMELHO para AMARELO durante a implantação. A severidade técnica NUNCA é rebaixada. Padrão: FALSE.';
