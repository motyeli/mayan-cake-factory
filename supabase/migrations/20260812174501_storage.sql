-- Storage buckets.
--
-- Customer uploads and generated designs are PRIVATE. The backend issues
-- short-lived signed URLs; nothing is served from a public bucket, because a
-- public URL for a customer's personal photograph is a permanent leak.
--
-- Catalog assets (example cake styles on the home page) are public: they are
-- marketing images with no personal data.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('customer-uploads', 'customer-uploads', false, 5242880,
   array['image/jpeg', 'image/png', 'image/webp', 'image/heic']),

  ('cake-designs', 'cake-designs', false, 10485760,
   array['image/png', 'image/webp', 'image/jpeg', 'image/svg+xml']),

  ('catalog-assets', 'catalog-assets', true, 5242880,
   array['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'])
on conflict (id) do update
  set file_size_limit    = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types,
      public             = excluded.public;

-- Public read for catalog assets only. The two private buckets get no anon
-- policy at all, so they are reachable only via the service role (backend)
-- or a signed URL it generates.
create policy catalog_assets_public_read on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'catalog-assets');

-- Active staff may read generated designs directly (order review screens can
-- fall back to this if a signed URL expires mid-session).
create policy cake_designs_admin_read on storage.objects
  for select to authenticated
  using (bucket_id = 'cake-designs' and is_active_admin());
