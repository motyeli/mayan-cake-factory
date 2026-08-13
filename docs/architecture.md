# Architecture

## The rule everything else serves

> **The AI proposes. Deterministic code decides.**

Prices, availability, feasibility, delivery zones and order status are computed
by database-driven Python. The language model never calculates them.

This is not a policy written in a prompt — prompts are advisory. It is
structural: the model emits **names**, and `services/ai/resolver.py` maps them
onto catalog rows by ID. Everything downstream takes IDs. A flavour the bakery
does not make has nowhere to go.

```
customer message
  → sanitize          injection detection, invisible characters, length cap
  → language model    proposes an understanding, in NAMES
  → resolver          maps names to catalog rows, or asks again
  → pricing engine    computes the price
  → feasibility       decides what needs a human
  → capacity          reserves production points, transactionally
  → order
```

## Services

Two independently deployable services plus Supabase. No frontend framework
(spec §37).

```
frontend/   Flask + Jinja + vanilla JS  ──fetch (CORS)──▶  backend/  FastAPI
                                                               │
                                                               ▼
                                          Supabase: Postgres · Storage · Auth
```

The frontend holds **no secrets**. It renders HTML and calls the backend from
the browser, so there is exactly one place where business decisions are made.
The Supabase service-role key exists only in the backend process.

## Backend layout

```
app/
  core/          config, logging, errors, rate limiting, supabase client
  schemas/       catalog rows, cake specification (pydantic)
  services/
    ai/          providers, prompts, resolver, safety, conversation, sessions
    pricing/     what a cake costs
    feasibility/ whether it can be made, and by whom approved
    availability/lead time, rush, capacity arithmetic
    delivery/    geocoding, distance, zones
    orders/      creation, status machine, admin operations
    storage.py   uploads, validation, signed URLs
  repositories/  catalog and settings loading, cached
  security/      admin identity
  api/v1/        thin route handlers — no business logic
```

### Why the engines are pure functions

`pricing`, `feasibility`, `availability` and the order state machine take
`(specification, catalog, settings)` and return a result. They cannot reach a
database or a clock.

That is what makes the business rules cheap to test — most of the 227 backend
tests need no fixtures, no network and no mocking. It also means the same code
answers "what would this cost?" during a conversation and "what does this cost?"
at checkout, with no chance of the two disagreeing.

## Where state lives

| Concern | Home |
|---|---|
| What the bakery sells | catalog tables — editable by Mayan, no deploy |
| What it will not make | `feasibility_rules` — data, not code |
| What things cost | `pricing_rules` + catalog price adjustments |
| Operational constants | `settings` table, not environment variables |
| Conversation | `ai_conversations`, customer-visible messages only |
| The cake | `cake_specifications` — the operational source of truth |
| Design versions | `cake_designs`, one row per version, never overwritten |

Environment variables hold **infrastructure**: credentials, URLs, modes.
Anything Mayan might change on a Tuesday lives in the database.

## The one place logic is SQL

`create_order_atomic` and `reserve_production_capacity` are plpgsql.

PostgREST cannot run multi-statement transactions, and reserving capacity must
commit with the order or not at all — otherwise two customers racing for the
last Saturday slot both get confirmed. Inside one transaction the conditional
`UPDATE ... WHERE reserved_points + p <= max_points` is a genuine
compare-and-swap; the loser matches zero rows and is rejected.

Everything else stayed in Python. Business logic went to SQL only where
atomicity forced it.

## AI providers

Four protocols — `LLMProvider`, `ExtractionProvider`, `ImageGenerationProvider`,
`ImageRevisionProvider` — with mock and OpenAI implementations selected by
`AI_MODE`.

`AI_MODE=mock` is a real implementation, not a stub: it parses dates, guest
counts, flavours, colours and inscriptions, and renders an SVG cake from the
specification. The whole product and every test run offline.

A live provider that fails to construct falls back to the mock with a loud log
line, because a customer mid-conversation is better served by a working
assistant than a 500.

## Asynchronous image generation

Generation takes about a minute (measured: 57.4 s for `gpt-image-1`). An HTTP
request held open that long is cut by proxies.

So the design row is created immediately with a null image path, a background
task generates and uploads, and the client polls. **The design row is the job
record** — it already has prompt, provider, result id, usage and error columns.
No queue, no Redis.

*Ceiling:* in-process background tasks do not survive a restart. The row stays
pending and the customer regenerates. At five orders a day that is the right
trade.

## Security posture

- Customers are guests. A session is reached by token; only its SHA-256 hash is
  stored.
- Admins need a valid Supabase token **and** an active `admin_profiles` row.
- RLS is enabled on every table with **no** `anon` policy at all — the browser
  never talks to Postgres, so anon needs nothing.
- Secrets are redacted by the log formatter structurally, not by discipline.
- Uploads are validated by their bytes, not their declared type.

See [security.md](security.md).

## Deployment

Two Railway environments from two Git branches, two Supabase projects that
share nothing. See [deployment.md](deployment.md).
