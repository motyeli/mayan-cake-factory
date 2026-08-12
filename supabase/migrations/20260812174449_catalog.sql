-- Catalog, pricing rules, feasibility rules and delivery zones.
-- Everything the AI is allowed to offer must exist as a row here; the model
-- resolves names to these IDs and can never invent an option or a price.
--
-- Shared shape for every catalog table (spec section 39):
--   name, description, price adjustment, active, preparation time,
--   production points, manual-approval flag, display order.

-- ------------------------------------------------------------ cake sizes --

create table cake_sizes (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  min_servings             integer not null check (min_servings > 0),
  max_servings             integer not null check (max_servings >= min_servings),
  base_price_cents         bigint  not null check (base_price_cents >= 0),
  tiers                    smallint not null default 1 check (tiers between 1 and 5),
  preparation_hours        integer not null default 48 check (preparation_hours >= 0),
  production_points        smallint not null default 1 check (production_points > 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger cake_sizes_updated_at before update on cake_sizes
  for each row execute function set_updated_at();

-- ------------------------------------------------------------- flavors --

create table cake_flavors (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0,
  is_premium               boolean not null default false,
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger cake_flavors_updated_at before update on cake_flavors
  for each row execute function set_updated_at();

-- ------------------------------------------------------------ fillings --

create table fillings (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0,
  is_premium               boolean not null default false,
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger fillings_updated_at before update on fillings
  for each row execute function set_updated_at();

-- ----------------------------------------------------------- frostings --
-- Transport constraints live here: whipped cream is pickup / short-distance
-- only, expressed as data rather than hard-coded in the rule engine.

create table frostings (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0,
  pickup_only              boolean not null default false,
  max_delivery_km          numeric(6,2),
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger frostings_updated_at before update on frostings
  for each row execute function set_updated_at();

-- -------------------------------------------------------- design styles --

create table design_styles (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0,
  base_complexity_level    smallint not null default 1 check (base_complexity_level between 1 and 4),
  image_prompt_hint        text,
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger design_styles_updated_at before update on design_styles
  for each row execute function set_updated_at();

-- ---------------------------------------------------------- decorations --
-- Price is a range: the engine charges price_adjustment_cents by default and
-- the admin may override up to max_price_cents for elaborate work.

create table decorations (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0 check (price_adjustment_cents >= 0),
  max_price_cents          bigint check (max_price_cents >= price_adjustment_cents),
  complexity_points        smallint not null default 0 check (complexity_points >= 0),
  food_safe                boolean not null default true,
  requires_barrier         boolean not null default false,
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger decorations_updated_at before update on decorations
  for each row execute function set_updated_at();

-- ------------------------------------------------------- dietary options --
-- A severe-allergy declaration routes the order to Mayan. The bakery never
-- guarantees an allergen-free environment (spec section 18).

create table dietary_options (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  description              text,
  price_adjustment_cents   bigint not null default 0,
  severe_allergy_flag      boolean not null default false,
  preparation_hours        integer not null default 0 check (preparation_hours >= 0),
  production_points        smallint not null default 0 check (production_points >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger dietary_options_updated_at before update on dietary_options
  for each row execute function set_updated_at();

-- ---------------------------------------------- recommended combinations --
-- Guidance only. Never blocks a different valid combination (spec section 16).

create table recommended_combinations (
  id             uuid primary key default gen_random_uuid(),
  name           text not null,
  cake_flavor_id uuid references cake_flavors (id) on delete cascade,
  filling_id     uuid references fillings (id) on delete cascade,
  frosting_id    uuid references frostings (id) on delete cascade,
  description    text,
  active         boolean not null default true,
  display_order  integer not null default 0,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create trigger recommended_combinations_updated_at before update on recommended_combinations
  for each row execute function set_updated_at();

-- ------------------------------------------------------ catalog availability --
-- Marks an ingredient or decoration temporarily unavailable without
-- deactivating it permanently (spec section 5.2).

create table catalog_availability (
  id               uuid primary key default gen_random_uuid(),
  catalog_type     text not null check (catalog_type in
                     ('cake_sizes', 'cake_flavors', 'fillings', 'frostings',
                      'design_styles', 'decorations', 'dietary_options')),
  item_id          uuid not null,
  unavailable_from date,
  unavailable_to   date,
  reason           text,
  created_at       timestamptz not null default now(),
  check (unavailable_to is null or unavailable_from is null or unavailable_to >= unavailable_from)
);

create index catalog_availability_lookup_idx
  on catalog_availability (catalog_type, item_id, unavailable_from, unavailable_to);

-- -------------------------------------------------------- delivery zones --

create table delivery_zones (
  id                       uuid primary key default gen_random_uuid(),
  name                     text not null unique,
  min_distance_km          numeric(6,2) not null default 0 check (min_distance_km >= 0),
  max_distance_km          numeric(6,2) not null check (max_distance_km > min_distance_km),
  delivery_fee_cents       bigint not null check (delivery_fee_cents >= 0),
  requires_manual_approval boolean not null default false,
  active                   boolean not null default true,
  display_order            integer not null default 0,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create trigger delivery_zones_updated_at before update on delivery_zones
  for each row execute function set_updated_at();

-- --------------------------------------------------------- pricing rules --
-- Data-driven surcharges evaluated in priority order by the Python pricing
-- engine. `conditions` is matched against the resolved specification.
-- adjustment_amount is cents for fixed_cents, basis points for percent.

create table pricing_rules (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  rule_type         text not null check (rule_type in
                      ('base', 'flavor', 'filling', 'frosting', 'decoration',
                       'complexity', 'rush', 'delivery', 'custom')),
  conditions        jsonb not null default '{}'::jsonb,
  adjustment_type   adjustment_type not null,
  adjustment_amount bigint not null,
  priority          integer not null default 100,
  active            boolean not null default true,
  effective_from    date,
  effective_to      date,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  check (effective_to is null or effective_from is null or effective_to >= effective_from)
);

create index pricing_rules_active_idx on pricing_rules (active, priority);

create trigger pricing_rules_updated_at before update on pricing_rules
  for each row execute function set_updated_at();

-- ----------------------------------------------------- feasibility rules --
-- The deterministic production-rule engine (spec section 19). The language
-- model never decides feasibility; it only explains these outcomes and
-- offers the stored alternative.

create table feasibility_rules (
  id                     uuid primary key default gen_random_uuid(),
  name                   text not null,
  description            text,
  conditions             jsonb not null default '{}'::jsonb,
  outcome                feasibility_outcome not null,
  manual_approval_reason text,
  customer_message       text,
  suggested_alternative  text,
  priority               integer not null default 100,
  active                 boolean not null default true,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index feasibility_rules_active_idx on feasibility_rules (active, priority);

create trigger feasibility_rules_updated_at before update on feasibility_rules
  for each row execute function set_updated_at();
