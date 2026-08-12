-- Foundation: extensions, enum types, shared triggers, admin profiles,
-- runtime settings and the audit log.
-- Money is ALWAYS bigint cents. Never float, never numeric-as-money.

create extension if not exists "pgcrypto";      -- gen_random_uuid, digest

-- ---------------------------------------------------------------- enums --

create type admin_role         as enum ('owner', 'staff');

create type cake_shape         as enum ('round', 'square', 'rectangle', 'heart', 'custom');

create type session_status     as enum ('active', 'specification_confirmed', 'design_generated',
                                        'design_approved', 'ordered', 'expired', 'abandoned');

create type message_role       as enum ('user', 'assistant', 'system');

create type asset_type         as enum ('inspiration', 'personal_photo', 'logo', 'illustration');

create type fulfillment_method as enum ('pickup', 'delivery');

create type order_status       as enum ('draft', 'design_in_progress', 'awaiting_customer_approval',
                                        'awaiting_bakery_approval', 'confirmed', 'in_production',
                                        'ready_for_pickup', 'out_for_delivery', 'completed', 'cancelled');

create type payment_status     as enum ('pending_external_payment', 'deposit_paid', 'paid', 'refunded', 'void');

create type payment_method     as enum ('pay_at_pickup', 'pay_on_delivery', 'arranged_separately');

create type adjustment_type    as enum ('fixed_cents', 'percent');

create type feasibility_outcome as enum ('allow', 'require_manual_approval', 'reject');

-- ------------------------------------------------------------- triggers --

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

comment on function set_updated_at is 'Generic updated_at maintenance trigger.';

-- ------------------------------------------------------- admin profiles --
-- One row per bakery staff member, keyed to a Supabase Auth user.

create table admin_profiles (
  id           uuid primary key default gen_random_uuid(),
  auth_user_id uuid not null unique references auth.users (id) on delete cascade,
  full_name    text not null,
  role         admin_role not null default 'staff',
  active       boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index admin_profiles_auth_user_id_idx on admin_profiles (auth_user_id) where active;

create trigger admin_profiles_updated_at
  before update on admin_profiles
  for each row execute function set_updated_at();

-- -------------------------------------------------------------- settings --
-- Every operational constant the admin can change without a deploy.
-- Typed loosely on purpose (jsonb value) but read through a validated
-- Pydantic settings model in the backend.

create table settings (
  key         text primary key,
  value       jsonb not null,
  value_type  text not null check (value_type in ('string', 'integer', 'boolean', 'json')),
  label       text not null,
  description text,
  editable    boolean not null default true,
  updated_at  timestamptz not null default now()
);

create trigger settings_updated_at
  before update on settings
  for each row execute function set_updated_at();

-- ------------------------------------------------------------- audit log --
-- Sensitive administrative changes. Append-only by policy (no update/delete
-- grants are ever issued to any role except the service role).

create table audit_log (
  id            bigserial primary key,
  actor_id      uuid references admin_profiles (id) on delete set null,
  actor_label   text,                       -- retained if the profile is deleted
  action        text not null,              -- e.g. 'order.price_override'
  entity_type   text not null,              -- e.g. 'order'
  entity_id     text,
  previous_data jsonb,
  new_data      jsonb,
  reason        text,
  ip_address    inet,
  created_at    timestamptz not null default now()
);

create index audit_log_entity_idx  on audit_log (entity_type, entity_id, created_at desc);
create index audit_log_actor_idx   on audit_log (actor_id, created_at desc);
create index audit_log_created_idx on audit_log (created_at desc);
