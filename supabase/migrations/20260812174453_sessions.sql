-- Customers, guest design sessions, AI conversation, uploads, specifications
-- and generated design versions.
--
-- Customers never create accounts (spec section 6). A session is reached
-- through a secure tokenised link; only the SHA-256 hash of that token is
-- stored, so a database leak does not hand out working links.

-- ------------------------------------------------------------- customers --
-- Created at order time, or earlier if the customer volunteers contact
-- details. Retained internally for the lightweight CRM (spec section 36).

create table customers (
  id                 uuid primary key default gen_random_uuid(),
  full_name          text not null,
  email              text,
  phone              text,
  preferred_language text not null default 'en',
  internal_notes     text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  check (email is not null or phone is not null)
);

create index customers_email_idx on customers (lower(email)) where email is not null;
create index customers_phone_idx on customers (phone) where phone is not null;
create index customers_name_idx  on customers using gin (to_tsvector('simple', full_name));

create trigger customers_updated_at before update on customers
  for each row execute function set_updated_at();

-- -------------------------------------------------------- design sessions --

create table design_sessions (
  id                uuid primary key default gen_random_uuid(),
  public_token_hash text not null unique,
  status            session_status not null default 'active',
  revision_count    smallint not null default 0 check (revision_count >= 0),
  message_count     integer not null default 0 check (message_count >= 0),
  customer_id       uuid references customers (id) on delete set null,
  expires_at        timestamptz not null,
  last_seen_at      timestamptz not null default now(),
  ip_hash           text,                -- coarse abuse detection, not an identity
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index design_sessions_expiry_idx   on design_sessions (expires_at);
create index design_sessions_customer_idx on design_sessions (customer_id);
create index design_sessions_status_idx   on design_sessions (status, created_at desc);

create trigger design_sessions_updated_at before update on design_sessions
  for each row execute function set_updated_at();

comment on column design_sessions.public_token_hash is
  'SHA-256 of the customer link token. The plaintext token exists only in the '
  'URL handed to the customer and is never stored.';

-- ------------------------------------------------------- ai conversations --
-- Customer-visible messages plus the structured data extracted from them.
-- Hidden model reasoning is deliberately NOT stored (spec section 10).

create table ai_conversations (
  id                  uuid primary key default gen_random_uuid(),
  session_id          uuid not null references design_sessions (id) on delete cascade,
  role                message_role not null,
  message             text not null,
  structured_data     jsonb,
  provider            text,
  provider_message_id text,
  usage_metadata      jsonb,          -- token counts / latency, no payload text
  error_info          text,
  created_at          timestamptz not null default now()
);

create index ai_conversations_session_idx on ai_conversations (session_id, created_at);

-- --------------------------------------------------------- uploaded assets --

create table uploaded_assets (
  id                uuid primary key default gen_random_uuid(),
  session_id        uuid references design_sessions (id) on delete cascade,
  asset_type        asset_type not null,
  storage_path      text not null,
  mime_type         text not null,
  original_filename text,
  file_size         integer not null check (file_size > 0),
  width             integer,
  height            integer,
  created_at        timestamptz not null default now()
);

create index uploaded_assets_session_idx on uploaded_assets (session_id, created_at);

-- ---------------------------------------------------- cake specifications --
-- The operational source of truth. The generated image is a representation
-- of this row, never the other way round (spec section 20).
--
-- Catalog choices are foreign keys: the model resolves a name to a row or
-- asks again. It can never invent a flavor that the bakery does not make.

create table cake_specifications (
  id                       uuid primary key default gen_random_uuid(),
  session_id               uuid not null unique references design_sessions (id) on delete cascade,
  event_type               text,
  event_date               date,
  servings                 integer check (servings > 0),
  size_id                  uuid references cake_sizes (id) on delete restrict,
  shape                    cake_shape,
  number_of_tiers          smallint check (number_of_tiers between 1 and 5),
  cake_flavor_id           uuid references cake_flavors (id) on delete restrict,
  filling_id               uuid references fillings (id) on delete restrict,
  frosting_id              uuid references frostings (id) on delete restrict,
  design_style_id          uuid references design_styles (id) on delete restrict,
  colors                   text[] not null default '{}',
  decoration_ids           uuid[] not null default '{}',
  inscription              text,
  dietary_requirement_ids  uuid[] not null default '{}',
  allergen_notes           text[] not null default '{}',
  customer_budget_cents    bigint check (customer_budget_cents >= 0),
  fulfillment_method       fulfillment_method,
  delivery_address         text,
  missing_information      text[] not null default '{}',
  requires_manual_approval boolean not null default false,
  manual_approval_reasons  text[] not null default '{}',
  complexity_level         smallint check (complexity_level between 1 and 4),
  production_points        smallint check (production_points >= 0),
  estimated_price_cents    bigint check (estimated_price_cents >= 0),
  price_breakdown          jsonb,
  confirmed_by_customer    boolean not null default false,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create index cake_specifications_event_date_idx on cake_specifications (event_date);

create trigger cake_specifications_updated_at before update on cake_specifications
  for each row execute function set_updated_at();

-- ----------------------------------------------------------- cake designs --
-- One row per generated version. Earlier versions are never deleted or
-- overwritten so the customer can go back to any of them (spec section 21).

create table cake_designs (
  id                      uuid primary key default gen_random_uuid(),
  session_id              uuid not null references design_sessions (id) on delete cascade,
  version_number          smallint not null check (version_number > 0),
  image_storage_path      text,
  generation_prompt       text not null,
  revision_request        text,
  structured_specification jsonb not null,
  price_cents             bigint check (price_cents >= 0),
  price_breakdown         jsonb,
  provider                text,
  provider_result_id      text,
  usage_metadata          jsonb,
  error_info              text,
  customer_approved       boolean not null default false,
  created_at              timestamptz not null default now(),
  unique (session_id, version_number)
);

create index cake_designs_session_idx  on cake_designs (session_id, version_number);
create unique index cake_designs_one_approved_idx
  on cake_designs (session_id) where customer_approved;

comment on index cake_designs_one_approved_idx is
  'At most one approved design per session — the one the order is built from.';
