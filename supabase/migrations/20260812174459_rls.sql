-- Row Level Security.
--
-- THREAT MODEL
-- The browser never talks to Postgres. Customers reach their session through
-- a backend-issued token; admins log in with Supabase Auth and send the JWT
-- to the backend, which verifies it and then uses the service role. The
-- service role bypasses RLS by design.
--
-- So RLS here is defence in depth: if an anon key ever leaks into a page, it
-- must grant nothing. Default-deny is achieved by enabling RLS on every table
-- and writing no permissive policy for `anon` at all.
--
-- Admin-authenticated read policies are added on top so an active staff JWT
-- can read operational data directly (useful for ad-hoc reporting) without
-- ever being able to write.

-- Enable RLS on every table in `public`, including any added later by a
-- migration that forgets to. Loop rather than 27 hand-written lines.
do $$
declare t record;
begin
  for t in
    select tablename from pg_tables where schemaname = 'public'
  loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end;
$$;

-- ---------------------------------------------------------------- helper --

create or replace function is_active_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from admin_profiles
     where auth_user_id = auth.uid()
       and active
  );
$$;

comment on function is_active_admin is
  'True when the calling JWT belongs to an active staff member. security '
  'definer so the lookup itself is not blocked by admin_profiles RLS.';

revoke execute on function is_active_admin() from anon;

-- ------------------------------------------------- admin read-only access --
-- Writes are deliberately absent: all mutations go through the backend, which
-- validates status transitions, recalculates prices and writes the audit log.
-- Granting UPDATE here would create a path around every one of those checks.

do $$
declare t text;
begin
  foreach t in array array[
    'cake_sizes', 'cake_flavors', 'fillings', 'frostings', 'design_styles',
    'decorations', 'dietary_options', 'recommended_combinations',
    'catalog_availability', 'delivery_zones', 'pricing_rules',
    'feasibility_rules', 'time_slots', 'availability_dates',
    'time_slot_availability', 'settings', 'customers', 'orders',
    'order_status_history', 'order_price_overrides', 'cake_specifications',
    'cake_designs', 'design_sessions', 'audit_log'
  ]
  loop
    execute format(
      'create policy %I on public.%I for select to authenticated using (is_active_admin())',
      t || '_admin_read', t);
  end loop;
end;
$$;

-- An admin may read their own profile row (needed to resolve role after login).
create policy admin_profiles_self_read on admin_profiles
  for select to authenticated
  using (auth_user_id = auth.uid());

-- ------------------------------------------------------------ no anon access --
-- Intentionally no policies for the `anon` role on any table. Customer data,
-- conversations, uploads and designs are reachable only through the backend
-- after it has verified a session token.
--
-- ai_conversations and uploaded_assets have no admin read policy either:
-- conversations can contain personal detail the CRM does not need, so they
-- are read exclusively through audited backend endpoints (GDPR data
-- minimisation, spec section 44).
