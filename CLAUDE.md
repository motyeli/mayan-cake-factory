# CLAUDE.md

Working notes for this repository. Read before changing anything.

## RESUME HERE

Last worked: **2026-08-12**. Everything below is merged into `dev` and green.

| Phase | State |
|---|---|
| 0 Repository foundation | ✅ |
| 1 Supabase schema + seed | ✅ dev **and** prod, 9 migrations |
| 2 Service skeletons | ✅ both services boot |
| 3 UX via Stitch | ⚠️ **4 of 13 screens** — quota-limited, see below |
| 4 Business rules | ✅ pricing, feasibility, delivery, capacity |
| 5 AI conversation | ⏭️ **NEXT** |
| 6 Design generation | ⏳ |
| 7 Ordering + admin | ⏳ |
| 8 Deployment | ⏳ |

**Tests: 106 backend + 10 frontend, `ruff` clean.**

### Next task — Phase 5, AI conversation

Build in `backend/app/services/ai/`:

1. `LLMProvider` protocol + a `MockLLM` that needs no credentials (tests depend
   on it being deterministic).
2. An OpenAI adapter using JSON-schema structured output. The key goes in
   `backend/.env` as `LLM_API_KEY`, then `AI_MODE=live`. **Not yet supplied.**
3. A specification builder that resolves catalog **names to IDs** — an unknown
   name is a re-ask, never an invention.
4. Missing-information logic: `CakeSpecification.missing_labels()` already
   exists and returns customer-ready phrasing.
5. Prompt-injection guards: system instructions are fixed and never
   concatenated with customer text.
6. Persist messages to `ai_conversations` with usage metadata, no hidden
   reasoning.

The engines it must call are done and tested:
`services/pricing/engine.py`, `services/feasibility/engine.py`,
`services/delivery/geo.py`, `services/availability/rules.py`, and the
endpoints in `api/v1/quoting.py`.

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
