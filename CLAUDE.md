## RESUME HERE

Last worked: **2026-08-13**. Everything below is merged into `dev` and green.

**Tests: 227 backend + 45 frontend, `ruff` clean. CI green. Live OpenAI verified.**

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
| 8 Deployment + docs | done: both environments live, 8 docs written |

**All nine phases are complete.** What remains is the go-live checklist, not
construction.

### Deployed and verified

Railway project `mayan-cake-factory` — `0eff19da-70d4-4f5a-9caf-0ead71ed0707`.

| Env | Branch | Frontend | Backend |
|---|---|---|---|
| `dev` | `dev` | frontend-dev-3e33 | backend-dev-b0f4 |
| `production` | `main` | frontend-production-d6f7 | backend-production-fabf8 |

All four on `*.up.railway.app`. **Both environments deploy `SUCCESS` from their
own branch** — production from `main`, confirmed at the deployment level, not
only by `/health`.

Both backends return `"database": "ok"` and `"missing_credentials": []`.
Production reports `environment: production` and runs `AI_MODE=mock` on purpose
— it is set up, not open for business.

Rebuilt from scratch on 2026-08-14. The previous project was deleted; it had
reached its shape by duplicating dev into production, which left production
serving an inherited image while every build from `main` failed behind a green
health check.

**The lesson that cost the most: a healthy `/health` describes the *running
image*. It says nothing about whether the last deploy succeeded.** Check both:

```bash
railway deployment list --service backend --environment production   # SUCCESS on branch=main
curl -s https://backend-production-fabf8.up.railway.app/health
```

### Railway's model, learned the hard way

- **Services are project-level; each environment holds an *instance*.** An
  environment created *before* the services exist gets no instances, and then
  nothing can deploy into it — `service source connect`, `redeploy`,
  `serviceInstanceDeploy`, `environmentTriggersDeploy` and `railway up` all
  fail with "Service Instance not found". The only fix is
  `railway environment new <name> --duplicate <existing>`.
- **Branch tracking is a *deployment trigger*, not a service field.** There is
  no `branch` on ServiceInstance. `railway add --branch X` creates triggers in
  **every** environment, so production must be repointed afterwards via
  `deploymentTriggerUpdate`.
- **Duplicating an environment copies its variables**, including Supabase
  credentials. Overwrite them immediately or production talks to the dev
  database — invisible until someone reads the data.
- `railway domain` generates domains automatically on first deploy.

Isolation was proven rather than assumed: order `MCF-20260813-01002` returns
200 on dev and **404 on prod**, while both show identical seeded catalogs.

A full order was placed end to end on the deployed development stack: design
generated, stored in Supabase Storage, served through a signed URL, order
MCF-20260813-01002 confirmed at 336.00.

### Going live — the only remaining work

The checklist lives in `docs/deployment.md`. In short:

1. Set `AI_MODE=live` plus `LLM_API_KEY` and `IMAGE_API_KEY` on the production
   backend. **The user must set these themselves — never paste a key into chat.**
2. Create Mayan's admin account in the **production** project: a Supabase Auth
   user AND an `admin_profiles` row with `active = true`. The user alone gets 403.
3. Delete `test-admin@cake-factory.local` from the dev project.
4. Self-host Playfair Display and DM Sans (AD-12).
5. Check the Railway and Supabase bill before leaving production running.

### Gotchas that cost time twice each

- **"Failed to fetch" is almost never CORS.** Check `/openapi.json` route count
  first — a stale backend holding the port serves an old route table and the
  404 looks identical to a CORS failure. Kill listeners by port, not name.
- **`supabase link` is global state.** After pushing to production, re-link to
  dev or the next push goes to the wrong database.
- **Supabase silently skips** migrations not matching `<14-digit>_name.sql`.
  A skipped migration looks exactly like a successful push. CI checks this.
- **Railway builds from the repo root** via `RAILWAY_DOCKERFILE_PATH`; locally
  use `docker build -f backend/Dockerfile .`, never `docker build backend/`.
- **OpenAPI is disabled in production** — generate API docs from dev.
- **Stitch queues rather than fails.** A timeout means nothing; never retry, it
  just queues another job. Wait, then `list_screens`.
- `tzdata` must be installed — Windows and `python:slim` have no IANA database.

### Known gaps

- **No fulfilment page.** The APIs work (`/delivery/calculate`,
  `/availability/check`, order creation); there is no screen for picking a
  date, slot and address. The order flow goes through the API directly.
- Catalog and availability have working APIs but no admin screens yet
  (acceptance criteria 24 and 25 are API-only).
- Stitch never produced the fulfilment screen or the two admin table screens;
  those pages extend the existing design language instead (AD-35).

All three are listed in `docs/assumptions.md` so a reader does not have to
discover them.

### Still needed from the user

- Mayan's admin email and password, for the production account
- The OpenAI key on production, when going live — set by the user, not pasted
  into chat
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
