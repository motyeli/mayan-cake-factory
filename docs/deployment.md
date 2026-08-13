# Deployment

Two Railway environments, each with two services, deploying from two Git
branches.

| Railway environment | Git branch | Services | Supabase project |
|---|---|---|---|
| `development` | `dev` | `backend`, `frontend` | `cake-factory-dev` (`ntngfmeucypgpjvdxcdo`) |
| `production` | `main` | `backend`, `frontend` | `cake-factory-prod` (`zdbzwjqhfzjwpctmrclg`) |

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

```bash
npm install -g @railway/cli
railway login                       # opens a browser
railway init --name mayan-cake-factory --workspace "<your workspace>"
railway environment new development
```

Add the services. `--branch` is what ties an environment to a Git branch:

```bash
railway environment link development
railway add --service backend  --repo <owner>/<repo> --branch dev
railway add --service frontend --repo <owner>/<repo> --branch dev

railway environment link production
railway add --service backend  --repo <owner>/<repo> --branch main
railway add --service frontend --repo <owner>/<repo> --branch main
```

## Variables

Set per service, per environment. Never committed.

**Backend** — the service-role key lives only here and never reaches a browser:

| Variable | development | production |
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
railway variables --service backend --environment development \
  --set "APP_ENV=development" --set "SUPABASE_URL=..."

railway variables --service backend --environment development   # verify
```

> **The URLs are circular.** `ALLOWED_ORIGINS` needs the frontend's domain and
> `BACKEND_URL` needs the backend's, and neither domain exists until after the
> first deploy. Deploy first, generate the domains, then set the URLs and
> redeploy. The first deploy failing CORS is expected, not a fault.

## Domains

```bash
railway domain --service frontend --environment development
railway domain --service backend  --environment development
```

## Deploying

Pushing to the branch is the deploy. `dev` updates development, `main` updates
production.

```bash
git push origin dev                 # development
gh pr create --base main --head dev # production, via a reviewed PR
```

Manual redeploy of the current commit:

```bash
railway redeploy --service backend --environment development --yes
```

## Verifying — do this before saying it worked

```bash
railway service status
railway service logs --service backend --environment development

curl -s https://<backend-domain>/health | python -m json.tool
curl -s -o /dev/null -w "%{http_code}\n" https://<frontend-domain>/healthz
```

A healthy backend returns:

```json
{"status": "ok", "database": "ok", "ai_mode": "mock", "missing_credentials": []}
```

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
