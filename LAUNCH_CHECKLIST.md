# Kayak v1 — launch-day checklist

Practical, command-driven checklist for first production deployment. Replace `app.example.com`, `api.example.com`, and placeholders with your values.

**Related:** [LAUNCH.md](LAUNCH.md) (full runbook) · [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md) · [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)

---

## Variables (set once per session)

```bash
export APP_URL=https://app.example.com
export API_URL=https://api.example.com
export ADMIN_EMAIL=ops@your-company.com
export ADMIN_PASSWORD='choose-a-strong-password'
cd /path/to/Kayak
```

---

## 1. Before deploy

- [ ] DNS: `app.example.com` and `api.example.com` point to the server
- [ ] Release tag checked out: `git checkout v1.0.0 && git log -1 --oneline`
- [ ] Host venv for launch scripts (migrate, verify, check env — needs `python-dotenv`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

- [ ] `.env` created from template and filled (never commit):

```bash
cp .env.production.example .env
chmod 600 .env
openssl rand -hex 32   # paste into JWT_SECRET=
openssl rand -hex 16   # paste into POSTGRES_PASSWORD= (same in DATABASE_URL / MIGRATE_DATABASE_URL)
```

- [ ] Required `.env` values set: `APP_ENV=production`, `MOCK_AUTH_MODE=false`, `MOCK_CHECKOUT_MODE=false`, `SHOW_DEMO_DATA=false`, Stripe keys, `ADMIN_EMAILS=$ADMIN_EMAIL`
- [ ] Env validation passes:

```bash
./scripts/check_prod_env.sh
```

- [ ] RC audit (optional, from dev machine):

```bash
./.venv/bin/python -m pytest -q
cd web && npm run build && cd ..
```

- [ ] Postgres backup plan documented (snapshot before first migrate)
- [ ] Stripe Dashboard: test-mode product + price + webhook endpoint URL ready

**Stop if:** `check_prod_env.sh` fails or secrets are missing.

---

## 2. Deploy

- [ ] Start Postgres only first (migrate before full traffic):

```bash
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml ps postgres   # status: healthy
```

- [ ] Build and start API + web:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

- [ ] TLS reverse proxy configured (Caddy/nginx → `localhost:3000` web, `localhost:8000` api)
- [ ] Optional: start jobs container for daily cron:

```bash
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs
```

- [ ] Quick liveness (local or via proxy):

```bash
curl -sf "$API_URL/health"
curl -sf "$API_URL/health/ready"
```

**Stop if:** API container exits — check `docker compose -f docker-compose.prod.yml logs api`.

---

## 3. Database migration

**First deploy (empty database only):**

```bash
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
```

**Every deploy (including first, if bootstrap already ran):**

```bash
./scripts/prod_migrate.sh
./scripts/prod_verify_db.sh
```

- [ ] `prod_verify_db.sh` reports: required tables present, Hunt Pass plans, **zero demo incentives**
- [ ] **Never run** `./scripts/bootstrap_db.sh`, `seed.sql`, or `seed_incentives.sql` in production

Manual SQL sanity check:

```bash
psql "$MIGRATE_DATABASE_URL" -c "SELECT COUNT(*) AS demo_incentives FROM incentives WHERE is_demo = true;"
psql "$MIGRATE_DATABASE_URL" -c "SELECT code FROM plans WHERE is_active ORDER BY code;"
```

Expect: `demo_incentives = 0`, plans include `hunt_pass_30`.

**Stop if:** migration fails or demo incentives > 0 after bootstrap.

---

## 4. Stripe webhook verification

- [ ] Stripe webhook endpoint: `$API_URL/webhooks/stripe`
- [ ] Events subscribed: `checkout.session.completed`, `checkout.session.expired`, `invoice.payment_succeeded`, `customer.subscription.deleted`, `customer.subscription.updated`, `charge.refunded`, `payment_intent.payment_failed`
- [ ] `STRIPE_WEBHOOK_SECRET` in `.env` matches Dashboard signing secret
- [ ] Restart API after secret change:

```bash
docker compose -f docker-compose.prod.yml up -d api
./scripts/verify_stripe.sh
```

- [ ] Test-mode checkout (before live keys):

```bash
./scripts/stripe_test_checkout.sh
# Pay with 4242 4242 4242 4242 — see docs/STRIPE_RUNBOOK.md
```

- [ ] Confirm webhook processed:

```bash
psql "$MIGRATE_DATABASE_URL" -c \
  "SELECT stripe_event_id, event_type, status FROM stripe_webhook_events ORDER BY created_at DESC LIMIT 5;"
```

**Stop if:** `verify_stripe.sh` fails or test payment does not create entitlement within ~60s.

Full runbook: [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md)

---

## 5. Admin user creation

Admins are users whose email is in `ADMIN_EMAILS` or `users.is_admin = true`.

- [ ] `ADMIN_EMAILS` includes `$ADMIN_EMAIL` in `.env` (lowercase)
- [ ] Restart API if you changed `.env` after first start
- [ ] Register admin account:

```bash
curl -s -X POST "$API_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\",\"name\":\"Launch Admin\"}" | jq .

export ADMIN_TOKEN="$(curl -s -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r .access_token)"

curl -s "$API_URL/auth/me" -H "Authorization: Bearer $ADMIN_TOKEN" | jq .is_admin
```

Expect: `"is_admin": true`

**Alternative (SQL)** if account already exists:

```bash
psql "$MIGRATE_DATABASE_URL" -c \
  "UPDATE users SET is_admin = true WHERE lower(email) = lower('$ADMIN_EMAIL');"
```

- [ ] Admin route responds:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "$API_URL/admin/incentives?status=pending_review" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Expect: `200` (not `403`).

**Stop if:** admin JWT returns 403 on `/admin/*`.

---

## 6. Import first verified incentives CSV

Use real leasing-office data — **not** `fixtures/incentives_import_example.csv` (example rows are rejected).

- [ ] CSV prepared from blank template (see [docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md)):

```bash
cp fixtures/incentives_import_template.csv verified_specials.csv
# fill 30–75 verified rows; run quality checklist in DMV_INCENTIVE_IMPORT.md
```

- [ ] Quality checklist complete: source URLs open, values match site, no `example.com`, no `[EXAMPLE ONLY]`
- [ ] Dry-run validation:

```bash
TOKEN="$ADMIN_TOKEN" ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
```

- [ ] Import:

```bash
TOKEN="$ADMIN_TOKEN" ./scripts/import_incentives_csv.sh verified_specials.csv
```

- [ ] Verify public API:

```bash
curl -s "$API_URL/incentives?include_demo=false" | jq '.[].building_name'
curl -s "$API_URL/search?include_demo=false" | jq '.[].name'
```

- [ ] All imported rows: `is_demo=false`, `status=verified`

```bash
psql "$MIGRATE_DATABASE_URL" -c \
  "SELECT building_id, status, is_demo, capture_method FROM incentives ORDER BY created_at DESC LIMIT 10;"
```

**Stop if:** import errors > 0 or search/specials empty when CSV had valid rows.

Guide: [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md)

---

## 7. Run scheduled jobs once manually

Required before relying on cron/jobs container. Entitlement expiry must work for Hunt Pass.

```bash
# Option A — host script (needs Python + deps on server)
./scripts/run_scheduled_jobs.sh --expire-pending

# Option B — inside API container (recommended on Docker deploy)
docker compose -f docker-compose.prod.yml exec api python -m jobs.run_scheduled --expire-pending
```

- [ ] Exit code 0; logs show `job=expire_entitlements status=ok`
- [ ] Do **not** run `--crawl` unless `ENABLE_DAILY_CRAWL=true` and sources are configured

```bash
docker compose -f docker-compose.prod.yml exec api python -m jobs.run_scheduled
docker compose -f docker-compose.prod.yml exec api python -m jobs.run_scheduled --expire-pending
```

Guide: [docs/SCHEDULED_JOBS.md](docs/SCHEDULED_JOBS.md)

---

## 8. Post-deploy smoke tests

```bash
export API_URL=https://api.example.com
export WEB_URL=https://app.example.com
./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

**Note:** `prod_smoke.sh` checks `GET $WEB_URL/` — start the web container (`docker compose … up web`) or local `npm run start` first. For API-only smoke during staging, set `WEB_URL` to a running web origin or expect the homepage check to fail.

- [ ] `GET /health` → ok
- [ ] `GET /health/ready` → ready (DB connected)
- [ ] `GET /plans` includes `hunt_pass_30`
- [ ] CORS preflight passes (when `CORS_ORIGINS` set in `.env`)
- [ ] `POST /auth/register` succeeds
- [ ] Web homepage responds (`GET $WEB_URL/` → 200/307)

**Stop if:** any smoke step fails.

---

## 9. Manual browser QA

Open `$APP_URL` in a private/incognito window.

| # | Page | Path | Pass criteria |
|---|------|------|---------------|
| 1 | Home | `/` | Loads, nav works |
| 2 | Search | `/search` | Shows imported buildings or clean empty state |
| 3 | Specials | `/specials` | Verified specials listed; no dev/seed messages |
| 4 | Calculator | `/calculator` | Effective rent calculates |
| 5 | Building detail | `/buildings/{id}` | Deal Report preview visible |
| 6 | Submit special | `/submit-special` | Form submits → pending review |
| 7 | Register / Login | `/register`, `/login` | Auth works; redirect OK |
| 8 | Pricing | `/pricing` | Hunt Pass → Stripe Checkout (test card) |
| 9 | Billing success | `/billing/success` | Hunt Pass appears within ~30s after payment |
| 10 | Account | `/account` | Shows Hunt Pass + expiry after purchase |
| 11 | Deal Report (paid) | building page | Full report unlocked after Hunt Pass |
| 12 | Admin import | `/admin/incentives` | CSV validate + import (admin login) |

- [ ] No console CORS errors on login or checkout
- [ ] No `MOCK_CHECKOUT_MODE` or localhost hints visible to users

---

## 10. Rollback steps

If launch fails after deploy:

```bash
# 1. Revert code
git checkout <previous-release-tag>
docker compose -f docker-compose.prod.yml up -d --build

# 2. Restore .env if changed
cp .env.backup .env
docker compose -f docker-compose.prod.yml up -d api web

# 3. Database — forward-only migrations; restore from snapshot if needed
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U kayak kayak_prod > kayak_prod_pre_rollback.sql   # if still up
# Restore: psql ... < backup.sql (follow your Postgres restore procedure)

# 4. Stripe — revert price IDs in .env if pricing changed; webhook can stay
```

- [ ] Communicate downtime if rolling back after users registered
- [ ] Keep `stripe_webhook_events` for payment audit

---

## 11. Go / no-go criteria

### GO — all must be true

| # | Criterion | Verified by |
|---|-----------|-------------|
| 1 | `./scripts/check_prod_env.sh` passes | §1 |
| 2 | `./scripts/prod_verify_db.sh` passes; zero demo incentives | §3 |
| 3 | `GET /health/ready` returns ready on production URL | §2, §8 |
| 4 | Stripe test checkout grants Hunt Pass via webhook | §4 |
| 5 | Admin can access `/admin/incentives` | §5 |
| 6 | At least one verified incentive visible on `/search` or `/specials` | §6, §9 |
| 7 | `./scripts/prod_smoke.sh` passes | §8 |
| 8 | Manual browser QA table complete (no blockers) | §9 |
| 9 | Scheduled jobs run once without error | §7 |
| 10 | TLS on both app and API domains | §2 |
| 11 | `SHOW_DEMO_DATA=false`; no demo seed scripts run | §3 |

### NO-GO — any one triggers hold

- API fails `validate_production()` or will not start
- Database migration failed or demo data present in production
- Stripe webhook not receiving events / entitlements not granted after paid checkout
- Admin cannot access `/admin/*`
- CORS blocks login or checkout from browser
- Critical page broken in manual QA (auth, search, pricing, account)
- Rollback plan not confirmed (no DB backup before first migrate)

### After GO

- [ ] Switch Stripe to **live** keys + live webhook secret + live price (when ready for paid traffic)
- [ ] Re-run `./scripts/check_prod_env.sh` and one live Hunt Pass purchase
- [ ] Enable uptime monitoring on `/health` and `/health/ready`
- [ ] Confirm jobs container or cron is scheduled daily

---

## Quick reference (full sequence)

```bash
./scripts/check_prod_env.sh
docker compose -f docker-compose.prod.yml up -d postgres
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs
./scripts/verify_stripe.sh
# register admin, import CSV, run jobs — see sections 5–7
API_URL=$API_URL WEB_URL=$APP_URL ./scripts/prod_smoke.sh
```
