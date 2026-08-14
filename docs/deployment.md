# Deployment

Two Railway environments, each with two services, deploying from two Git
branches.

Railway project `mayan-cake-factory` — `0eff19da-70d4-4f5a-9caf-0ead71ed0707`.

| Railway environment | Git branch | Frontend | Backend | Supabase project |
|---|---|---|---|---|
| `dev` | `dev` | frontend-dev-3e33 | backend-dev-b0f4 | `cake-factory-dev` (`ntngfmeucypgpjvdxcdo`) |
| `production` | `main` | frontend-production-d6f7 | backend-production-fabf8 | `cake-factory-prod` (`zdbzwjqhfzjwpctmrclg`) |

They share nothing: separate databases, separate service-role keys, separate
storage buckets, separate URLs.

## The monorepo problem, and how it is solved

Railway normally builds a service from a **root directory** set in its web UI.
The CLI has no flag for it, so this project uses the documented alternative:
each service sets `RAILWAY_DOCKERFILE_PATH` and builds from the **repository
root**.

```
backend   RAILWAY_DOCKERFILE_PATH = backend/Dockerfile
frontend  RAILWAY_DOCKERFILE_PATH = frontend/Dockerfile
```

Both Dockerfiles therefore use root-relative `COPY` paths, and there is a
single `.dockerignore` at the root rather than one per service.

> **Building locally** you must name the file and pass the root as context:
> ```bash
> docker build -f backend/Dockerfile -t cake-backend .
> ```
> Running `docker build backend/` will fail. This is written at the top of both
> Dockerfiles too.

## First-time setup

Everything below is reproducible from a terminal. No step needs the web UI.

> **Order matters more than anything else on this page.** Read the model below
> before running a single command — getting the sequence wrong produces an
> environment that cannot deploy at all, and no command will fix it afterwards.

### Railway's model

**Services are project-level. Each environment holds an *instance* of a
service.** An environment created *before* the services exist receives no
instances — and then nothing can deploy into it. Every route fails identically:

```
railway service source connect      → ServiceInstance not found
railway redeploy                    → service doesn't exist in this environment
railway up                          → 404 Failed to upload
serviceInstanceDeploy (GraphQL)     → Service Instance not found
environmentTriggersDeploy (GraphQL) → ServiceInstance not found
serviceInstanceUpdate (GraphQL)     → returns true, creates nothing
```

The only cure is to duplicate an environment that already has instances.

**Branch tracking is a deployment trigger, not a service property.** There is
no `branch` field on a service or an instance. `railway add --branch X` creates
triggers in **every** environment at once, so a second environment on a
different branch must be repointed afterwards.

### The sequence that works

```bash
npm install -g @railway/cli
railway login                       # opens a browser
railway init --name mayan-cake-factory
```

`init` creates a `production` environment. Add the services **into it first**,
so the instances exist before any other environment is created:

```bash
railway environment link production
railway add --service backend  --repo <owner>/<repo> --branch main
railway add --service frontend --repo <owner>/<repo> --branch main
```

Then create `dev` by duplicating, which copies the instances:

```bash
railway environment new dev --duplicate production
```

Finally repoint `dev`'s triggers to the `dev` branch — the duplicate inherits
`main`. There is no CLI command; use the API:

```bash
railway api 'query { project(id: "<project-id>") { deploymentTriggers { edges {
  node { id branch environmentId serviceId } } } } }'

railway api 'mutation { deploymentTriggerUpdate(id: "<trigger-id>",
  input: { branch: "dev" }) { id branch } }'
```

> **A duplicated environment inherits the source environment's variables**,
> including `SUPABASE_URL` and the service-role key. Overwrite them immediately
> or the new environment talks to the wrong database — which nothing surfaces
> until someone reads the data. The isolation check below is what catches it.

## Variables

Set per service, per environment. Never committed.

**Backend** — the service-role key lives only here and never reaches a browser:

| Variable | dev | production |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `SECRET_KEY` | from `backend/.env` | from `backend/.env.production` |
| `SUPABASE_URL` | dev project | **prod project** |
| `SUPABASE_ANON_KEY` | dev | **prod** |
| `SUPABASE_SERVICE_ROLE_KEY` | dev | **prod** |
| `AI_MODE` | `mock` | `live` once verified |
| `LLM_API_KEY` / `IMAGE_API_KEY` | omit while mocked | required when live |
| `ALLOWED_ORIGINS` | the frontend's Railway URL | the frontend's Railway URL |
| `BACKEND_URL` / `FRONTEND_URL` | the Railway URLs | the Railway URLs |
| `RAILWAY_DOCKERFILE_PATH` | `backend/Dockerfile` | `backend/Dockerfile` |

**Frontend** — holds no secrets at all. It needs only its own identity and the
backend's public URL:

| Variable | Value |
|---|---|
| `APP_ENV` | `development` / `production` |
| `BACKEND_URL` | the backend service's public URL |
| `RAILWAY_DOCKERFILE_PATH` | `frontend/Dockerfile` |

Setting them:

```bash
railway variables --service backend --environment dev \
  --set "APP_ENV=development" --set "SUPABASE_URL=..."

railway variables --service backend --environment dev   # verify
```

> **The URLs are circular.** `ALLOWED_ORIGINS` needs the frontend's domain and
> `BACKEND_URL` needs the backend's, and neither domain exists until after the
> first deploy. Deploy first, generate the domains, then set the URLs and
> redeploy. The first deploy failing CORS is expected, not a fault.

## Domains

```bash
railway domain --service frontend --environment dev
railway domain --service backend  --environment dev
```

## Deploying

Pushing to the branch is the deploy. `dev` updates the `dev` environment, `main`
updates production.

```bash
git push origin dev                 # dev environment
gh pr create --base main --head dev # production, via a reviewed PR
```

Manual redeploy of the current commit:

```bash
railway redeploy --service backend --environment dev --yes
```

## Verifying — do this before saying it worked

**Two checks, and neither substitutes for the other.**

`/health` describes the **running image**. It says nothing about whether the
last deploy succeeded. A previous version of this project ran for days with a
green health check sitting on top of nine consecutive failed builds, serving an
image inherited from another environment.

```bash
# 1. did the last deploy actually succeed, and from the right branch?
railway deployment list --service backend --environment production
#    expect: SUCCESS  branch=main

# 2. is the thing that is running healthy?
curl -s https://backend-production-fabf8.up.railway.app/health | python -m json.tool
curl -s -o /dev/null -w "%{http_code}\n" https://frontend-production-d6f7.up.railway.app/healthz
```

A healthy backend returns:

```json
{"status": "ok", "database": "ok", "ai_mode": "mock", "missing_credentials": []}
```

### Isolation — the check worth repeating

Configuring two Supabase projects is not evidence that they *are* separate. Ask
both for the same record:

```bash
curl -s -o /dev/null -w "dev  %{http_code}\n" https://backend-dev-b0f4.up.railway.app/api/v1/orders/<order-number>
curl -s -o /dev/null -w "prod %{http_code}\n" https://backend-production-fabf8.up.railway.app/api/v1/orders/<order-number>
```

Expect **200 on dev, 404 on production**, with both returning identical seeded
catalogs. Every plausible failure here — a copied variable, a stale
`supabase link`, a duplicated environment that inherited its parent's
credentials — produces configuration that looks correct and a system that is
not. Only reading from both settles it.

`"database": "unreachable"` means the Supabase variables are wrong or the
project is paused. `missing_credentials` lists exactly what is absent — the
endpoint reports its own misconfiguration rather than failing on the first
customer request.

## Rolling back

```bash
railway deployment list --service backend --environment production
railway deployment redeploy <deployment-id>      # previous known-good build
```

Or revert the commit and push; the branch is the source of truth.

Database migrations do **not** roll back with a deployment. A migration that
must be undone needs a new migration that undoes it.

## Production checklist

- [ ] `AI_MODE=live` with real `LLM_API_KEY` and `IMAGE_API_KEY`
- [ ] `ALLOWED_ORIGINS` contains only the production frontend domain — no
      wildcard, no localhost. The backend refuses to start with `*` in
      production.
- [ ] `SUPABASE_URL` is the **production** project, not development.
      `scripts/validate_environment.sh` fails the build if it is not.
- [ ] Migrations pushed: `supabase link --project-ref <prod>` then
      `supabase db push`, then **re-link to dev**.
- [ ] Mayan's admin account created: a Supabase Auth user **plus** an
      `admin_profiles` row with `active = true`. The user alone returns 403.
- [ ] `test-admin@cake-factory.local` deleted from the development project.
- [ ] Fonts self-hosted, so no request reaches Google (see `security.md`).

## Cost

Four services on Railway plus two Supabase projects. Railway bills by usage,
and both Supabase projects are separate instances. For a bakery taking five
orders a day this is small, but it is not zero — check the plan before leaving
production running.
