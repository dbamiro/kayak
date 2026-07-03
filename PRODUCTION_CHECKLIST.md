# Kayak DMV — production checklist

Use this before pointing real users or paid traffic at the stack.

**Launch day sequence:** [LAUNCH.md](LAUNCH.md) (full runbook) · **[LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)** (command-driven checklist)

## Required environment variables

| Variable | Production value |
|----------|------------------|
| `APP_ENV` | `production` |
| `JWT_SECRET` | 32+ chars (`openssl rand -hex 32`) |
| `DATABASE_URL` | Managed Postgres connection string |
| `MOCK_AUTH_MODE` | `false` |
| `MOCK_CHECKOUT_MODE` | `false` (when Stripe live) |
| `SHOW_DEMO_DATA` | `false` |
| `CORS_ORIGINS` | Your deployed web origin(s), e.g. `https://app.example.com` |
| `APP_BASE_URL` | Frontend URL (Stripe success/cancel redirects) |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-reachable API URL |
| `STRIPE_SECRET_KEY` | Live secret key |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret |
| `STRIPE_PRICE_HUNT_PASS_30` | Stripe Price ID |
| `ADMIN_EMAILS` | Comma-separated admin emails for `/admin/*` |

The API **fails startup** when `APP_ENV=production` and JWT, auth, demo, or checkout settings are unsafe.

## Database

1. Fresh production DB (no demo buildings/incentives):

   ```bash
   ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
   # or: ALLOW_PROD_BOOTSTRAP=yes ./scripts/bootstrap_prod_db.sh
   ```

   Applies `schema.sql`, migrations, and `seed_plans.sql` only. **Never** runs `seed.sql` / `seed_incentives.sql` in production.

2. Verify schema after bootstrap or every migrate:

   ```bash
   ./scripts/prod_verify_db.sh
   ```

   Confirms required v1 tables, Hunt Pass plans, and zero demo incentives.

3. Subsequent deploys: `./scripts/prod_migrate.sh` then `./scripts/prod_verify_db.sh`.

4. Local dev DB: `./scripts/bootstrap_db.sh` (includes demo seeds).

5. Configure backups and retention.

Full reference: [docs/DATABASE.md](docs/DATABASE.md). Deploy steps: [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md).

## Deploy verification commands

```bash
# From repo root — API running with production .env
./scripts/check_prod_env.sh
API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

See also [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md) and [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md).

## Auth & security

- Register/login via `/auth/register` and `/auth/login` (JWT Bearer in `Authorization` header).
- Tokens stored in **localStorage** on the web client (not HttpOnly cookies).
- Legacy `POST /users` is **disabled** in production — use auth routes.
- `/admin/*` requires `AdminUser` (`users.is_admin` or `ADMIN_EMAILS`).

## Checkout (Hunt Pass)

Full runbook: [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md)

**Before launch — complete in Stripe test mode:**

- [ ] Product + Price created; `STRIPE_PRICE_HUNT_PASS_30=price_...`
- [ ] `STRIPE_SECRET_KEY=sk_test_...` and `MOCK_CHECKOUT_MODE=false`
- [ ] Webhook endpoint → `POST /webhooks/stripe` (local: `./scripts/stripe_webhook_listen.sh`)
- [ ] `STRIPE_WEBHOOK_SECRET=whsec_...` matches active CLI or Dashboard endpoint
- [ ] Success URL: `{APP_BASE_URL}/billing/success?session_id=...` (set automatically by API)
- [ ] Cancel URL: `{APP_BASE_URL}/billing/cancel`
- [ ] `./scripts/verify_stripe.sh` passes
- [ ] `./scripts/stripe_test_checkout.sh` → pay with `4242 4242 4242 4242`
- [ ] Hunt Pass on `/account`; Deal Report `access: full` for paid user
- [ ] Cancel checkout → no entitlement; free user stays preview-only
- [ ] Webhook replay does not double-grant (`stripe events resend`)

**Entitlement rule:** granted only on verified `checkout.session.completed` with `payment_status=paid` — not on success page load alone.

**Production switch:** live keys + live webhook + `./scripts/check_prod_env.sh` + one live test purchase.

## Incentive data trust

- User submissions → `pending_review` (hidden from search until admin verifies at `/admin/incentives`).
- Production: set `SHOW_DEMO_DATA=false`; demo specials hidden unless explicitly requested.
- **Real inventory:** bulk import via CSV — [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md)
  ```bash
  TOKEN=$ADMIN_JWT ./scripts/import_incentives_csv.sh --dry-run verified_specials.csv
  TOKEN=$ADMIN_JWT ./scripts/import_incentives_csv.sh verified_specials.csv
  curl -s "$API_URL/incentives?include_demo=false" | jq '.[].building_name'
  ```
- Template: `fixtures/incentives_import_template.csv` → `verified_specials.csv` ([docs/DMV_INCENTIVE_IMPORT.md](docs/DMV_INCENTIVE_IMPORT.md)). Do not import `fixtures/incentives_import_example.csv`.

## Scheduled jobs

Full reference: [docs/SCHEDULED_JOBS.md](docs/SCHEDULED_JOBS.md)

Daily Hunt Pass expiry (**required**):

```bash
PYTHONPATH=. python -m jobs.expire_entitlements
# or: ./scripts/run_scheduled_jobs.sh
```

Optional pending incentive cleanup:

```bash
./scripts/run_scheduled_jobs.sh --expire-pending
```

Optional crawl (only when `ENABLE_DAILY_CRAWL=true` and permitted sources configured):

```bash
./scripts/run_scheduled_jobs.sh --crawl
# or combined: ./scripts/run_scheduled_jobs.sh --all
```

Docker Compose: `docker compose -f docker-compose.prod.yml --profile jobs up -d jobs`

## Abuse protection

- Rate limits on `/auth/register`, `/auth/login`, `/incentives/submit`, `/admin/*` (see `.env.production.example`).
- Tune via `RATE_LIMIT_*` env vars; set to `0` to disable a limit.
- Full details: [docs/ABUSE_PROTECTION.md](docs/ABUSE_PROTECTION.md).

## Observability

- Uptime on `GET /health` (liveness) and `GET /health/ready` (readiness + DB).
- Ship API logs to your platform.

## Legal

- Confirm scraping respects each site’s terms and robots rules; do not bypass logins or paywalls.
