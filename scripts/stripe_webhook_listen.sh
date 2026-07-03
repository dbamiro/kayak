#!/usr/bin/env bash
# Forward Stripe webhooks to local Kayak API (test mode).
#
# Prerequisites:
#   stripe login          # one-time Stripe CLI auth
#   API running on :8000  # ./scripts/dev-api.sh
#
# Usage:
#   ./scripts/stripe_webhook_listen.sh
#
# Copy the whsec_... secret printed by `stripe listen` into .env as STRIPE_WEBHOOK_SECRET,
# then restart the API.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://127.0.0.1:8000}"
FORWARD_URL="${API_URL}/webhooks/stripe"

if ! command -v stripe >/dev/null 2>&1; then
  echo "ERROR: Stripe CLI not found." >&2
  echo "Install: https://stripe.com/docs/stripe-cli" >&2
  exit 1
fi

echo "==> Forwarding Stripe events to $FORWARD_URL"
echo "    Set STRIPE_WEBHOOK_SECRET in .env to the whsec_... value shown below."
echo "    Required .env for checkout test:"
echo "      MOCK_CHECKOUT_MODE=false"
echo "      STRIPE_SECRET_KEY=sk_test_..."
echo "      STRIPE_PRICE_HUNT_PASS_30=price_..."
echo ""
echo "    Full runbook: docs/STRIPE_RUNBOOK.md"
echo ""

exec stripe listen --forward-to "$FORWARD_URL" \
  --events checkout.session.completed,checkout.session.expired,invoice.payment_succeeded,customer.subscription.deleted,customer.subscription.updated,charge.refunded,payment_intent.payment_failed
