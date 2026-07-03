# Stripe Hunt Pass — test & production verification runbook

Complete this runbook in **Stripe test mode** before switching to live keys.

**Core rule:** Hunt Pass access is granted **only** when Stripe sends a verified `checkout.session.completed` webhook with `payment_status=paid`. Landing on `/billing/success` does **not** grant access — the success page polls `/me/entitlements` until the webhook is processed.

---

## Quick local test (3 terminals)

| Terminal | Command |
|----------|---------|
| 1 — API | `./scripts/dev-api.sh` |
| 2 — Web | `./scripts/dev-web.sh` |
| 3 — Webhooks | `./scripts/stripe_webhook_listen.sh` → copy `whsec_...` to `.env` as `STRIPE_WEBHOOK_SECRET`, restart API |

Then:

```bash
./scripts/verify_stripe.sh
./scripts/stripe_test_checkout.sh
# Open printed checkout URL → pay with 4242 4242 4242 4242
# Check /account — Hunt Pass should appear within a few seconds
```

---

## Required environment variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `STRIPE_SECRET_KEY` | API + Checkout session create | `sk_test_...` / `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Verify webhook signatures | `whsec_...` from Dashboard or CLI |
| `STRIPE_PRICE_HUNT_PASS_30` | Hunt Pass Price ID | `price_...` |
| `MOCK_CHECKOUT_MODE` | Must be `false` for Stripe | `false` |
| `APP_BASE_URL` | Stripe redirect base (web origin) | `http://localhost:3000` |
| `API_BASE_URL` | API URL (optional links) | `http://localhost:8000` |
| `NEXT_PUBLIC_API_BASE_URL` | Browser → API (web build) | `http://localhost:8000` |

Optional plan prices: `STRIPE_PRICE_PREMIUM_PLUS_30`, `STRIPE_PRICE_CONCIERGE_ONE_TIME`.

Copy from [`.env.example`](../.env.example) and fill Stripe fields. Quick check:

```bash
./scripts/verify_stripe.sh
```

---

## Stripe Dashboard setup (test mode)

Open [Stripe Dashboard → Test mode](https://dashboard.stripe.com/test/dashboard).

### 1. Product

| Field | Value |
|-------|-------|
| **Location** | Product catalog → **Add product** |
| **Name** | `Premium Hunt Pass (30 days)` |
| **Description** | Optional — e.g. “Full Deal Reports for 30 days” |

### 2. Price ID → `STRIPE_PRICE_HUNT_PASS_30`

| Field | Value |
|-------|-------|
| **Amount** | `$19.00` (matches `plans.price_cents = 1900`) |
| **Billing period** | Recurring / monthly **or** one-time — Kayak uses Checkout `mode=subscription` for Hunt Pass |
| **Copy** | Price ID (`price_...`) → `.env` as `STRIPE_PRICE_HUNT_PASS_30` |

Kayak reads this price when creating Checkout sessions (`app/services/stripe_checkout_service.py`).

### 3. Secret key → `STRIPE_SECRET_KEY`

| Field | Value |
|-------|-------|
| **Location** | Developers → **API keys** |
| **Copy** | **Secret key** (`sk_test_...`) → `.env` |

Never commit or log this value.

### 4. Webhook endpoint

| Environment | Endpoint URL |
|-------------|--------------|
| **Local (Stripe CLI)** | Forwarded to `http://127.0.0.1:8000/webhooks/stripe` via `./scripts/stripe_webhook_listen.sh` |
| **Deployed** | `https://api.<your-domain>/webhooks/stripe` |

**Subscribe to events:**

- `checkout.session.completed`
- `checkout.session.expired`
- `invoice.payment_succeeded`
- `customer.subscription.deleted`
- `customer.subscription.updated`
- `charge.refunded`
- `payment_intent.payment_failed`

Route handler: `POST /webhooks/stripe` (`app/routers/monetization_api.py`).

### 5. Webhook secret → `STRIPE_WEBHOOK_SECRET`

| Source | When to use |
|--------|-------------|
| **Stripe CLI** (`stripe listen`) | Local development — secret printed in Terminal 3 |
| **Dashboard → Webhooks → endpoint → Signing secret** | Deployed/staging API |

Copy `whsec_...` → `.env` → **restart API**.

The CLI secret differs from Dashboard secrets — use the one matching your active forwarder.

### 6. Success URL

Kayak sets this when creating Checkout (you do **not** configure it in Dashboard):

```
{APP_BASE_URL}/billing/success?session_id={CHECKOUT_SESSION_ID}
```

| `APP_BASE_URL` | Resulting success URL |
|----------------|----------------------|
| `http://localhost:3000` | `http://localhost:3000/billing/success?session_id=cs_...` |
| `https://app.example.com` | `https://app.example.com/billing/success?session_id=cs_...` |

The success page polls entitlements every 2s until Hunt Pass appears (`web/src/app/billing/success/page.tsx`).

### 7. Cancel URL

```
{APP_BASE_URL}/billing/cancel
```

User sees “Checkout cancelled” — no charge, no entitlement (`web/src/app/billing/cancel/page.tsx`).

Override per request via `POST /checkout/session` body: `success_url`, `cancel_url` (optional).

---

## Local webhook testing (Stripe CLI)

**Install:** [Stripe CLI](https://stripe.com/docs/stripe-cli)

```bash
stripe login   # one-time
```

**Forward webhooks:**

```bash
chmod +x scripts/stripe_webhook_listen.sh
./scripts/stripe_webhook_listen.sh
```

Output includes `whsec_...` — set as `STRIPE_WEBHOOK_SECRET`, restart API.

Required `.env` for real checkout:

```bash
MOCK_CHECKOUT_MODE=false
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PRICE_HUNT_PASS_30=price_...
STRIPE_WEBHOOK_SECRET=whsec_...   # from stripe listen
APP_BASE_URL=http://localhost:3000
```

---

## End-to-end test-mode purchase

### Option A — helper script

```bash
./scripts/stripe_test_checkout.sh
```

Opens instructions with checkout URL and verification curls.

### Option B — manual curls

```bash
export API_URL=http://127.0.0.1:8000

curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"stripe-test@example.com","password":"testpassword123","name":"Stripe Test"}' | jq .

export TOKEN="<access_token>"

curl -s -X POST "$API_URL/checkout/session" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan_code":"hunt_pass_30"}' | jq .
```

Expect: `"mock_mode": false` and `checkout_url` starting with `https://checkout.stripe.com/`.

### Complete payment

Open `checkout_url`. Test card:

| Field | Value |
|-------|-------|
| Card | `4242 4242 4242 4242` |
| Expiry | Any future date |
| CVC | Any 3 digits |

Redirects:

- Success → `/billing/success?session_id=...`
- Cancel → `/billing/cancel`

### Confirm webhook fired

In the `stripe listen` terminal: `checkout.session.completed` with `payment_status: paid`.

### Confirm entitlement (30-day Hunt Pass)

```bash
curl -s "$API_URL/me/entitlements" -H "Authorization: Bearer $TOKEN" | jq .
# active_plan_codes: ["hunt_pass_30"]
# feature_flags.can_view_full_deal_reports: true

curl -s "$API_URL/deal-reports/<building_uuid>" -H "Authorization: Bearer $TOKEN" | jq .access
# "full"
```

**Web UI:** `/account` shows “Premium Hunt Pass” with expiry date.

SQL verification:

```sql
SELECT plan_code, status, starts_at, expires_at,
       (expires_at - starts_at) AS duration
FROM customer_entitlements
ORDER BY created_at DESC LIMIT 3;

SELECT stripe_event_id, event_type, status FROM stripe_webhook_events ORDER BY created_at DESC LIMIT 5;

SELECT status FROM checkout_sessions ORDER BY created_at DESC LIMIT 3;
```

Expect:

- `customer_entitlements.status = active`, duration ≈ **30 days**
- `stripe_webhook_events.status = processed`
- `checkout_sessions.status = completed`

---

## Negative cases (must NOT grant access)

| Scenario | How to test | Expected |
|----------|-------------|----------|
| **Cancel checkout** | Click Back on Stripe Checkout | `/billing/cancel`; no entitlement |
| **Success page only** | Complete payment but stop `stripe listen` | Success page shows “Confirming payment…”; no Hunt Pass until webhook arrives |
| **Session expires** | Abandon checkout | `checkout.session.expired` → session `expired`; no grant |
| **Unpaid session** | Webhook with `payment_status != paid` | Kayak skips grant (`stripe_webhook_service`) |
| **Failed payment** | Card `4000 0000 0000 0002` | No paid `checkout.session.completed`; no grant |
| **Mock checkout in prod** | `APP_ENV=production` + `POST /checkout/mock-complete` | HTTP 403 |

After cancel/decline:

```bash
curl -s "$API_URL/me/entitlements" -H "Authorization: Bearer $TOKEN" | jq .active_plan_codes
# [] — free user, Deal Report preview only
```

---

## Webhook idempotency

Kayak deduplicates at three levels:

1. **Event ID** — `stripe_webhook_events.stripe_event_id` unique; HTTP replays return `{"received":"true","duplicate":"true"}`
2. **Payment intent** — same `payment_intent` on `checkout.session.completed` skips a second grant
3. **Checkout session** — if `checkout_sessions.status = completed`, grant is skipped

Verify CLI replay:

```bash
stripe events resend evt_...
```

Second delivery must not create a duplicate entitlement row.

Automated tests: `tests/test_stripe_webhook.py`

---

## Free vs Hunt Pass access

| User | `/me/entitlements` | Deal Report `access` | Account page |
|------|-------------------|----------------------|--------------|
| Anonymous | — | `preview` | — |
| Registered free | `active_plan_codes: []` | `preview` | “Free tier” |
| Hunt Pass (paid) | `hunt_pass_30` | `full` | “Premium Hunt Pass” + expiry |

Preview locks: `full_fee_breakdown`, `rent_history`, `negotiation_script`, etc.

---

## Switch to production (live mode)

- [ ] Replace `sk_test_` → `sk_live_`
- [ ] Create **live** Product/Price; update `STRIPE_PRICE_HUNT_PASS_30`
- [ ] Register **live** webhook at `https://api.<your-domain>/webhooks/stripe`
- [ ] Set live `STRIPE_WEBHOOK_SECRET` from Dashboard (not CLI)
- [ ] Set `APP_ENV=production`, `MOCK_CHECKOUT_MODE=false`, full prod env (see `.env.production.example`)
- [ ] `./scripts/check_prod_env.sh`
- [ ] Repeat end-to-end test with a real card or internal price
- [ ] Confirm `POST /checkout/mock-complete` returns **403**

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `503 stripe_webhook_not_configured` | `STRIPE_WEBHOOK_SECRET` set; API restarted |
| `400 invalid_signature` | Webhook secret matches CLI or Dashboard endpoint |
| Checkout returns `mock_mode: true` | `STRIPE_SECRET_KEY` set; `MOCK_CHECKOUT_MODE=false` |
| Checkout 500 `missing_stripe_price` | `STRIPE_PRICE_HUNT_PASS_30` matches Dashboard price ID |
| Payment ok, no entitlement | `stripe listen` running; secret in `.env`; check `stripe_webhook_events` |
| Success page stuck on “Confirming payment…” | Webhook not received — check CLI; wait or fix secret |
| Account still “Free tier” | `GET /me/entitlements`; verify webhook processed |
| Deal Report still preview | Entitlement missing or expired; check `expires_at` |
| CORS error on checkout | `CORS_ORIGINS` includes `APP_BASE_URL` |

---

## Related scripts

```bash
./scripts/verify_stripe.sh           # env validation
./scripts/stripe_webhook_listen.sh   # local webhook forwarding
./scripts/stripe_test_checkout.sh    # create test checkout session
./scripts/prod_smoke.sh              # post-deploy API smoke
```

See also [PRODUCTION_DEPLOY.md](./PRODUCTION_DEPLOY.md) and [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md).
