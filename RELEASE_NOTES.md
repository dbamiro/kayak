# Kayak v1.0.0-rc1 — Release Notes

**Release candidate** for first production deployment and first real users. No new features after this tag — launch hygiene, docs, and deploy validation only.

**Tag:** `v1.0.0-rc1`  
**Date:** 2026-07-03

---

## What Kayak v1 is

Kayak is an **apartment incentive discovery engine** for the DMV (DC, Northern Virginia, Maryland). Renters compare sticker rent vs effective rent after move-in specials, see total savings and discount %, and run Deal Reports on verified inventory.

Production v1 ships **admin-verified inventory only** — no fabricated building specials in production.

---

## Features (v1)

### Search and specials

- Building search ranked by incentives and effective rent (`/search`, `/specials`)
- Verified move-in specials with effective rent, savings, and concession breakdown
- Demo data labeled in dev; hidden in production when `SHOW_DEMO_DATA=false`
- Savings calculator (`/incentives/calculate`)

### Deal Reports

- Building detail pages with Deal Report preview
- Full Deal Report for entitled users (Hunt Pass or Concierge)

### Auth and accounts

- Email/password registration and login (bcrypt + JWT access tokens + refresh tokens)
- Account page with entitlements
- Admin role via `ADMIN_EMAILS` or `users.is_admin`

### Monetization (Hunt Pass)

- Stripe Checkout for 30-day Hunt Pass
- Webhook-driven entitlement grants (idempotent)
- Mock checkout mode for local dev only (`MOCK_CHECKOUT_MODE=true`)
- Success page polls entitlements; grant is webhook-only, not redirect

### Admin and inventory

- Admin incentive review queue (`/admin/incentives`)
- **CSV bulk import** for verified DMV specials ([docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md))
- User submission flow → admin verify/reject
- Production DB bootstrap: schema + migrations + subscription plans only — **no demo seeds**

### Jobs and ops

- Scheduled jobs: entitlement expiry, pending incentive expiry, alerts
- Rate limiting and abuse protection (in-process; edge limits recommended at scale)
- Production scripts: `check_prod_env.sh`, `prod_migrate.sh`, `prod_verify_db.sh`, `prod_smoke.sh`, `verify_stripe.sh`

### Web and deploy

- Next.js 15 frontend (`web/`) with production Docker build
- Docker Compose production stack (`docker-compose.prod.yml`)
- VPS + Docker deployment guide ([docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md))

### Crawler (dev / future)

- Modular parser pipeline (Next.js `__NEXT_DATA__`, RentCafe HTML, floorplan cards)
- Crawler-derived incentives stay `pending_review` until admin verifies
- **Daily crawl disabled by default in production** (`ENABLE_DAILY_CRAWL=false`)

---

## Test and quality gates (rc1)

| Gate | Result |
|------|--------|
| pytest | 141 tests |
| `npm run build` (web) | Production build |
| `scripts/smoke.sh` | API health + search/incentives/plans/deal report |
| Production dry run | GO with fixes applied ([docs/DEPLOYMENT_READINESS_REPORT.md](docs/DEPLOYMENT_READINESS_REPORT.md)) |

---

## Known risks (v1)

| Risk | Mitigation |
|------|------------|
| **Empty search at launch** | Import verified CSV before announcing ([docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md)) |
| **Webhook delay after payment** | Success page polls; Hunt Pass grants only on Stripe webhook |
| **Single-instance rate limits** | Add edge rate limits at reverse proxy for multi-replica |
| **JWT in localStorage** | HTTPS only in production |
| **Crawler not production-ready** | Use admin CSV import for launch inventory |
| **User submissions unverified** | Public search shows admin-verified or CSV-imported incentives only |
| **Forward-only migrations** | Postgres snapshot before first production migrate |
| **Demo data in dev only** | Never run `bootstrap_db.sh` on prod; `prod_migrate.sh` blocks demo seed files |
| **Stripe test vs live mismatch** | Switch secret key, webhook secret, and price ID together |
| **Concierge fulfillment** | Manual ops placeholder — not automated |

---

## Upgrade / install

**New production install:** follow [LAUNCH.md](LAUNCH.md) and [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).

**Dev quick start:** see [README.md](README.md).

---

## Documentation index

| Doc | Purpose |
|-----|---------|
| [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) | Launch-day steps |
| [LAUNCH.md](LAUNCH.md) | Runbook + known risks |
| [PRE_TAG_CHECKLIST.md](PRE_TAG_CHECKLIST.md) | Before tagging releases |
| [TAG_INSTRUCTIONS.md](TAG_INSTRUCTIONS.md) | Commit, tag, push, rollback |
| [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md) | VPS + Docker deploy |
| [docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md) | First verified inventory |
| [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md) | Hunt Pass verification |
| [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md) | Inventory overview |
| [docs/DATABASE.md](docs/DATABASE.md) | Dev vs prod DB |

---

## Not in v1

- Automated concierge fulfillment
- Multi-region / multi-replica entitlements sync
- Production crawler as primary inventory source
- Mobile apps

---

## Contributors

Fill in before public release if applicable.
