#!/usr/bin/env bash
# Verifies the toolchain and the .env file before development or deployment.
# Prints only variable NAMES and whether they are set — never their values.
set -uo pipefail

ENV_FILE="${1:-backend/.env}"
fail=0

echo "== CLI tools =="
for tool in git python supabase gh railway; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '  ok      %-10s %s\n' "$tool" "$("$tool" --version 2>&1 | head -1)"
  else
    printf '  MISSING %-10s\n' "$tool"
    [ "$tool" = railway ] || fail=1   # railway is only needed for deployment
  fi
done

echo
echo "== Authentication =="
gh auth status >/dev/null 2>&1 && echo "  ok      github authenticated" || { echo "  MISSING github  (run: gh auth login)"; fail=1; }
supabase projects list >/dev/null 2>&1 && echo "  ok      supabase authenticated" || { echo "  MISSING supabase (run: supabase login)"; fail=1; }

echo
echo "== $ENV_FILE =="
if [ ! -f "$ENV_FILE" ]; then
  echo "  MISSING $ENV_FILE  (run: cp .env.example $ENV_FILE)"
  exit 1
fi

# Required in every environment.
required=(APP_ENV SECRET_KEY FRONTEND_URL BACKEND_URL ALLOWED_ORIGINS
          SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET
          AI_MODE BAKERY_LATITUDE BAKERY_LONGITUDE DEFAULT_CURRENCY DEFAULT_TIMEZONE)

get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r'; }

for key in "${required[@]}"; do
  if [ -n "$(get "$key")" ]; then printf '  ok      %s\n' "$key"
  else printf '  EMPTY   %s\n' "$key"; fail=1; fi
done

# Conditionally required: live AI mode needs real keys.
if [ "$(get AI_MODE)" = "live" ]; then
  for key in LLM_API_KEY LLM_MODEL IMAGE_API_KEY IMAGE_MODEL; do
    if [ -n "$(get "$key")" ]; then printf '  ok      %s\n' "$key"
    else printf '  EMPTY   %s  (required when AI_MODE=live)\n' "$key"; fail=1; fi
  done
else
  echo "  info    AI_MODE=$(get AI_MODE) — provider keys not required"
fi

if [ "$(get MAPS_PROVIDER)" != "mock" ] && [ -z "$(get MAPS_API_KEY)" ]; then
  echo "  EMPTY   MAPS_API_KEY  (required when MAPS_PROVIDER is not 'mock')"; fail=1
fi

echo
if [ "$fail" -eq 0 ]; then echo "environment OK"; else echo "environment INCOMPLETE"; fi
exit "$fail"
