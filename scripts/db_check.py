#!/usr/bin/env python
"""Read-only database inspection through PostgREST.

Exists because this project develops against remote Supabase projects and the
machine has neither psql nor Docker. Uses the service-role key from the .env
file and never prints it.

    python scripts/db_check.py                 # seed summary
    python scripts/db_check.py cake_sizes      # dump a table
    python scripts/db_check.py --env backend/.env cake_flavors
"""

from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request

SEEDED_TABLES = [
    "settings", "cake_sizes", "cake_flavors", "fillings", "frostings",
    "design_styles", "decorations", "dietary_options",
    "recommended_combinations", "delivery_zones", "time_slots",
    "pricing_rules", "feasibility_rules",
]


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # .env.example keeps trailing "# comment" notes on some lines.
        env[key.strip()] = value.split(" #")[0].strip()
    return env


def _request(env: dict[str, str], path: str, extra_headers: dict[str, str] | None = None):
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    headers.update(extra_headers or {})
    req = urllib.request.Request(f"{env['SUPABASE_URL']}/rest/v1/{path}", headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=20)
    except urllib.error.HTTPError as exc:
        # Show the API's own error, but never echo the request headers.
        print(f"  HTTP {exc.code}: {exc.read().decode()[:200]}", file=sys.stderr)
        raise SystemExit(1) from None


def query(env: dict[str, str], path: str) -> list[dict]:
    with _request(env, path) as response:
        return json.loads(response.read())


def count(env: dict[str, str], table: str) -> int:
    """Row count via the Content-Range header — works for any table without
    having to know which columns it has."""
    with _request(env, f"{table}?select=*&limit=1", {"Prefer": "count=exact"}) as response:
        return int(response.headers.get("Content-Range", "*/0").split("/")[-1])


def main() -> int:
    args = sys.argv[1:]
    env_path = "backend/.env"
    if args and args[0] == "--env":
        env_path, args = args[1], args[2:]
    env = load_env(env_path)

    print(f"project: {env['SUPABASE_URL']}\n")

    if args:
        rows = query(env, f"{args[0]}?select=*&limit=200")
        print(json.dumps(rows, indent=2, default=str))
        return 0

    for table in SEEDED_TABLES:
        print(f"  {count(env, table):>3}  {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
