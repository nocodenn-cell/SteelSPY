-- WhatsApp fiscal por obra (Evolution); fallback global via WHATSAPP_ALERT_NUMBER na API
ALTER TABLE obras ADD COLUMN IF NOT EXISTS whatsapp_destino TEXT
  CHECK (whatsapp_destino IS NULL OR (length(whatsapp_destino) >= 10 AND length(whatsapp_destino) <= 15 AND whatsapp_destino ~ '^[0-9]+$'));

COMMENT ON COLUMN obras.whatsapp_destino IS
  'Destino alertas WhatsApp (apenas dígitos, DDI+DDD+número). NULL = usar WHATSAPP_ALERT_NUMBER no servidor.';
