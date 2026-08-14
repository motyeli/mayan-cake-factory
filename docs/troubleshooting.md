# Troubleshooting

Ordered by how often each has actually happened during this build.

## "Failed to fetch" in the browser

Almost never CORS. **Check the routes first:**

```bash
curl -s http://127.0.0.1:8001/openapi.json | python -c "import json,sys; print(len(json.load(sys.stdin)['paths']))"
```

A stale backend from an earlier session holding the port will serve an old,
smaller route table, and the resulting 404 looks exactly like a CORS failure.
Kill listeners **by port**, not by process name:

```powershell
Get-NetTCPConnection -LocalPort 8001 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

If the route table is right, then check CORS: `localhost` and `127.0.0.1` are
**different origins**. `ALLOWED_ORIGINS` must list both in development.

## A new route returns 404 locally

The Flask dev server runs with `use_reloader=False`. Restart it.

## `/health` says `"database": "unreachable"`

- Supabase variables wrong or missing — `missing_credentials` in the same
  response names them.
- The Supabase project is paused. Free-tier projects pause when idle; open the
  dashboard to wake it.
- `supabase link` is pointed at the wrong project.

## `ZoneInfo("Europe/Paris")` raises

`tzdata` is not installed. Windows ships no IANA database and `python:*-slim`
images do not either. It is pinned in `backend/requirements.txt`; if you built
an image without it, every lead-time calculation fails.

## Admin API returns 403 to a real user

A valid Supabase account is not an administrator. Insert an `admin_profiles`
row with `active = true` and matching `auth_user_id`.

## An order returns 409 at the last step

Working as intended. Either the day filled while the customer was deciding, or
the design was never approved, or a feasibility rule now rejects it. The
`details` field names the reason: `DATE_FULL`, `TIME_SLOT_FULL`,
`REVISION_LIMIT_REACHED`.

## A migration "applied" but the schema is wrong

Supabase **silently skips** files that do not match `<14-digit>_name.sql`. A
skipped migration looks exactly like a successful push. CI validates the
filenames for this reason; run it locally:

```bash
ls supabase/migrations/*.sql | xargs -n1 basename
```

## `supabase db push` wrote to the wrong project

`supabase link` is global state. After touching production, **re-link to dev**:

```bash
supabase link --project-ref ntngfmeucypgpjvdxcdo
```

## Railway deploy succeeded but the page points at localhost

Expected on the **first** deploy. `ALLOWED_ORIGINS` needs the frontend domain
and `BACKEND_URL` needs the backend's, and neither exists until after deploying.
Set them, then redeploy. Sequence, not failure.

## Railway says "ServiceInstance not found" and nothing can deploy

The environment has no *instance* of the service. Services are project-level;
each environment holds an instance, and an environment created **before** the
services existed never gets one. Every deploy route then fails the same way —
`service source connect`, `redeploy`, `railway up`, `serviceInstanceDeploy`,
`environmentTriggersDeploy`. `serviceInstanceUpdate` returns `true` and creates
nothing, which is the confusing part.

No command repairs it. Duplicate an environment that already has instances:

```bash
railway environment delete <broken-env> --yes
railway environment new <name> --duplicate <working-env>
```

Then fix the two things a duplicate inherits: its **branch triggers** point at
the source environment's branch, and its **variables** are the source
environment's — including `SUPABASE_URL` and the service-role key.

## A deploy succeeded but the wrong branch is running

Check what the deployment list says, not what you configured:

```bash
railway deployment list --service backend --environment production
```

Branch tracking is a *deployment trigger*, not a service property, and
`railway add --branch X` writes triggers into **every** environment at once. A
second environment on a different branch must be repointed with
`deploymentTriggerUpdate` — there is no CLI command for it.

## Railway build fails on `COPY requirements.txt`

The build context is the **repository root**, so paths are root-relative
(`COPY backend/requirements.txt`). Locally you must name the file:

```bash
docker build -f backend/Dockerfile -t cake-backend .
```

## Stitch generation never lands

It **queues** rather than failing, and a timeout tells you nothing. Never retry
on a timeout — each retry queues another job. Wait 60–120 s, then
`list_screens`. If jobs still never land, the project is out of stored-asset
space: delete screens in the Stitch UI and the queue drains immediately.

## An image never finishes generating

Generation takes about a minute with a real provider. If a design row stays
`generating` forever, the background task died with the process — in-process
tasks do not survive a restart. The customer can regenerate; the row records
`error_info` when the provider itself failed.
