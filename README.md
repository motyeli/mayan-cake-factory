# Mayan's Cake Factory

AI-assisted custom cake design and ordering system for Mayan's bakery, Paris.

Customers anywhere in the world describe a cake in conversation; the system turns that into a
**structured, feasibility-validated, priced, capacity-checked order** with a generated visual
concept. Mayan manages catalog, pricing, capacity and orders through a private admin area.

```
Conversation → Structured spec → Feasibility → Availability → Price → Image → Revisions → Approval → Order
```

> **Architectural rule:** the AI proposes, deterministic code decides. Prices, availability,
> feasibility, delivery zones and order status are computed by database-driven Python — never by
> the language model.

## Status

Built in phases. See `docs/` for architecture, API, database, deployment, security and
troubleshooting guides.

| Phase | Scope | State |
|---|---|---|
| 0 | Repository & Git foundation | ✅ |
| 1 | Supabase schema + seed | ✅ |
| 2 | Backend + frontend skeleton | ✅ |
| 3 | UX/UI via Stitch | ⏳ |
| 4 | Catalog & business rules | ⏳ |
| 5 | AI conversation | ⏳ |
| 6 | Design generation & revisions | ⏳ |
| 7 | Ordering & admin | ⏳ |
| 8 | Deployment & docs | 🔸 dev live, prod pending |

## Architecture

Two independently deployable services plus Supabase. No frontend framework.

```
frontend/   Flask + Jinja + vanilla JS   ──fetch (CORS)──▶   backend/   FastAPI + Pydantic v2
                                                                  │
                                                                  ▼
                                              Supabase: Postgres · Storage · Auth
```

## Live environments

| Environment | Frontend | Backend | Branch |
|---|---|---|---|
| Development | https://frontend-development-706f.up.railway.app | https://backend-development-1382.up.railway.app | `dev` |
| Production | not deployed yet | not deployed yet | `main` |

Verified on the development deployment: `/health` reports `database: ok`, and a
full order — design generated, stored, approved, confirmed — was placed end to
end against it.

See [docs/deployment.md](docs/deployment.md).

## Supabase projects

Development and production are **separate projects** and never share a database, a
service-role key, storage or secrets. Project refs are not secrets; the keys are, and they live
only in gitignored `.env` files.

| Environment | Project | Ref | Region |
|---|---|---|---|
| Development | `cake-factory-dev` | `ntngfmeucypgpjvdxcdo` | `eu-central-1` |
| Production | `cake-factory-prod` | `zdbzwjqhfzjwpctmrclg` | `eu-central-1` |

```bash
supabase link --project-ref ntngfmeucypgpjvdxcdo   # dev
supabase db push                                   # apply migrations
python scripts/db_check.py                         # read-only seed summary
```

Seed data lives in a migration, not only in `supabase/seed.sql`, so `db push` delivers identical
catalog rows to both remote projects. Every statement is idempotent.

## Requirements

| Tool | Purpose |
|---|---|
| Python 3.12+ | both services |
| Supabase CLI | migrations, seeds, project linking |
| GitHub CLI | branches, pull requests, releases |
| Railway CLI | deployment (Phase 8) |
| Docker *(optional)* | only needed for the local Supabase stack |

## Local development

```bash
cp .env.example backend/.env      # then fill in the values
bash scripts/validate_environment.sh

python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv/Scripts/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt

uvicorn app.main:app --reload --port 8001 --app-dir backend   # backend  → :8001
python frontend/app.py                                        # frontend → :8000
```

`AI_MODE=mock` runs the entire flow with **no AI credentials**: a deterministic LLM adapter and an
SVG cake renderer stand in for the real providers.

## Tests

The two services are tested separately because both define a module called `app`; putting them on
one import path would make `import app` ambiguous.

```bash
pytest                                   # backend suite (see pyproject.toml)
pytest -m integration                    # adds tests that hit the dev Supabase project
cd frontend && pytest                    # frontend suite (see frontend/pytest.ini)
ruff check .
```

## Branches

`main` = production · `dev` = shared development. Feature branches off `dev`, merged by pull
request. See `CONTRIBUTING.md`.

## License

Private, single-tenant product. Not a multi-bakery SaaS.
