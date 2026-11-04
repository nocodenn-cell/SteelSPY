-- M30 — Bucket privado de evidências no Supabase Storage
--
-- Por que existe: as fotos de recebimento são prova pericial e dado de tenant.
-- Elas não podem ficar em bucket público nem ser acessíveis com a chave
-- publicável. O acesso acontece exclusivamente pela API, que já aplicou RLS e
-- autorização por obra; o servidor usa a service role, que nunca vai ao cliente.
--
-- Este arquivo é tolerante a bancos sem o schema `storage` (PostgreSQL puro
-- usado em teste local): nesse caso ele apenas registra e segue. Não cria um
-- segundo sistema de migração — usa o mesmo runner e o mesmo histórico.
--
-- Sem policies em storage.objects de propósito: bucket privado sem policy não
-- é acessível por `anon`/`authenticated`. A service role ignora RLS e é a única
-- credencial que o backend usa.

DO $$
BEGIN
  IF to_regclass('storage.buckets') IS NULL THEN
    RAISE NOTICE 'schema storage ausente: bucket de evidências será criado pelo Supabase';
    RETURN;
  END IF;

  INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  VALUES (
    'evidencias',
    'evidencias',
    false,
    12582912, -- 12 MiB, igual a EVIDENCIA_MAX_BYTES
    ARRAY['image/jpeg', 'image/png']
  )
  ON CONFLICT (id) DO NOTHING;

  -- Bucket público seria vazamento de fotos entre tenants: falha alto em vez
  -- de "corrigir" silenciosamente uma configuração que alguém pode ter mudado.
  IF EXISTS (SELECT 1 FROM storage.buckets WHERE id = 'evidencias' AND public) THEN
    RAISE EXCEPTION 'bucket evidencias existe como público; torne-o privado antes de usar';
  END IF;
END $$;
