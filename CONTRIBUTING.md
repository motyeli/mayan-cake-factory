# Contributing

## Branches

| Branch | Meaning | Deploys to |
|---|---|---|
| `main` | production | Railway **Production** environment |
| `dev` | shared development | Railway **Development** environment |
| `feat/*`, `fix/*`, `chore/*` | short-lived work, branched from `dev` | nothing |

Rules:

- **Never commit directly to `main`.**
- Prefer not to commit directly to `dev` — open a pull request.
- Production releases are `dev` → `main` pull requests, reviewed, then tagged.

## Workflow

```bash
git switch dev && git pull
git switch -c feat/pricing-engine

# ... implement, then ...
pytest backend/tests/unit && ruff check .

git push -u origin feat/pricing-engine
gh pr create --base dev --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
```

Release to production:

```bash
gh pr create --base main --head dev --title "Release: <summary>"
gh pr merge --merge                       # after review
git switch main && git pull
git tag -a v0.1.0 -m "MVP" && git push origin v0.1.0
gh release create v0.1.0 --generate-notes
```

## Commit style

`<type>: <imperative summary>` — `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
One logical unit of work per commit.

## Database changes

Schema changes live **only** in version-controlled migrations:

```bash
supabase migration new add_something
# edit supabase/migrations/<timestamp>_add_something.sql
supabase db push                      # dev project
```

Never apply undocumented manual changes to the production database.

## Definition of done

- [ ] `pytest backend/tests/unit` green
- [ ] `ruff check .` and `ruff format --check .` clean
- [ ] New business rules have tests
- [ ] No secret values in code, logs, templates or docs
- [ ] Docs updated when behaviour or setup changed
