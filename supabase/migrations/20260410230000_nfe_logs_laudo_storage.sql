-- Cache do laudo PDF no Storage (URL pública ou assinada gravada após primeiro GET)
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS laudo_pdf_url TEXT;
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS laudo_pdf_gerado_em TIMESTAMPTZ;

COMMENT ON COLUMN nfe_logs.laudo_pdf_url IS 'URL do PDF no Supabase Storage; GET /laudo.pdf redireciona se preenchido';
COMMENT ON COLUMN nfe_logs.laudo_pdf_gerado_em IS 'Momento em que o laudo foi gerado e enviado ao storage';
