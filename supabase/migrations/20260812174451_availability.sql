-- Capacity and availability.
--
-- Capacity is measured in PRODUCTION POINTS, not order counts (spec section 29):
-- a simple cake costs 1 point, detailed 2, complex 3, special projects are
-- assigned manually. Counting orders alone would let six three-tier cakes
-- book the same day.

-- ------------------------------------------------------------ time slots --
-- Reusable two-hour windows for pickup and delivery.

create table time_slots (
  id            uuid primary key default gen_random_uuid(),
  start_time    time not null,
  end_time      time not null,
  label         text,
  max_orders    integer not null default 3 check (max_orders >= 0),
  applies_to    fulfillment_method,      -- null = both pickup and delivery
  active        boolean not null default true,
  display_order integer not null default 0,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  check (end_time > start_time),
  unique (start_time, end_time, applies_to)
);

create trigger time_slots_updated_at before update on time_slots
  for each row execute function set_updated_at();

-- ----------------------------------------------------- availability dates --
-- One row per calendar day that has been touched. A missing row means
-- "default capacity, not blocked" — the backend materialises the row on the
-- first reservation for that date.
--
-- reserved_points is maintained ONLY by reserve_production_capacity() so the
-- overbooking guard has a single writer.

create table availability_dates (
  date            date primary key,
  max_points      smallint not null check (max_points >= 0),
  reserved_points smallint not null default 0 check (reserved_points >= 0),
  max_orders      integer,
  reserved_orders integer not null default 0 check (reserved_orders >= 0),
  blocked         boolean not null default false,
  rush_available  boolean not null default true,
  notes           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint availability_dates_not_overbooked check (reserved_points <= max_points)
);

create index availability_dates_open_idx
  on availability_dates (date)
  where not blocked;

create trigger availability_dates_updated_at before update on availability_dates
  for each row execute function set_updated_at();

comment on constraint availability_dates_not_overbooked on availability_dates is
  'Last line of defence against overbooking. The reservation function also '
  'guards with a conditional UPDATE, but this constraint means no code path '
  'anywhere can exceed the daily point limit.';

-- ------------------------------------------------- time slot availability --
-- Per-date override of a slot: block it, or cap it differently.

create table time_slot_availability (
  date            date not null,
  time_slot_id    uuid not null references time_slots (id) on delete cascade,
  max_orders      integer not null check (max_orders >= 0),
  reserved_orders integer not null default 0 check (reserved_orders >= 0),
  blocked         boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  primary key (date, time_slot_id),
  constraint time_slot_not_overbooked check (reserved_orders <= max_orders)
);

create index time_slot_availability_date_idx on time_slot_availability (date) where not blocked;

create trigger time_slot_availability_updated_at before update on time_slot_availability
  for each row execute function set_updated_at();
