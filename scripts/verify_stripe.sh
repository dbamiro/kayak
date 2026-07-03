#!/usr/bin/env bash
# Verify Stripe env configuration (does not charge cards).
#
# Usage:
#   ./scripts/verify_stripe.sh
#   API_URL=... TOKEN=... ./scripts/verify_stripe.sh  # also test checkout session create

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

API_URL="${API_URL:-http://127.0.0.1:8000}"

pass() { echo "OK: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }
warn() { echo "WARN: $*"; }

echo "==> Stripe configuration check"

[[ -n "${STRIPE_SECRET_KEY:-}" ]] || fail "STRIPE_SECRET_KEY not set"
pass "STRIPE_SECRET_KEY present"

[[ -n "${STRIPE_WEBHOOK_SECRET:-}" ]] || fail "STRIPE_WEBHOOK_SECRET not set"
pass "STRIPE_WEBHOOK_SECRET present"

[[ -n "${STRIPE_PRICE_HUNT_PASS_30:-}" ]] || fail "STRIPE_PRICE_HUNT_PASS_30 not set"
pass "STRIPE_PRICE_HUNT_PASS_30 present"

[[ -n "${APP_BASE_URL:-}" ]] || fail "APP_BASE_URL not set (Stripe success/cancel redirects)"
pass "APP_BASE_URL=${APP_BASE_URL}"

[[ -n "${API_BASE_URL:-}" ]] || warn "API_BASE_URL not set"
[[ -n "${API_BASE_URL:-}" ]] && pass "API_BASE_URL=${API_BASE_URL}"

[[ -n "${NEXT_PUBLIC_API_BASE_URL:-}" ]] || warn "NEXT_PUBLIC_API_BASE_URL not set (web checkout calls)"
[[ -n "${NEXT_PUBLIC_API_BASE_URL:-}" ]] && pass "NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}"

if [[ "${MOCK_CHECKOUT_MODE:-true}" == "true" ]]; then
  warn "MOCK_CHECKOUT_MODE=true — set false for real Stripe checkout"
else
  pass "MOCK_CHECKOUT_MODE=false"
fi

if [[ "${STRIPE_SECRET_KEY}" == sk_test_* ]]; then
  pass "Stripe test mode key (sk_test_)"
elif [[ "${STRIPE_SECRET_KEY}" == sk_live_* ]]; then
  warn "Live Stripe key — ensure webhook and prices are live too"
else
  warn "Unrecognized STRIPE_SECRET_KEY prefix"
fi

if [[ "${STRIPE_WEBHOOK_SECRET}" == whsec_* ]]; then
  pass "Webhook secret format whsec_*"
fi

# Optional: verify API can create checkout session
if [[ -n "${TOKEN:-}" ]]; then
  RESP="$(curl -s -X POST "$API_URL/checkout/session" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"plan_code":"hunt_pass_30"}')"
  echo "$RESP" | grep -q 'checkout_url' || fail "checkout session: $RESP"
  if echo "$RESP" | grep -q '"mock_mode":true'; then
    warn "Checkout returned mock_mode=true — Stripe may not be active"
  else
    pass "POST /checkout/session returns Stripe checkout_url"
  fi
fi

echo ""
echo "Stripe config OK."
echo "Next:"
echo "  ./scripts/stripe_webhook_listen.sh   # local webhooks (Terminal 3)"
echo "  ./scripts/stripe_test_checkout.sh    # test-mode Hunt Pass checkout"
echo "  docs/STRIPE_RUNBOOK.md               # full verification runbook"
