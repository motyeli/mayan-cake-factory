# Credentials

What the system needs, where each belongs, and what breaks without it.

**Never paste a key into a chat window, a commit, an Obsidian note or a
screenshot.** `.env`, `.env.production` and `.supabase-credentials` are
gitignored and CI fails the build if a credential-shaped string is committed.

## Already configured

| Credential | Where | Status |
|---|---|---|
| Supabase dev — URL, anon key, service-role key | `backend/.env`, Railway development | set |
| Supabase prod — URL, anon key, service-role key | `backend/.env.production`, Railway production | set |
| `SECRET_KEY` (one per environment) | both | generated |
| OpenAI API key | `backend/.env` | set, dev only |

## Needed before going live

**OpenAI key in production.** Production runs `AI_MODE=mock` today. Going live
means setting `LLM_API_KEY` and `IMAGE_API_KEY` on the production backend and
switching `AI_MODE=live`:

```bash
railway variables --service backend --environment production \
  --set "AI_MODE=live" --set "LLM_API_KEY=..." --set "IMAGE_API_KEY=..."
```

The mock is a genuine implementation, so nothing is broken until then — the
assistant simply parses with rules instead of a model, and designs render as
SVG rather than photographs.

**Mayan's admin account.** Two steps, and the second is the one that gets
forgotten: a Supabase Auth user in the **production** project, *and* an
`admin_profiles` row with `active = true` and a matching `auth_user_id`. The
Auth user alone authenticates and then gets 403.

## Optional

**Maps API key.** Without it, delivery zones use a Paris postal-code centroid
table and straight-line distance. That is genuinely accurate enough for zone
classification inside Paris; a real routing key would only refine edge cases at
the zone boundaries.

## Must be removed before production

`test-admin@cake-factory.local` — a development-only administrator with a known
password, in the development project only. Delete it before production carries
real orders. It is listed in the production checklist in
[deployment.md](deployment.md).

## If a key leaks

1. Rotate it at the provider first — Supabase dashboard, OpenAI dashboard.
2. Update Railway variables and redeploy.
3. Only then worry about git history. A rotated key in an old commit is
   harmless; an un-rotated key scrubbed from history is still live.
