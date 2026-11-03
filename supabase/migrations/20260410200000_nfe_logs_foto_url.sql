-- Evidência visual opcional (foto da NF no canteiro) para o laudo PDF
ALTER TABLE nfe_logs ADD COLUMN IF NOT EXISTS foto_url TEXT;

COMMENT ON COLUMN nfe_logs.foto_url IS 'URL da imagem da NF (storage); exibida como miniatura no laudo';
