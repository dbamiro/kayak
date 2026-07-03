#!/usr/bin/env bash
# Start a Stripe test-mode Hunt Pass checkout (API must be running with Stripe configured).
#
# Prerequisites:
#   MOCK_CHECKOUT_MODE=false
#   STRIPE_SECRET_KEY=sk_test_...
#   STRIPE_PRICE_HUNT_PASS_30=price_...
#   ./scripts/dev-api.sh
#   ./scripts/stripe_webhook_listen.sh  (separate terminal; set STRIPE_WEBHOOK_SECRET)
#
# Usage:
#   ./scripts/stripe_test_checkout.sh
#   EMAIL=you@example.com ./scripts/stripe_test_checkout.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

API_URL="${API_URL:-http://127.0.0.1:8000}"
API_URL="${API_URL%/}"
EMAIL="${EMAIL:-stripe-test-$(date +%s)@example.com}"
PASSWORD="${PASSWORD:-testpassword123}"

pass() { echo "OK: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "==> Stripe test-mode Hunt Pass checkout"
echo "    API_URL=$API_URL"
echo "    EMAIL=$EMAIL"
echo ""

[[ "${MOCK_CHECKOUT_MODE:-true}" == "false" ]] || fail "Set MOCK_CHECKOUT_MODE=false in .env"
[[ -n "${STRIPE_SECRET_KEY:-}" ]] || fail "STRIPE_SECRET_KEY not set"
[[ -n "${STRIPE_PRICE_HUNT_PASS_30:-}" ]] || fail "STRIPE_PRICE_HUNT_PASS_30 not set"
pass "Stripe env present (test checkout mode)"

REG="$(curl -s -w "\n%{http_code}" -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"name\":\"Stripe Test\"}")"
REG_BODY="$(echo "$REG" | head -n -1)"
REG_CODE="$(echo "$REG" | tail -n 1)"
[[ "$REG_CODE" == "201" ]] || fail "POST /auth/register returned $REG_CODE: $REG_BODY"
pass "Registered $EMAIL"

TOKEN="$(echo "$REG_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

SESSION="$(curl -s -w "\n%{http_code}" -X POST "$API_URL/checkout/session" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_code":"hunt_pass_30"}')"
SESSION_BODY="$(echo "$SESSION" | head -n -1)"
SESSION_CODE="$(echo "$SESSION" | tail -n 1)"
[[ "$SESSION_CODE" == "200" ]] || fail "POST /checkout/session returned $SESSION_CODE: $SESSION_BODY"

MOCK_MODE="$(echo "$SESSION_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mock_mode', True))")"
[[ "$MOCK_MODE" == "False" || "$MOCK_MODE" == "false" ]] || fail "checkout returned mock_mode=true — configure Stripe keys"

CHECKOUT_URL="$(echo "$SESSION_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['checkout_url'])")"
pass "Checkout session created"

echo ""
echo "Next steps:"
echo "  1. Open checkout URL in a browser:"
echo "     $CHECKOUT_URL"
echo ""
echo "  2. Pay with test card 4242 4242 4242 4242 (any future expiry, any CVC)."
echo ""
echo "  3. Ensure stripe listen is forwarding webhooks (./scripts/stripe_webhook_listen.sh)."
echo ""
echo "  4. After payment, verify entitlement:"
echo "     curl -s $API_URL/me/entitlements -H \"Authorization: Bearer $TOKEN\" | python3 -m json.tool"
echo ""
echo "  5. Confirm Deal Report access is full (replace BUILDING_ID):"
echo "     curl -s $API_URL/deal-reports/BUILDING_ID -H \"Authorization: Bearer $TOKEN\" | python3 -c \"import sys,json; print(json.load(sys.stdin)['access'])\""
echo ""
echo "Full runbook: docs/STRIPE_RUNBOOK.md"
