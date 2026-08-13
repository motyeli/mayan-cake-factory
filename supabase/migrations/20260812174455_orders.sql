-- Orders, status history and the back-references from session-scoped tables.
--
-- Every money column is bigint cents. Order value is NOT revenue: paid and
-- outstanding amounts are tracked separately so the dashboard can never
-- present unpaid orders as collected money (spec section 32).

create table orders (
  id                       uuid primary key default gen_random_uuid(),
  order_number             text not null unique,
  customer_id              uuid not null references customers (id) on delete restrict,
  design_session_id        uuid references design_sessions (id) on delete set null,
  approved_design_id       uuid references cake_designs (id) on delete set null,

  status                   order_status not null default 'draft',

  -- Fulfillment -----------------------------------------------------------
  fulfillment_method       fulfillment_method not null,
  fulfillment_date         date not null,
  time_slot_id             uuid references time_slots (id) on delete set null,
  delivery_address         text,
  delivery_latitude        numeric(9,6),
  delivery_longitude       numeric(9,6),
  delivery_zone_id         uuid references delivery_zones (id) on delete set null,
  delivery_distance_km     numeric(6,2),

  -- Money -----------------------------------------------------------------
  subtotal_cents           bigint not null check (subtotal_cents >= 0),
  surcharge_cents          bigint not null default 0 check (surcharge_cents >= 0),
  delivery_fee_cents       bigint not null default 0 check (delivery_fee_cents >= 0),
  discount_cents           bigint not null default 0 check (discount_cents >= 0),
  total_price_cents        bigint not null check (total_price_cents >= 0),
  currency                 text not null default 'USD',
  price_breakdown          jsonb not null default '{}'::jsonb,
  price_is_estimate        boolean not null default false,

  -- Payment (no gateway in the MVP; fields exist so one can be added later) --
  payment_status           payment_status not null default 'pending_external_payment',
  payment_method           payment_method,
  amount_due_cents         bigint not null check (amount_due_cents >= 0),
  amount_paid_cents        bigint not null default 0 check (amount_paid_cents >= 0),
  deposit_required         boolean not null default false,
  deposit_amount_cents     bigint not null default 0 check (deposit_amount_cents >= 0),

  -- Production ------------------------------------------------------------
  complexity_level         smallint not null check (complexity_level between 1 and 4),
  production_points        smallint not null check (production_points >= 0),
  is_rush_order            boolean not null default false,
  requires_manual_approval boolean not null default false,
  manual_approval_reasons  text[] not null default '{}',
  has_allergen_warning     boolean not null default false,

  internal_notes           text,
  customer_notes           text,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),

  -- A delivery order must carry an address; a pickup order must not charge
  -- a delivery fee.
  constraint orders_delivery_needs_address check (
    fulfillment_method <> 'delivery' or delivery_address is not null),
  constraint orders_pickup_is_free check (
    fulfillment_method <> 'pickup' or delivery_fee_cents = 0)
);

create index orders_fulfillment_date_idx on orders (fulfillment_date, status);
create index orders_status_idx            on orders (status, created_at desc);
create index orders_customer_idx          on orders (customer_id, created_at desc);
create index orders_created_idx           on orders (created_at desc);
create index orders_manual_approval_idx   on orders (fulfillment_date)
  where requires_manual_approval;
create index orders_rush_idx              on orders (fulfillment_date) where is_rush_order;

create trigger orders_updated_at before update on orders
  for each row execute function set_updated_at();

comment on column orders.price_is_estimate is
  'True for special orders: the customer is shown "estimated price, subject to '
  'bakery approval" rather than a final figure (spec section 23).';

-- ------------------------------------------------------- status history --
-- Every transition is stored. Allowed transitions are enforced in the
-- backend, and this table is the audit trail for what actually happened.

create table order_status_history (
  id              bigserial primary key,
  order_id        uuid not null references orders (id) on delete cascade,
  previous_status order_status,
  new_status      order_status not null,
  changed_by      uuid references admin_profiles (id) on delete set null,
  changed_by_label text,
  reason          text,
  created_at      timestamptz not null default now()
);

create index order_status_history_order_idx on order_status_history (order_id, created_at desc);

-- ---------------------------------------------------- price override log --
-- A manual price change must record the previous price, the new price, the
-- administrator, the timestamp and the reason (spec section 34).

create table order_price_overrides (
  id                    bigserial primary key,
  order_id              uuid not null references orders (id) on delete cascade,
  previous_total_cents  bigint not null,
  new_total_cents       bigint not null,
  previous_points       smallint,
  new_points            smallint,
  changed_by            uuid references admin_profiles (id) on delete set null,
  changed_by_label      text not null,
  reason                text not null,
  created_at            timestamptz not null default now()
);

create index order_price_overrides_order_idx on order_price_overrides (order_id, created_at desc);

-- ------------------------------------- back-references from session tables --
-- Added here because these tables are created before `orders` exists.

alter table cake_specifications add column order_id uuid references orders (id) on delete set null;
alter table cake_designs        add column order_id uuid references orders (id) on delete set null;
alter table uploaded_assets     add column order_id uuid references orders (id) on delete set null;

create index cake_specifications_order_idx on cake_specifications (order_id);
create index cake_designs_order_idx        on cake_designs (order_id);
create index uploaded_assets_order_idx     on uploaded_assets (order_id);
