# Kayak v1 — launch day runbook

Release candidate freeze for first production deployment and first real users. **No new features** — follow this sequence exactly.

**Launch-day checklist (printable):** [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)  
**Dry-run audit report:** [docs/DEPLOYMENT_READINESS_REPORT.md](docs/DEPLOYMENT_READINESS_REPORT.md)  
**Release notes:** [RELEASE_NOTES.md](RELEASE_NOTES.md) · **Pre-tag checklist:** [PRE_TAG_CHECKLIST.md](PRE_TAG_CHECKLIST.md)

**Prerequisites:** VPS with Docker, domain DNS pointed, Stripe account (test mode first, then live), admin email chosen.

---

## Release candidate audit (pre-launch)

Run from repo root before launch day:

```bash
# 1. Tests
./.venv/bin/python -m pytest -q

# 2. Frontend production build
cd web && npm run build && cd ..

# 3. Local smoke (API running + dev DB bootstrapped)
./scripts/smoke.sh

# 4. Production env dry-run (on server after cp .env.production.example .env)
./scripts/check_prod_env.sh
```

Expected: **141 tests pass**, Next.js build succeeds, smoke checks `/health`, `/search`, `/incentives`, `/plans`, deal report preview.

---

## Launch-day sequence (copy/paste)

Replace `app.example.com`, `api.example.com`, and secrets with your values.

### Phase 0 — Server prep (one time)

```bash
sudo apt update && sudo apt install -y git docker.io docker-compose-v2 postgresql-client curl jq
sudo usermod -aG docker "$USER"
# log out and back in

git clone https://github.com/YOUR_ORG/Kayak.git
cd Kayak
git checkout v1.0.0   # or your release tag

# Host Python for migrate/verify scripts (uses python-dotenv from requirements.txt)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Phase 1 — Environment

```bash
cp .env.production.example .env
chmod 600 .env
openssl rand -hex 32   # → JWT_SECRET
openssl rand -hex 16   # → POSTGRES_PASSWORD (use same in DATABASE_URL / MIGRATE_DATABASE_URL)
```

Edit `.env` — required variables:

| Variable | Production value |
|----------|------------------|
| `APP_ENV` | `production` |
| `JWT_SECRET` | 32+ char hex |
| `MOCK_AUTH_MODE` | `false` |
| `MOCK_CHECKOUT_MODE` | `false` |
| `SHOW_DEMO_DATA` | `false` |
| `POSTGRES_*` / `DATABASE_URL` / `MIGRATE_DATABASE_URL` | See `.env.production.example` |
| `CORS_ORIGINS` | `https://app.example.com` |
| `APP_BASE_URL` | `https://app.example.com` |
| `API_BASE_URL` | `https://api.example.com` |
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.example.com` |
| `ADMIN_EMAILS` | Your ops email |
| `STRIPE_SECRET_KEY` | `sk_test_...` first, then `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | From Stripe Dashboard or CLI |
| `STRIPE_PRICE_HUNT_PASS_30` | Stripe Price ID |

Validate:

```bash
./scripts/check_prod_env.sh
```

### Phase 2 — Database (no demo data)

```bash
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml ps postgres   # wait for healthy

ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
```

Confirm: required tables exist, Hunt Pass plans seeded, **zero demo incentives**.

**Never run** `./scripts/bootstrap_db.sh` or apply `seed.sql` / `seed_incentives.sql` in production.

### Phase 3 — Deploy services

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs
```

Configure TLS reverse proxy (Caddy/nginx) → `localhost:3000` (web), `localhost:8000` (api). See [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md).

### Phase 4 — Stripe webhooks

1. Stripe Dashboard → Webhooks → `https://api.example.com/webhooks/stripe`
2. Events: `checkout.session.completed`, `checkout.session.expired`, `invoice.payment_succeeded`, `customer.subscription.deleted`, `customer.subscription.updated`, `charge.refunded`, `payment_intent.payment_failed`
3. Copy signing secret → `STRIPE_WEBHOOK_SECRET` → restart API

```bash
docker compose -f docker-compose.prod.yml up -d api
./scripts/verify_stripe.sh
```

Complete one test-mode Hunt Pass purchase: [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md)

### Phase 5 — Real incentive inventory

Import verified DMV specials (not demo CSV):

```bash
# Register admin or use existing JWT
TOKEN="$ADMIN_JWT" ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
TOKEN="$ADMIN_JWT" ./scripts/import_incentives_csv.sh verified_specials.csv
```

Template: `fixtures/incentives_import_template.csv` → copy to `verified_specials.csv`. Workflow: [docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md). Do **not** import `fixtures/incentives_import_example.csv` (`[EXAMPLE ONLY]` rows are rejected).

Verify:

```bash
curl -s "https://api.example.com/incentives?include_demo=false" | jq '.[].building_name'
curl -s "https://api.example.com/search?include_demo=false" | jq '.[].name'
```

Web: `/search`, `/specials`, building detail pages show verified specials.

### Phase 6 — Post-deploy smoke

```bash
export API_URL=https://api.example.com
export WEB_URL=https://app.example.com
./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

Manual UI checklist:

| Page | URL | Expect |
|------|-----|--------|
| Search | `/search` | Buildings with verified specials (or empty state) |
| Specials | `/specials` | Ranked incentives, no dev/seed messages |
| Calculator | `/calculator` | Effective rent calculation |
| Submit special | `/submit-special` | Form submits → pending review |
| Pricing | `/pricing` | Hunt Pass checkout → Stripe |
| Account | `/account` | Plan status after purchase |
| Building | `/buildings/{id}` | Deal Report preview; full when entitled |
| Admin import | `/admin/incentives` | CSV validate + import (admin only) |

### Phase 7 — Go live

- [ ] Switch Stripe to **live** keys + live webhook secret + live price ID
- [ ] `./scripts/check_prod_env.sh` passes
- [ ] Repeat one real Hunt Pass purchase
- [ ] Monitor `GET /health` and `GET /health/ready`
- [ ] Confirm jobs container or cron running ([docs/SCHEDULED_JOBS.md](docs/SCHEDULED_JOBS.md))

---

## Rollback

```bash
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml up -d --build
# Restore .env backup if env changed
# Postgres: restore snapshot if migration failed
```

---

## Known risks (v1)

| Risk | Mitigation |
|------|------------|
| **Empty search at launch** | Import verified CSV before announcing; empty state is expected until inventory exists |
| **Webhook delay after payment** | Success page polls entitlements; Hunt Pass grants only on webhook, not redirect |
| **Single-instance rate limits** | Abuse limits are in-process; add edge rate limits at proxy for multi-replica ([docs/ABUSE_PROTECTION.md](docs/ABUSE_PROTECTION.md)) |
| **JWT in localStorage** | Standard SPA tradeoff; use HTTPS only |
| **Crawler not production-ready** | `ENABLE_DAILY_CRAWL=false` by default; use admin CSV import for inventory |
| **User submissions unverified** | All public search requires admin-verified or CSV-imported incentives |
| **Forward-only migrations** | Back up Postgres before deploy; no automatic down migrations |
| **Demo data in dev only** | `SHOW_DEMO_DATA=false`; never run `bootstrap_db.sh` on prod; `prod_migrate.sh` blocks demo seed files |
| **Stripe test vs live mismatch** | Switch secret key, webhook secret, and price ID together |
| **Concierge fulfillment** | Placeholder — manual ops, not automated |

---

## Documentation index

| Doc | Purpose |
|-----|---------|
| [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) | Pre-launch checklist |
| [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md) | Full deploy guide (VPS + Docker) |
| [docs/DATABASE.md](docs/DATABASE.md) | Dev vs prod DB commands |
| [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md) | Hunt Pass payment verification |
| [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md) | CSV import + inventory |
| [docs/SCHEDULED_JOBS.md](docs/SCHEDULED_JOBS.md) | Entitlement expiry cron |
| [docs/ABUSE_PROTECTION.md](docs/ABUSE_PROTECTION.md) | Rate limits + admin auth |

---

## Scripts reference

| Script | When |
|--------|------|
| `scripts/check_prod_env.sh` | Before deploy |
| `scripts/prod_migrate.sh` | Every deploy |
| `scripts/prod_verify_db.sh` | After migrate |
| `scripts/prod_smoke.sh` | After TLS + services up |
| `scripts/verify_stripe.sh` | After Stripe config |
| `scripts/import_incentives_csv.sh` | Bulk verified inventory |
| `scripts/stripe_test_checkout.sh` | Pre-live Stripe test |
| `scripts/run_scheduled_jobs.sh` | Cron alternative to jobs container |
| `scripts/bootstrap_db.sh` | **Dev only** — includes demo seeds |

---

## Support contacts (fill in)

| Role | Contact |
|------|---------|
| On-call / deploy | |
| Stripe account | |
| Domain / DNS | |
