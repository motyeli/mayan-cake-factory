-- Transaction-safe order creation and capacity reservation.
--
-- WHY THIS IS SQL AND NOT PYTHON: PostgREST cannot run multi-statement
-- transactions. Reserving capacity and inserting the order must either both
-- happen or neither, otherwise two customers racing for the last slot on a
-- Saturday both get confirmed. A plpgsql function runs in one transaction,
-- so the conditional UPDATE below is a genuine compare-and-swap.
--
-- Pricing, feasibility and lead-time logic stay in Python where they are
-- pure functions and cheap to test. Only the commit step lives here.

-- ------------------------------------------------------------- settings --

create or replace function setting_int(p_key text, p_default integer)
returns integer
language sql
stable
as $$
  select coalesce((select (value #>> '{}')::integer from settings where key = p_key), p_default);
$$;

comment on function setting_int is
  'Reads an integer setting with a fallback, so a missing row never breaks a booking.';

-- -------------------------------------------------------- order numbers --

create sequence order_number_seq start 1000;

create or replace function next_order_number()
returns text
language sql
volatile
as $$
  select 'MCF-' || to_char(now() at time zone 'Europe/Paris', 'YYYYMMDD')
              || '-' || lpad(nextval('order_number_seq')::text, 5, '0');
$$;

comment on function next_order_number is
  'Human-readable, globally unique. The sequence is not reset daily; the date '
  'is for readability and the sequence alone guarantees uniqueness.';

-- --------------------------------------------------- capacity reservation --

create or replace function reserve_production_capacity(
  p_date         date,
  p_points       smallint,
  p_time_slot_id uuid default null
)
returns void
language plpgsql
as $$
declare
  v_blocked   boolean;
  v_updated   integer;
  v_slot_max  integer;
begin
  -- Materialise the day with the configured defaults if it has never been touched.
  insert into availability_dates (date, max_points, max_orders)
  values (p_date,
          setting_int('daily_production_points', 10)::smallint,
          setting_int('max_orders_per_day', 6))
  on conflict (date) do nothing;

  -- Serialise concurrent bookings for this date.
  select blocked into v_blocked
    from availability_dates
   where date = p_date
     for update;

  if v_blocked then
    raise exception 'DATE_BLOCKED';
  end if;

  -- Compare-and-swap: the row only updates if capacity genuinely remains.
  -- A loser in a race matches zero rows and is rejected rather than silently
  -- overbooking the day.
  update availability_dates
     set reserved_points = reserved_points + p_points,
         reserved_orders = reserved_orders + 1
   where date = p_date
     and reserved_points + p_points <= max_points
     and (max_orders is null or reserved_orders + 1 <= max_orders);

  get diagnostics v_updated = row_count;
  if v_updated = 0 then
    raise exception 'DATE_FULL';
  end if;

  if p_time_slot_id is not null then
    select max_orders into v_slot_max from time_slots where id = p_time_slot_id and active;
    if v_slot_max is null then
      raise exception 'TIME_SLOT_UNAVAILABLE';
    end if;

    insert into time_slot_availability (date, time_slot_id, max_orders)
    values (p_date, p_time_slot_id, v_slot_max)
    on conflict (date, time_slot_id) do nothing;

    update time_slot_availability
       set reserved_orders = reserved_orders + 1
     where date = p_date
       and time_slot_id = p_time_slot_id
       and not blocked
       and reserved_orders + 1 <= max_orders;

    get diagnostics v_updated = row_count;
    if v_updated = 0 then
      raise exception 'TIME_SLOT_FULL';
    end if;
  end if;
end;
$$;

create or replace function release_production_capacity(
  p_date         date,
  p_points       smallint,
  p_time_slot_id uuid default null
)
returns void
language plpgsql
as $$
begin
  update availability_dates
     set reserved_points = greatest(0, reserved_points - p_points),
         reserved_orders = greatest(0, reserved_orders - 1)
   where date = p_date;

  if p_time_slot_id is not null then
    update time_slot_availability
       set reserved_orders = greatest(0, reserved_orders - 1)
     where date = p_date and time_slot_id = p_time_slot_id;
  end if;
end;
$$;

comment on function release_production_capacity is
  'Called when an order is cancelled or rejected so the slot returns to the pool.';

-- ------------------------------------------------------ atomic order create --
-- Everything an order needs, committed together: customer, capacity,
-- order row, opening status history, design/spec linkage and the audit entry.

create or replace function create_order_atomic(payload jsonb)
returns jsonb
language plpgsql
as $$
declare
  v_customer_id  uuid;
  v_order_id     uuid;
  v_order_number text;
  v_status       order_status;
  v_points       smallint := (payload ->> 'production_points')::smallint;
  v_date         date     := (payload ->> 'fulfillment_date')::date;
  v_slot         uuid     := nullif(payload ->> 'time_slot_id', '')::uuid;
  v_session      uuid     := nullif(payload ->> 'design_session_id', '')::uuid;
  v_design       uuid     := nullif(payload ->> 'approved_design_id', '')::uuid;
begin
  -- Status is decided by the backend rule engine, never by the caller's whim:
  -- we only accept the two legal opening states.
  v_status := (payload ->> 'status')::order_status;
  if v_status not in ('confirmed', 'awaiting_bakery_approval') then
    raise exception 'INVALID_INITIAL_STATUS';
  end if;

  -- Reserve first: if the day is full we fail before creating anything.
  perform reserve_production_capacity(v_date, v_points, v_slot);

  -- Reuse an existing customer record when the email matches, so the CRM
  -- accumulates order history instead of duplicating people.
  select id into v_customer_id
    from customers
   where email is not null
     and lower(email) = lower(payload ->> 'customer_email')
   limit 1;

  if v_customer_id is null then
    insert into customers (full_name, email, phone)
    values (payload ->> 'customer_name',
            nullif(payload ->> 'customer_email', ''),
            nullif(payload ->> 'customer_phone', ''))
    returning id into v_customer_id;
  else
    update customers
       set full_name = coalesce(nullif(payload ->> 'customer_name', ''), full_name),
           phone     = coalesce(nullif(payload ->> 'customer_phone', ''), phone)
     where id = v_customer_id;
  end if;

  v_order_number := next_order_number();

  insert into orders (
    order_number, customer_id, design_session_id, approved_design_id, status,
    fulfillment_method, fulfillment_date, time_slot_id,
    delivery_address, delivery_latitude, delivery_longitude,
    delivery_zone_id, delivery_distance_km,
    subtotal_cents, surcharge_cents, delivery_fee_cents, discount_cents,
    total_price_cents, currency, price_breakdown, price_is_estimate,
    payment_status, payment_method, amount_due_cents,
    deposit_required, deposit_amount_cents,
    complexity_level, production_points, is_rush_order,
    requires_manual_approval, manual_approval_reasons, has_allergen_warning,
    customer_notes
  )
  values (
    v_order_number, v_customer_id, v_session, v_design, v_status,
    (payload ->> 'fulfillment_method')::fulfillment_method, v_date, v_slot,
    nullif(payload ->> 'delivery_address', ''),
    nullif(payload ->> 'delivery_latitude', '')::numeric,
    nullif(payload ->> 'delivery_longitude', '')::numeric,
    nullif(payload ->> 'delivery_zone_id', '')::uuid,
    nullif(payload ->> 'delivery_distance_km', '')::numeric,
    (payload ->> 'subtotal_cents')::bigint,
    coalesce((payload ->> 'surcharge_cents')::bigint, 0),
    coalesce((payload ->> 'delivery_fee_cents')::bigint, 0),
    coalesce((payload ->> 'discount_cents')::bigint, 0),
    (payload ->> 'total_price_cents')::bigint,
    coalesce(nullif(payload ->> 'currency', ''), 'USD'),
    coalesce(payload -> 'price_breakdown', '{}'::jsonb),
    coalesce((payload ->> 'price_is_estimate')::boolean, false),
    'pending_external_payment',
    nullif(payload ->> 'payment_method', '')::payment_method,
    (payload ->> 'total_price_cents')::bigint,
    coalesce((payload ->> 'deposit_required')::boolean, false),
    coalesce((payload ->> 'deposit_amount_cents')::bigint, 0),
    (payload ->> 'complexity_level')::smallint, v_points,
    coalesce((payload ->> 'is_rush_order')::boolean, false),
    coalesce((payload ->> 'requires_manual_approval')::boolean, false),
    coalesce(
      (select array_agg(value #>> '{}') from jsonb_array_elements(payload -> 'manual_approval_reasons')),
      '{}'::text[]),
    coalesce((payload ->> 'has_allergen_warning')::boolean, false),
    nullif(payload ->> 'customer_notes', '')
  )
  returning id into v_order_id;

  insert into order_status_history (order_id, previous_status, new_status, reason, changed_by_label)
  values (v_order_id, null, v_status, 'Order created', 'system');

  if v_session is not null then
    update design_sessions     set status = 'ordered'   where id = v_session;
    update cake_specifications set order_id = v_order_id where session_id = v_session;
    update cake_designs        set order_id = v_order_id where session_id = v_session;
    update uploaded_assets     set order_id = v_order_id where session_id = v_session;
  end if;

  insert into audit_log (actor_label, action, entity_type, entity_id, new_data)
  values ('system', 'order.created', 'order', v_order_id::text,
          jsonb_build_object('order_number', v_order_number,
                             'status', v_status,
                             'total_price_cents', (payload ->> 'total_price_cents')::bigint,
                             'production_points', v_points));

  return jsonb_build_object('id', v_order_id, 'order_number', v_order_number, 'status', v_status);
end;
$$;

comment on function create_order_atomic is
  'Single-transaction order commit. Raises DATE_BLOCKED, DATE_FULL, '
  'TIME_SLOT_FULL, TIME_SLOT_UNAVAILABLE or INVALID_INITIAL_STATUS; the '
  'backend maps these messages to HTTP 409 responses.';
