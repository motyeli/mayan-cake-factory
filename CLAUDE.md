## RESUME HERE

Last worked: **2026-08-13**. Everything below is merged into `dev` and green.

**Tests: 227 backend + 32 frontend, `ruff` clean. Live OpenAI verified.**

| Phase | State |
|---|---|
| 0 Repository foundation | ✅ |
| 1 Supabase schema + seed | ✅ dev **and** prod, 9 migrations |
| 2 Service skeletons | ✅ |
| 3 UX via Stitch | ⚠️ 8 screens generated, **5 customer pages built** |
| 4 Business rules | ✅ pricing, feasibility, delivery, capacity |
| 5 AI conversation | ✅ mock + OpenAI, injection guards |
| 6 Design generation | ✅ async, revisions capped, uploads validated |
| 7 Ordering + admin | ⚠️ **backend done — admin UI not built** |
| 8 Deployment | NEXT AFTER ADMIN UI |

### A customer can complete the whole journey in a browser

`/` then `/design` then `/design/summary` then `/design/preview` to a real
order number. Verified in Chrome: one message produces a full specification
and price; a revision moved 336.00 to 420.00 and redrew the cake with two
tiers; a standard order auto-confirmed as MCF-20260813-01000 and a
fresh-flowers order became awaiting_bakery_approval with the price marked an
estimate.

### Next task, the admin interface

All 19 admin endpoints exist and no screen uses them. Build:

1. `/admin/login` calling POST /api/v1/admin/auth/session, keeping the JWT in
   sessionStorage and sending it as a Bearer token. Stitch screen captured at
   docs/design/screens/admin-login.html
2. `/admin` dashboard calling GET /api/v1/admin/dashboard. Keep the four money
   figures visually distinct; unpaid value must never read as revenue. Screen
   captured at docs/design/screens/admin-dashboard.html
3. `/admin/orders` with the section 33 filters. Screen NOT yet generated.
4. `/admin/orders/<id>` detail, approve, reject, status change, and price
   override with a mandatory reason. Screen NOT yet generated.

Then Phase 8: Railway, CI, and the docs deliverables.

Before creating Mayan's admin account: a Supabase Auth user is not enough.
Insert a matching row in admin_profiles with active = true, or the API
returns 403.

### Stitch, how it actually behaves

Generation queues rather than failing. A timeout says nothing, and retrying on
one is how three duplicate chat screens appeared. Wait 60 to 120 seconds, then
list_screens. If jobs never land the project is out of stored-asset space:
delete screens in the Stitch UI and the queue drains. Everything generated so
far is saved under docs/design/.

### Still needed from the user

- Railway account, for Phase 8
- Mayan's admin email and password, to create the first admin_profiles row
- Optional: Maps API key. The mock is production-plausible for Paris.

## What this is

AI-assisted custom cake design and ordering for **one** bakery in Paris. Not a
multi-tenant SaaS — never add support for multiple bakeries or branches.

```
Conversation → Structured spec → Feasibility → Availability → Price → Image → Revisions → Approval → Order
```

## The rule that overrides everything

> **The AI proposes, deterministic code decides.**

The language model must never calculate a price, invent availability, invent a
catalog option, decide feasibility, or set an order status. Every option it can
offer exists as a database row and is resolved by ID. An unknown flavour name
causes a re-ask, never an invention.

If a change would let the model decide any of those, it is wrong regardless of
how well it works in a demo.

## Non-negotiables

- **Money is `bigint` cents.** Never float, never numeric-as-money. Percentages
  are basis points (2000 = 20%). Use `apply_basis_points()`.
- **No frontend framework.** HTML, CSS, vanilla JS, Flask + Jinja. No React,
  Vue, Angular, Next — and no Tailwind CDN (Stitch emits one; strip it).
- **No Google Fonts CDN.** It sends visitor IPs to a third party — a live GDPR
  problem for a French business. Self-host or use system fallbacks.
- **Backend enforces limits.** Revision counts, prices, availability and status
  transitions are enforced server-side. Frontend counters are courtesy only.
- **Never log secrets.** The JSON formatter redacts secret-looking field names
  structurally; do not add a code path that bypasses it.
- **The service-role key never reaches a browser.**

## Layout

```
backend/app/
  core/        config, logging, errors, rate limiting, supabase client
  schemas/     catalog rows, cake specification (pydantic)
  services/    pricing/ feasibility/ availability/ delivery/ ai/ orders/ …
  api/v1/      thin route handlers — no business logic here
frontend/      Flask + Jinja + vanilla JS
supabase/migrations/   plain SQL, version-controlled, the schema source of truth
docs/design/   Stitch output + screen briefs
```

Business logic lives in `services/`, as **pure functions** over
`(specification, catalog, settings)`. That is what makes the rule tests cheap —
keep it that way; do not reach for the database inside an engine.

## Commands

```bash
pytest                          # backend suite
cd frontend && pytest           # frontend suite (separate root — both define `app`)
ruff check .
bash scripts/validate_environment.sh
python scripts/db_check.py      # read-only DB summary (no psql/Docker on this machine)

uvicorn app.main:app --reload --port 8001 --app-dir backend
python frontend/app.py
```

`AI_MODE=mock` runs everything with no AI credentials.

## Gotchas that have already bitten

- **`supabase link` is global state.** After touching production, re-link to dev
  or the next `db push` writes to production.
- **Separate test roots.** Both services define `app`; one import path makes
  `import app` ambiguous. Backend uses `pyproject.toml`, frontend uses
  `frontend/pytest.ini`.
- **Stitch generation times out but still succeeds.** Never retry on a timeout —
  each retry queues another job. Wait 60–120 s, then `list_screens`. If jobs
  never land, the project is out of stored-asset space: delete screens in the
  UI and the queue drains. Not a generation quota; waiting does not help.
- **Stitch HTML is a design reference, never shipped.** It carries a Tailwind
  CDN script, a Google Fonts link and the Material Symbols icon font. Rebuild
  layouts on `tokens.css` with inline SVG icons.
- **Stitch also invents business facts.** Its home page promised a two-week lead
  time and a 50% credit-card deposit. Take the layout; read every price, policy
  and disclaimer from the catalog endpoint at runtime.
- **Kill stale dev servers by port before debugging.** An old backend holding
  port 8001 served only 2 routes, so a 404 looked exactly like a CORS failure.
  Check `/openapi.json` first.
- **Flask runs with `use_reloader=False`** — a newly added route 404s until the
  server is restarted.
- **PostgREST has no multi-statement transactions.** Order commit + capacity
  reservation is one plpgsql function, `create_order_atomic`. Do not split it.
- **`supabase-py` is synchronous** and would block the event loop. Use the
  `httpx` wrapper in `core/supabase.py`.

## Environments

| Env | Supabase project | Ref |
|---|---|---|
| dev | `cake-factory-dev` | `ntngfmeucypgpjvdxcdo` |
| prod | `cake-factory-prod` | `zdbzwjqhfzjwpctmrclg` |

Fully separate databases — verified. Keys live only in gitignored `.env` files.

## Working method

Nine phases, each a closed loop: build → test + lint → commit on a feature
branch → PR into `dev` → **write the phase log to the Obsidian vault** → report
→ **stop and say you are waiting for approval**.

Obsidian vault:
`C:\Users\Moty\Documents\Moty Course AI\moty obsidian vault\Mayan Cake Factory\`
(`Mayan Cake Factory.md` is the index; also `Architecture Decisions.md`,
`Verification Log.md`, `Open Questions and Risks.md`). Never put secrets there.

Branches: `main` = production, `dev` = development, feature branches off `dev`.
Never commit directly to `main`.

## Honesty rules for this project

- Do not claim a deployment succeeded without verifying it.
- Do not claim a CLI operation succeeded unless it returned success.
- Record what was actually executed and observed in `Verification Log.md`;
  keep "not yet verified" items explicitly listed.
- When an external dependency blocks a requirement, deliver everything around
  it and state the blocker with evidence. Do not quietly substitute a
  workaround for a stated requirement.
