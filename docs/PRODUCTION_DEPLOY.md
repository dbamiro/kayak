# Kayak v1 — production deployment guide

Deploy Kayak **API + web + Postgres** to production. This guide uses one recommended path end-to-end so a real person can follow it without guessing.

## Recommended path: VPS + Docker Compose

The repo ships production Dockerfiles and `docker-compose.prod.yml`. Run everything on a single **Ubuntu 22.04+ VPS** (DigitalOcean, Hetzner, AWS EC2, etc.) with Docker Compose. You get Postgres, API, web, and optional scheduled jobs in one place.

**Why this path:** all build/start commands, health checks, and networking are already defined in the repo. No platform-specific config files required.

**Time estimate:** ~30–45 minutes for a first deploy (excluding DNS propagation).

---

## Before you start

| Item | Notes |
|------|-------|
| Domain | Two hostnames recommended: `app.example.com` (web), `api.example.com` (API) |
| Stripe account | Test mode first; switch to live when ready ([STRIPE_RUNBOOK.md](./STRIPE_RUNBOOK.md)) |
| Secrets | Copy `.env.production.example` → `.env` on the server — **never commit `.env`** |

---

## Architecture

```
                    ┌─────────────┐
   Browser ────────►│ Caddy/nginx │  TLS (443)
                    └───┬────┬────┘
                        │    │
              / (web)   │    │  api.example.com
                        ▼    ▼
                   ┌─────┐ ┌─────┐
                   │ web │ │ api │  :8000  FastAPI
                   │:3000│ └─────┘
                   └─────┘     │
                                 │ DATABASE_URL
                                 ▼
                           ┌──────────┐
                           │ Postgres │
                           └──────────┘

   Jobs container / cron ──► expire entitlements (+ optional crawl)
   Stripe ───────────────► POST /webhooks/stripe
```

---

## Server setup (one time)

On a fresh Ubuntu VPS:

```bash
sudo apt update && sudo apt install -y git docker.io docker-compose-v2 postgresql-client curl
sudo usermod -aG docker "$USER"
# Log out and back in so the docker group applies
```

Clone the repo:

```bash
git clone https://github.com/YOUR_ORG/Kayak.git
cd Kayak
```

Create host venv for migrate/verify scripts (`python-dotenv` required):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create production environment file:

```bash
cp .env.production.example .env
chmod 600 .env
openssl rand -hex 32   # paste into JWT_SECRET=
openssl rand -hex 16   # paste into POSTGRES_PASSWORD= (use same value in DATABASE_URL / MIGRATE_DATABASE_URL)
```

Edit `.env` — replace every `REPLACE_WITH_*` and `your-app.example.com` placeholder with real values (see [§4 Environment variables](#4-environment-variables)).

Validate before continuing:

```bash
./scripts/check_prod_env.sh
```

---

## 1. Services needed

| Service | How it runs | Internal port | Purpose |
|---------|-------------|---------------|---------|
| **Postgres** | `postgres:16-alpine` in compose | 5432 | Primary database |
| **API** | Root `Dockerfile` → `uvicorn` | 8000 | FastAPI backend |
| **Web** | `web/Dockerfile` → `next start` | 3000 | Next.js frontend |
| **Jobs** (optional) | Same API image, different command | — | Daily entitlement expiry |

All services are defined in [`docker-compose.prod.yml`](../docker-compose.prod.yml).

---

## 2. API — build and start

### Production (Docker Compose — recommended)

```bash
# Build and start API (and dependencies)
docker compose -f docker-compose.prod.yml up -d --build api
```

**What the Dockerfile does:**

```dockerfile
# Root Dockerfile — summary
pip install -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Start Postgres first, run migrations, then start full stack:**

```bash
docker compose -f docker-compose.prod.yml up -d postgres
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap   # first deploy only
docker compose -f docker-compose.prod.yml up -d --build
```

**Restart API after env changes:**

```bash
docker compose -f docker-compose.prod.yml up -d api
```

### Manual reference (local debugging only)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export PYTHONPATH="$(pwd)" APP_ENV=production
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API **refuses to start** when `APP_ENV=production` and JWT, Stripe, mock modes, or demo settings are unsafe (`app/config.py` → `validate_production()`).

---

## 3. Web — build and start

The web app bakes `NEXT_PUBLIC_*` variables in at **build time**. Set them in `.env` before building.

### Production (Docker Compose — recommended)

```bash
docker compose -f docker-compose.prod.yml up -d --build web
```

**What `web/Dockerfile` does:**

```dockerfile
# web/Dockerfile — summary
npm ci && npm run build    # uses package-lock.json; NEXT_PUBLIC_API_BASE_URL at build time
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
```

**Rebuild web after changing `NEXT_PUBLIC_API_BASE_URL`:**

```bash
docker compose -f docker-compose.prod.yml build --no-cache web
docker compose -f docker-compose.prod.yml up -d web
```

### Manual reference (local debugging only)

```bash
cd web
export NEXT_PUBLIC_API_BASE_URL=https://api.example.com
npm install && npm run build
npm run start -- -H 0.0.0.0 -p 3000
```

---

## 4. Environment variables

**Template:** [`.env.production.example`](../.env.production.example) — copy to `.env`, fill in values, never commit.

### Required

| Variable | Example | Used by |
|----------|---------|---------|
| `APP_ENV` | `production` | API — enables startup validation |
| `JWT_SECRET` | 64-char hex (`openssl rand -hex 32`) | API — auth tokens (32+ chars) |
| `POSTGRES_USER` | `kayak` | Postgres container |
| `POSTGRES_PASSWORD` | strong password | Postgres container |
| `POSTGRES_DB` | `kayak_prod` | Postgres container |
| `DATABASE_URL` | `postgresql://kayak:PASS@postgres:5432/kayak_prod` | API, jobs (Docker hostname `postgres`) |
| `MIGRATE_DATABASE_URL` | `postgresql://kayak:PASS@127.0.0.1:5432/kayak_prod` | Host-side migrate scripts |
| `MOCK_AUTH_MODE` | `false` | API |
| `MOCK_CHECKOUT_MODE` | `false` | API |
| `SHOW_DEMO_DATA` | `false` | API — hides demo incentives |
| `CORS_ORIGINS` | `https://app.example.com` | API — must include web origin |
| `APP_BASE_URL` | `https://app.example.com` | API — Stripe redirect URLs |
| `API_BASE_URL` | `https://api.example.com` | API — internal links |
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.example.com` | **Web build** — browser API URL |
| `NEXT_PUBLIC_APP_NAME` | `Kayak DMV` | Web build |
| `ADMIN_EMAILS` | `ops@example.com` | API — `/admin/*` access |
| `STRIPE_SECRET_KEY` | `sk_test_...` or `sk_live_...` | API |
| `STRIPE_WEBHOOK_SECRET` | `whsec_...` | API |
| `STRIPE_PRICE_HUNT_PASS_30` | `price_...` | API |

### Optional (recommended)

| Variable | Default | Purpose |
|----------|---------|---------|
| `JWT_EXPIRES_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_DAYS` | `14` | Refresh token lifetime |
| `STRIPE_PRICE_PREMIUM_PLUS_30` | — | Premium Plus checkout |
| `STRIPE_PRICE_CONCIERGE_ONE_TIME` | — | Concierge checkout |
| `RATE_LIMIT_AUTH_REGISTER_PER_MINUTE` | `5` | Abuse protection |
| `RATE_LIMIT_AUTH_LOGIN_PER_MINUTE` | `20` | Abuse protection |
| `RATE_LIMIT_INCENTIVE_SUBMIT_PER_MINUTE` | `6` | Abuse protection |
| `RATE_LIMIT_ADMIN_PER_MINUTE` | `120` | Abuse protection |
| `ENABLE_DAILY_CRAWL` | `false` | Allow scheduled crawl job |
| `PENDING_INCENTIVE_TTL_DAYS` | `90` | Pending incentive expiry |
| `CRAWL_LIMIT` | `20` | Max sources per crawl run |
| `CRAWLER_USER_AGENT` | — | Identifiable crawler string |

Validate:

```bash
./scripts/check_prod_env.sh
```

---

## 5. CORS configuration

The browser web app (`app.example.com`) calls the API (`api.example.com`) cross-origin. Set these three consistently:

```bash
CORS_ORIGINS=https://app.example.com
APP_BASE_URL=https://app.example.com
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

Rules:

- Include `https://` — no trailing slash.
- **`CORS_ORIGINS` must include `APP_BASE_URL`** or login/register/checkout from the browser will fail.
- Multiple origins: comma-separated, e.g. `https://app.example.com,https://www.example.com`.

CORS is configured in `app/main.py` via `CORSMiddleware` using `CORS_ORIGINS`.

Verify after deploy:

```bash
API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
```

The smoke test sends an `OPTIONS` preflight to `/auth/login` with your web origin.

---

## 6. Database migration

Run migrations **before** sending user traffic. Production bootstrap applies schema + migrations + Hunt Pass plans only — **never** demo buildings or incentives.

Full reference: [DATABASE.md](./DATABASE.md)

### First deploy (empty database)

```bash
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml ps postgres   # wait until "healthy"

ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
```

### Every subsequent deploy

```bash
./scripts/prod_migrate.sh
./scripts/prod_verify_db.sh
docker compose -f docker-compose.prod.yml up -d --build
```

`prod_migrate.sh` runs verification automatically unless `SKIP_PROD_VERIFY=yes`.

### Managed Postgres (no compose postgres service)

Set `DATABASE_URL` and `MIGRATE_DATABASE_URL` to the provider connection string (same value is fine):

```bash
ALLOW_PROD_BOOTSTRAP=yes DATABASE_URL='postgresql://user:pass@host:5432/dbname' ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
```

---

## 7. Health check endpoints

| Endpoint | Type | Expected | Use for |
|----------|------|----------|---------|
| `GET /health` | Liveness | `{"status":"ok"}` | Uptime monitor, load balancer alive probe |
| `GET /health/ready` | Readiness | `{"status":"ready"}` | Deploy gate — returns **503** if Postgres is down |

Manual check:

```bash
curl -sf https://api.example.com/health
curl -sf https://api.example.com/health/ready
```

Docker Compose health-checks the API container against `/health/ready` (see `docker-compose.prod.yml`).

Point your reverse proxy / uptime monitor at these URLs after TLS is configured.

---

## 8. Stripe webhook setup

1. In [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks), create an endpoint:
   - **URL:** `https://api.example.com/webhooks/stripe`
   - **Events:**
     - `checkout.session.completed`
     - `checkout.session.expired`
     - `invoice.payment_succeeded`
     - `customer.subscription.deleted`
     - `customer.subscription.updated`
     - `charge.refunded`

2. Copy the **signing secret** → `STRIPE_WEBHOOK_SECRET` in `.env`.

3. Create a Product + Price for Hunt Pass (30 days) → `STRIPE_PRICE_HUNT_PASS_30`.

4. Ensure `MOCK_CHECKOUT_MODE=false` and restart API:

   ```bash
   docker compose -f docker-compose.prod.yml up -d api
   ```

5. Verify configuration:

   ```bash
   ./scripts/verify_stripe.sh
   ```

6. Complete a test purchase: [STRIPE_RUNBOOK.md](./STRIPE_RUNBOOK.md).

**Test vs live:** use `sk_test_` keys and a test-mode webhook secret until checkout works end-to-end, then switch all three to live values together.

---

## 9. Scheduled job setup

**Required:** expire Hunt Pass entitlements daily. Without this, access continues past the 30-day window.

Full reference: [SCHEDULED_JOBS.md](./SCHEDULED_JOBS.md)

### Option A — Docker jobs profile (simplest)

```bash
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs
```

Runs `python -m jobs.run_scheduled` every 24 hours inside the jobs container.

### Option B — Host cron

Install Python deps on the host or run via Docker:

```cron
# /etc/cron.d/kayak
0 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh >> /var/log/kayak-jobs.log 2>&1
15 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh --expire-pending >> /var/log/kayak-jobs.log 2>&1
```

Optional crawl (only when `ENABLE_DAILY_CRAWL=true` in `.env`):

```cron
30 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh --crawl >> /var/log/kayak-jobs.log 2>&1
```

Or combine: `./scripts/run_scheduled_jobs.sh --all`

---

## 10. Post-deploy smoke tests

Configure TLS first (see [Reverse proxy](#reverse-proxy-tls) below), then run:

```bash
export API_URL=https://api.example.com
export WEB_URL=https://app.example.com
./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

`prod_smoke.sh` checks:

| Check | What it validates |
|-------|-------------------|
| `GET /health` | API is up |
| `GET /health/ready` | Postgres reachable |
| `GET /plans` | Hunt Pass plan seeded |
| CORS preflight | Browser can call API from web origin |
| `POST /auth/register` | Auth + DB writes work |
| `GET $WEB_URL/` | Web frontend responds |

Then complete a Stripe test checkout per [STRIPE_RUNBOOK.md](./STRIPE_RUNBOOK.md) and import real incentives per [VERIFIED_INCENTIVES.md](./VERIFIED_INCENTIVES.md).

---

## 11. Rollback

| Layer | Action |
|-------|--------|
| **API / web code** | `git checkout <previous-tag>` → `docker compose -f docker-compose.prod.yml up -d --build` |
| **Environment** | Restore backed-up `.env` → restart affected services |
| **Database** | Migrations are forward-only — restore Postgres from snapshot if a migration caused issues |
| **Stripe** | Webhook endpoint can stay; revert price IDs in `.env` if pricing changed |
| **Web build** | Rebuild web if `NEXT_PUBLIC_*` changed: `docker compose -f docker-compose.prod.yml build --no-cache web` |

**Before every deploy:** back up `.env` and take a Postgres snapshot.

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U kayak kayak_prod > kayak_prod_$(date +%Y%m%d).sql
```

---

## 12. Common failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| API container exits immediately | Missing/weak `JWT_SECRET`, `MOCK_AUTH_MODE=true`, or missing Stripe vars | Run `./scripts/check_prod_env.sh`; check `docker compose logs api` |
| `GET /health/ready` → 503 | Postgres not running or wrong `DATABASE_URL` | `docker compose -f docker-compose.prod.yml ps postgres`; verify `DATABASE_URL` uses hostname `postgres` inside Docker |
| Browser login fails (CORS error) | `CORS_ORIGINS` missing web URL | Set `CORS_ORIGINS=https://app.example.com` matching `APP_BASE_URL`; restart API |
| Web shows wrong API / network errors | Stale `NEXT_PUBLIC_API_BASE_URL` baked into build | Update `.env`, rebuild: `docker compose -f docker-compose.prod.yml build --no-cache web` |
| Checkout redirects to localhost | `APP_BASE_URL` not set to production web URL | Fix `.env`, restart API |
| Stripe webhook 400/401 | Wrong `STRIPE_WEBHOOK_SECRET` or test secret with live key | Match webhook secret to the Stripe mode (test vs live) |
| Hunt Pass not granted after payment | Webhook not reaching API or wrong endpoint URL | Confirm Stripe webhook URL is `https://api.example.com/webhooks/stripe`; check API logs |
| `./scripts/prod_migrate.sh` fails on `.env` | Special characters in values (e.g. parentheses in user agent) | Scripts use safe dotenv loading — ensure you are on latest repo; or run with explicit `DATABASE_URL=...` |
| `ALLOW_PROD_BOOTSTRAP=yes` required | Running `--bootstrap` on empty DB without opt-in | Set `ALLOW_PROD_BOOTSTRAP=yes` for first deploy only |
| Admin pages 403 | Email not in `ADMIN_EMAILS` | Add admin email to `.env`, restart API |
| Demo incentives visible in production | `SHOW_DEMO_DATA=true` or demo seed ran | Set `SHOW_DEMO_DATA=false`; never run `bootstrap_db.sh` in production |
| Jobs not expiring entitlements | Cron/jobs container not running | Enable jobs profile or host cron (§9) |

---

## Reverse proxy (TLS)

Expose web and API on HTTPS. Example **Caddy** (`/etc/caddy/Caddyfile`):

```caddy
app.example.com {
    reverse_proxy localhost:3000
}

api.example.com {
    reverse_proxy localhost:8000
}
```

```bash
sudo caddy reload --config /etc/caddy/Caddyfile
```

Compose binds API (`8000`) and web (`3000`) to localhost by default when you use `127.0.0.1` in the proxy config above. Adjust if you expose ports publicly during initial testing.

---

## Deploy checklist (copy/paste)

```bash
# 1. Environment
cp .env.production.example .env    # fill all secrets
./scripts/check_prod_env.sh

# 2. Database
docker compose -f docker-compose.prod.yml up -d postgres
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap   # first deploy only
./scripts/prod_verify_db.sh

# 3. Services
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs   # optional

# 4. TLS — configure Caddy/nginx, then:
API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
./scripts/verify_stripe.sh
```

**Subsequent deploys:**

```bash
./scripts/prod_migrate.sh
./scripts/prod_verify_db.sh
docker compose -f docker-compose.prod.yml up -d --build
API_URL=https://api.example.com WEB_URL=https://app.example.com ./scripts/prod_smoke.sh
```

---

## Related docs

- [LAUNCH.md](../LAUNCH.md) — launch-day copy/paste sequence and known risks
- [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md) — pre-launch checklist
- [DATABASE.md](./DATABASE.md) — dev vs production DB commands
- [STRIPE_RUNBOOK.md](./STRIPE_RUNBOOK.md) — Hunt Pass payment verification
- [SCHEDULED_JOBS.md](./SCHEDULED_JOBS.md) — cron and jobs detail
- [VERIFIED_INCENTIVES.md](./VERIFIED_INCENTIVES.md) — real inventory import

---

## Alternative platforms (Render / Railway)

If you prefer a managed platform over a VPS, deploy the same Docker images:

| Component | Render | Railway |
|-----------|--------|---------|
| API | Web Service → root `Dockerfile` | Service → root `Dockerfile` |
| Web | Web Service → `web/Dockerfile` | Service → `web/Dockerfile` |
| Postgres | Render Postgres addon | Railway Postgres plugin |
| Migrate | Shell: `ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap` | Same via Railway shell |
| Jobs | Cron job → `./scripts/run_scheduled_jobs.sh` | Cron or separate worker service |

Use the same env vars from [§4](#4-environment-variables). Set `DATABASE_URL` to the provider connection string (no Docker hostname `postgres`). Run `./scripts/prod_smoke.sh` against the public API URL after deploy.
