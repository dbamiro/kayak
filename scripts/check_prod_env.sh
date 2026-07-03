#!/usr/bin/env bash
# Validate production environment before deploy. Does not print secret values.
#
# Usage:
#   ./scripts/check_prod_env.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "OK: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }

if [[ ! -f .env ]]; then
  fail ".env missing — copy .env.production.example to .env and fill in values"
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

REQUIRED=(
  APP_ENV
  JWT_SECRET
  DATABASE_URL
  CORS_ORIGINS
  APP_BASE_URL
  API_BASE_URL
  ADMIN_EMAILS
  STRIPE_SECRET_KEY
  STRIPE_WEBHOOK_SECRET
  STRIPE_PRICE_HUNT_PASS_30
  NEXT_PUBLIC_API_BASE_URL
)

for var in "${REQUIRED[@]}"; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    fail "$var is not set"
  fi
  pass "$var is set"
done

[[ "${APP_ENV}" == "production" ]] || fail "APP_ENV must be production (got: ${APP_ENV})"
pass "APP_ENV=production"

[[ "${MOCK_AUTH_MODE:-false}" == "false" ]] || fail "MOCK_AUTH_MODE must be false"
pass "MOCK_AUTH_MODE=false"

[[ "${MOCK_CHECKOUT_MODE:-false}" == "false" ]] || fail "MOCK_CHECKOUT_MODE must be false"
pass "MOCK_CHECKOUT_MODE=false"

[[ "${SHOW_DEMO_DATA:-false}" == "false" ]] || fail "SHOW_DEMO_DATA must be false"
pass "SHOW_DEMO_DATA=false"

# CORS should include the web origin
web_origin="${APP_BASE_URL%/}"
IFS=',' read -ra cors_list <<< "${CORS_ORIGINS}"
cors_ok=false
for origin in "${cors_list[@]}"; do
  if [[ "${origin// /}" == "$web_origin" ]]; then
    cors_ok=true
    break
  fi
done
if [[ "$cors_ok" == "true" ]]; then
  pass "CORS_ORIGINS includes APP_BASE_URL ($web_origin)"
else
  warn "CORS_ORIGINS may not include APP_BASE_URL ($web_origin) — browser auth/checkout may fail"
fi

if [[ "${NEXT_PUBLIC_API_BASE_URL}" == http://* && "${APP_ENV}" == "production" ]]; then
  warn "NEXT_PUBLIC_API_BASE_URL uses http:// — use https:// in production"
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
[[ -n "$PYTHON" ]] || fail "python3 not found for validate_production"

export PYTHONPATH="$ROOT"
"$PYTHON" -c "
from app.config import get_settings
get_settings.cache_clear()
get_settings().validate_production()
print('OK: validate_production() passed')
"

echo ""
echo "Environment check passed."
echo "Next:"
echo "  docker compose -f docker-compose.prod.yml up -d postgres"
echo "  ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap   # first deploy only"
echo "  ./scripts/prod_verify_db.sh"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
