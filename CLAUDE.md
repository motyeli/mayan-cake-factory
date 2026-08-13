# CLAUDE.md

Working notes for this repository. Read before changing anything.

## RESUME HERE

Last worked: **2026-08-13**. Everything below is merged into `dev` and green.

| Phase | State |
|---|---|
| 0 Repository foundation | ✅ |
| 1 Supabase schema + seed | ✅ dev **and** prod, 9 migrations |
| 2 Service skeletons | ✅ both services boot |
| 3 UX via Stitch | ⚠️ **4 of 13 screens** — quota-limited, see below |
| 4 Business rules | ✅ pricing, feasibility, delivery, capacity |
| 5 AI conversation | ✅ mock + OpenAI, injection guards |
| 6 Design generation | ⏭️ **NEXT** |
| 7 Ordering + admin | ⏳ |
| 8 Deployment | ⏳ |

**Tests: 170 backend + 10 frontend, `ruff` clean.**

### Next task — Phase 6, design generation and revisions

The AI and image provider layers already exist. What remains:

1. `POST /design-sessions/{token}/generate-design` — build the prompt with
   `prompts.image_prompt`, call `factory.get_image_provider()`, upload to the
   `cake-designs` Supabase bucket, insert a `cake_designs` row at version 1.
2. `POST /design-sessions/{token}/revisions` — **enforce the 3-revision limit in
   the backend** (409 on the 4th). Each revision must re-resolve, re-price,
   re-check feasibility and create a NEW version; earlier versions are never
   overwritten.
3. `GET /design-sessions/{token}/designs` — version history with signed URLs.
4. `POST /design-sessions/{token}/designs/{id}/approve` — one approved design per
   session (a partial unique index already enforces this).
5. Signed URLs from the private bucket, short expiry.

Already done and usable: `services/ai/mock_images.py` renders a real SVG cake
from the spec; `openai_llm.OpenAIImages` implements both image protocols;
`sessions.py` handles tokens and expiry.

### Stitch: 9 screens still to generate

Quota-limited, not broken. Briefs are ready in `docs/design/screen-briefs.md`.
Generate **one at a time**, expect a timeout, wait 60–120 s, then
`list_screens`. Project `2064497605592133162`, design system
`assets/2131526806607800438`.

### Still needed from the user

- **OpenAI API key** → `backend/.env` (mock mode works without it)
- **Railway account** → Phase 8
- **Mayan's admin email/password** → Phase 7

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
- **Stitch generation times out but still succeeds.** Do not retry on timeout —
  it starts a second job. Wait 60–120 s, then `list_screens`. One job at a time
  per project; a concurrent call returns `Request contains an invalid argument`.
  A create call timing out is NOT evidence that nothing was created.
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
