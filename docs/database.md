# Database

Postgres via Supabase. Two projects with identical schemas and no shared data.

| | Project ref |
|---|---|
| development | `ntngfmeucypgpjvdxcdo` |
| production | `zdbzwjqhfzjwpctmrclg` |

Verified isolated, not merely configured: an order created in development
returns 404 in production.

## Conventions

**Money is `bigint` cents.** No `numeric`, no `float`. `33600` is $336.00.
Every intermediate calculation stays integral and rounds half-up exactly once
at the end, so a total never disagrees with the sum of its lines.

**Percentages are basis points** (`2000` = 20%), for the same reason.

**Catalog rows deactivate, never delete.** `active = false` keeps an old order
readable — deleting a discontinued flavour would corrupt the history of every
order that used it.

**Timestamps are `timestamptz`.** Dates the customer chooses are plain `date`;
"14 August" is a calendar day, not an instant.

## Tables by purpose

**What the bakery sells** — `cake_sizes`, `cake_flavours`, `fillings`,
`frostings`, `design_styles`, `decoration_options`, `dietary_options`. Each
row carries its own price adjustment. Mayan edits these; nothing is deployed.

**What it will not make** — `feasibility_rules`. Data, not code: a rule names a
condition and whether it blocks or needs approval. A new constraint is an
INSERT.

**What things cost** — `pricing_rules` (rush windows, complexity multipliers,
surcharges) plus the catalog's own adjustments.

**Operational constants** — `settings`. Lead times, capacity defaults, bakery
coordinates, currency, timezone. Deliberately *not* environment variables:
these change on a Tuesday, and changing them must not need a deploy.

**Capacity** — `availability_dates` (max and reserved production points per
day), `time_slots`, `time_slot_availability`. Capacity is measured in
**production points**, not order count, because one wedding cake and one
cupcake tray are not the same day's work.

**Delivery** — `delivery_zones` with radius bands and fees.

**A customer's session** — `design_sessions` (token hash, expiry),
`ai_conversations` (customer-visible messages only), `cake_specifications` (the
operational source of truth), `cake_designs` (one row per version, never
overwritten), `uploaded_assets`.

**Orders** — `orders`, `order_status_history`, `customers`, `audit_log`.

## The two functions that are SQL

Everything else is Python. These are plpgsql because PostgREST cannot run a
multi-statement transaction, and this one must be atomic.

```sql
create_order_atomic(payload jsonb)
```

Reserves capacity, inserts the order, writes the first status-history row and
an audit row — all or nothing. It raises `DATE_FULL` or `TIME_SLOT_FULL`, which
the backend maps to HTTP 409.

The reservation inside it is a genuine compare-and-swap:

```sql
UPDATE availability_dates
   SET reserved_points = reserved_points + p
 WHERE day = d AND reserved_points + p <= max_points;
```

Two customers racing for the last Saturday slot: one matches a row, the other
matches zero and is rejected. Without this in a transaction, both would be
confirmed and Mayan would find out on Saturday morning.

## Row-level security

RLS is enabled on **every** table, with **no `anon` policy at all**.

That looks aggressive until you notice the browser never talks to Postgres. All
access goes through the backend with the service-role key, which bypasses RLS
by design. So `anon` needs no policy, and a leaked anon key grants nothing.

The service-role key exists only in the backend process. It is never sent to a
browser, never in the frontend service's variables, never committed.

## Storage

Three buckets — customer uploads, generated designs, admin assets. All private;
files are served through short-lived signed URLs.

Uploads are validated by **magic bytes**, not the declared `Content-Type`,
which is attacker-controlled. Size and dimensions are capped before the file is
stored.

## Migrations

Nine ordered files in `supabase/migrations/`, plus `seed.sql`.

```bash
supabase link --project-ref ntngfmeucypgpjvdxcdo
supabase db push
```

> Supabase **silently skips** files that do not match
> `<14-digit-timestamp>_name.sql`. A skipped migration is indistinguishable
> from a successful push until the schema turns out to be wrong. CI validates
> the filenames for exactly this reason.

> `supabase link` is global state. After pushing to production, re-link to
> development or the next push goes to the wrong database.

Migrations do not roll back with a deployment. Undoing one needs a new one.
