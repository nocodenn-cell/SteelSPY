-- Destinatários do relatório semanal CSV (um ou mais e-mails por obra)
ALTER TABLE obras ADD COLUMN IF NOT EXISTS relatorio_email_destinos TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN obras.relatorio_email_destinos IS
  'E-mails que recebem o CSV semanal de NF-e conferidas; vazio = obra não entra no job';
