# Production deploy

**Launch checklist:** [LAUNCH_CHECKLIST.md](../LAUNCH_CHECKLIST.md)  
**Launch runbook:** [LAUNCH.md](../LAUNCH.md)  
**Full guide:** [PRODUCTION_DEPLOY.md](./PRODUCTION_DEPLOY.md) — VPS + Docker Compose (recommended).

## Quick start

```bash
cp .env.production.example .env          # fill secrets — never commit
./scripts/check_prod_env.sh
docker compose -f docker-compose.prod.yml up -d postgres
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs   # optional
API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/check_prod_env.sh` | Validate `.env` before deploy |
| `scripts/prod_migrate.sh` | Apply SQL migrations |
| `scripts/prod_verify_db.sh` | Verify tables and no demo incentives |
| `scripts/prod_smoke.sh` | Post-deploy health, CORS, auth checks |
| `scripts/verify_stripe.sh` | Stripe env and checkout config |
| `scripts/run_scheduled_jobs.sh` | Cron-friendly scheduled jobs |

See also [DATABASE.md](./DATABASE.md), [STRIPE_RUNBOOK.md](./STRIPE_RUNBOOK.md), [VERIFIED_INCENTIVES.md](./VERIFIED_INCENTIVES.md).
