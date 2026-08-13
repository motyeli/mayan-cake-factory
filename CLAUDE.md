## RESUME HERE

Last worked: **2026-08-13**. Everything below is merged into `dev` and green.

**Tests: 227 backend + 45 frontend, `ruff` clean. Live OpenAI verified.**

| Phase | State |
|---|---|
| 0 Repository foundation | done |
| 1 Supabase schema + seed | done, dev AND prod, 9 migrations |
| 2 Service skeletons | done |
| 3 UX via Stitch | partial: 8 screens generated, 9 pages built |
| 4 Business rules | done: pricing, feasibility, delivery, capacity |
| 5 AI conversation | done: mock + OpenAI, injection guards |
| 6 Design generation | done: async, revisions capped, uploads validated |
| 7 Ordering + admin | done: orders, 4 admin screens, CRM, audit |
| 8 Deployment | NEXT |

### The product works end to end, in a browser

Customer: `/` then `/design` then `/design/summary` then `/design/preview`
then a real order number at `/orders/<number>`.
Admin: `/admin/login` then `/admin`, `/admin/orders`, `/admin/orders/<id>`.

Verified: a revision moved 336.00 to 420.00 and redrew the cake with two
tiers; a standard order auto-confirmed as MCF-20260813-01000; a fresh-flowers
order became awaiting_bakery_approval with the price marked an estimate;
approving it cleared the estimate; jumping it to completed returned 409; a
price override from 372.00 to 399.00 was recorded with a reason.

### Next task, Phase 8 deployment

1. `npm i -g @railway/cli`, then the user runs `railway login`.
2. Two environments, development from branch `dev` and production from `main`.
   Two services each: root directories `backend` and `frontend`. Dockerfiles
   and railway.toml already exist with health check paths wired.
3. Environment variables per service. `backend/.env.production` already holds
   the production Supabase credentials; ALLOWED_ORIGINS and the two URLs still
   need the real Railway domains.
4. GitHub Actions: pytest for both suites, ruff, and migration validation.
5. The docs deliverables: architecture, api, database, deployment,
   troubleshooting, security, assumptions, credentials-required.
6. Verify with `railway status` and a live /health on both environments.
   Do not claim a deploy succeeded without seeing it.

### Cleanup owed before production

- Delete `test-admin@cake-factory.local` from the dev project. It has a
  throwaway password and only existed to exercise sign-in.
- Create Mayan's real account: a Supabase Auth user is NOT enough. Insert a
  matching `admin_profiles` row with `active = true`, or the API returns 403.
- Self-host Playfair Display and DM Sans. They currently fall back to system
  fonts, because a Google Fonts CDN link would send visitor IPs to a third
  party (AD-12).

### Known gaps

- Catalog and availability have working APIs but no admin screens yet
  (acceptance criteria 24 and 25 are API-only).
- Stitch never produced the fulfilment screen or the two admin table screens;
  those pages extend the existing design language instead (AD-35).

### Still needed from the user

- Railway account, for Phase 8
- Mayan's admin email and password
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
