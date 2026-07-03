#!/usr/bin/env bash
# Post-deploy smoke test for production/staging.
#
# Usage:
#   API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
#
# Loads CORS_ORIGINS from .env when present (for preflight check).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

API_URL="${API_URL:-http://127.0.0.1:8000}"
WEB_URL="${WEB_URL:-${APP_BASE_URL:-}}"
API_URL="${API_URL%/}"
WEB_URL="${WEB_URL%/}"

pass() { echo "OK: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }

echo "==> Kayak production smoke test"
echo "    API_URL=$API_URL"
[[ -n "$WEB_URL" ]] && echo "    WEB_URL=$WEB_URL"

curl -sf "$API_URL/health" | grep -q '"status"' || fail "GET /health"
pass "GET /health → ok"

curl -sf "$API_URL/health/ready" | grep -q '"ready"' || fail "GET /health/ready (database unavailable?)"
pass "GET /health/ready → ready"

PLANS="$(curl -sf "$API_URL/plans")"
echo "$PLANS" | grep -q 'hunt_pass_30' || fail "GET /plans missing hunt_pass_30"
pass "GET /plans includes hunt_pass_30"

# CORS preflight (browser login/register)
if [[ -n "${CORS_ORIGINS:-}" ]]; then
  ORIGIN="$(echo "$CORS_ORIGINS" | cut -d',' -f1 | xargs)"
  CORS_CODE="$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS "$API_URL/auth/login" \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: content-type")"
  if [[ "$CORS_CODE" == "200" || "$CORS_CODE" == "204" ]]; then
    pass "CORS preflight for Origin=$ORIGIN → $CORS_CODE"
  else
    fail "CORS preflight failed (HTTP $CORS_CODE) — check CORS_ORIGINS includes $ORIGIN"
  fi
else
  warn "CORS_ORIGINS not set — skipping preflight check"
fi

EMAIL="smoke-$(date +%s)@example.com"
REG_CODE="$(curl -s -o /tmp/kayak_smoke_reg.json -w "%{http_code}" -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"testpassword123\",\"name\":\"Smoke\"}")"
[[ "$REG_CODE" == "201" ]] || fail "POST /auth/register returned $REG_CODE ($(cat /tmp/kayak_smoke_reg.json))"
pass "POST /auth/register → 201"

if [[ -n "$WEB_URL" ]]; then
  WEB_CODE="$(curl -s -o /dev/null -w "%{http_code}" "$WEB_URL/")"
  if [[ "$WEB_CODE" == "200" || "$WEB_CODE" == "307" || "$WEB_CODE" == "308" ]]; then
    pass "GET $WEB_URL/ → $WEB_CODE"
  else
    fail "GET $WEB_URL/ returned $WEB_CODE"
  fi
fi

echo ""
echo "Smoke test passed."
echo "Next steps:"
echo "  ./scripts/verify_stripe.sh"
echo "  Complete a test Hunt Pass checkout — docs/STRIPE_RUNBOOK.md"
