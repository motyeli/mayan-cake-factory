#!/usr/bin/env bash
# Verifies the toolchain and the .env file before development or deployment.
# Prints only variable NAMES and whether they are set — never their values.
#
# Usage: bash scripts/validate_environment.sh [path/to/.env]
set -uo pipefail

ENV_FILE="${1:-backend/.env}"
fail=0

echo "== CLI tools =="
for tool in git python supabase gh railway; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '  ok      %-10s %s\n' "$tool" "$("$tool" --version 2>&1 | head -1)"
  else
    printf '  MISSING %-10s\n' "$tool"
    # railway is only needed at deployment time, so it does not fail the check.
    [ "$tool" = railway ] || fail=1
  fi
done

echo
echo "== Authentication =="
if gh auth status >/dev/null 2>&1; then echo "  ok      github authenticated"
else echo "  MISSING github  (run: gh auth login)"; fail=1; fi
if supabase projects list >/dev/null 2>&1; then echo "  ok      supabase authenticated"
else echo "  MISSING supabase (run: supabase login)"; fail=1; fi

echo
echo "== $ENV_FILE =="
if [ ! -f "$ENV_FILE" ]; then
  echo "  MISSING $ENV_FILE  (run: cp .env.example $ENV_FILE)"
  exit 1
fi

# Reads one variable. Strips the trailing " # comment" that .env.example
# carries, then trims whitespace. Every check below reads through this one
# helper, so the comment handling only has to be correct once.
get() {
  grep -E "^$1=" "$ENV_FILE" \
    | head -1 \
    | cut -d= -f2- \
    | tr -d '\r' \
    | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//'
}

check() {
  if [ -n "$(get "$1")" ]; then printf '  ok      %s\n' "$1"
  else printf '  EMPTY   %s%s\n' "$1" "${2:-}"; fail=1; fi
}

for key in APP_ENV SECRET_KEY FRONTEND_URL BACKEND_URL ALLOWED_ORIGINS \
           SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY \
           AI_MODE BAKERY_LATITUDE BAKERY_LONGITUDE DEFAULT_CURRENCY DEFAULT_TIMEZONE; do
  check "$key"
done

# Optional: admin tokens are verified against the Supabase Auth API, which
# works whether the project signs with HS256 or asymmetric keys.
if [ -n "$(get SUPABASE_JWT_SECRET)" ]; then
  echo "  ok      SUPABASE_JWT_SECRET"
else
  echo "  info    SUPABASE_JWT_SECRET unset — admin tokens verified via the Auth API"
fi

# Live AI mode is the only state that needs provider credentials.
if [ "$(get AI_MODE)" = "live" ]; then
  for key in LLM_API_KEY LLM_MODEL IMAGE_API_KEY IMAGE_MODEL; do
    check "$key" "  (required when AI_MODE=live)"
  done
else
  printf '  info    AI_MODE=%s — provider keys not required\n' "$(get AI_MODE)"
fi

if [ "$(get MAPS_PROVIDER)" = "mock" ]; then
  echo "  info    MAPS_PROVIDER=mock — Paris postal-code distances, no API key needed"
else
  check MAPS_API_KEY "  (required when MAPS_PROVIDER is not 'mock')"
fi

# Production must never point at a development Supabase project or allow
# wildcard origins.
if [ "$(get APP_ENV)" = "production" ]; then
  echo
  echo "== production guards =="
  case "$(get SUPABASE_URL)" in
    *ntngfmeucypgpjvdxcdo*) echo "  FAIL    SUPABASE_URL points at the DEVELOPMENT project"; fail=1 ;;
    *)                      echo "  ok      SUPABASE_URL is not the development project" ;;
  esac
  case "$(get ALLOWED_ORIGINS)" in
    *"*"*|*localhost*) echo "  FAIL    ALLOWED_ORIGINS contains a wildcard or localhost"; fail=1 ;;
    *)                 echo "  ok      ALLOWED_ORIGINS is restricted" ;;
  esac
fi

echo
if [ "$fail" -eq 0 ]; then echo "environment OK"; else echo "environment INCOMPLETE"; fi
exit "$fail"
