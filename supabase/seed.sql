-- Local seed for `supabase db reset`.
--
-- The seed data itself lives in a migration so that the remote development
-- and production projects receive exactly the same rows via `db push`.
-- Including it here rather than copying it keeps a single source of truth;
-- every statement is idempotent, so running it twice is harmless.

\ir migrations/20260812174503_seed_data.sql
