# Kayak v1 — deployment readiness report

**Date:** 2026-07-03  
**Scope:** Production dry run following [LAUNCH.md](LAUNCH.md) and [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)  
**Verdict:** **GO with fixes applied** — launch docs and scripts are followable; two launch blockers were found and fixed during this audit.

---

## Executive summary

| Gate | Result |
|------|--------|
| pytest (141 tests) | **PASS** |
| `npm run build` (host) | **PASS** |
| `docker compose -f docker-compose.prod.yml build` | **PASS** (after Dockerfile fix) |
| `check_prod_env.sh` | **PASS** (after `load_env.sh` fix) |
| Fresh DB bootstrap + verify | **PASS** — 0 demo incentives |
| `prod_smoke.sh` (API + CORS) | **PASS** |
| `verify_stripe.sh` | **PASS** (env validation; live checkout needs real Stripe keys) |
| Admin + CSV import + jobs | **PASS** (manual dry-run steps) |
| Manual browser QA | **Not run** — requires human + TLS domains |

---

## Dry-run execution log

### Automated (this audit)

```bash
./.venv/bin/python -m pytest -q                    # 141 passed
cd web && npm run build                            # OK
cp .env.production.example .env  # + fill secrets
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/check_prod_env.sh                        # OK
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap  # fresh DB, port 5433
./scripts/prod_verify_db.sh                        # OK, demo incentives: none
docker compose -f docker-compose.prod.yml build    # api + web OK
./scripts/verify_stripe.sh                         # OK
API_URL=http://127.0.0.1:8001 WEB_URL=http://127.0.0.1:3000 ./scripts/prod_smoke.sh  # OK
```

### Staging notes used for local dry run

| Doc default | Dry-run substitute | Why |
|-------------|-------------------|-----|
| `https://api.example.com` | `http://127.0.0.1:8001` | No TLS locally; API via host uvicorn |
| `https://app.example.com` | `http://127.0.0.1:3000` | Local Next.js for smoke WEB check |
| `docker compose … postgres` on `:5432` | `docker run … -p 127.0.0.1:5433:5432` | Existing dev Postgres occupied `:5432` |
| Real Stripe keys | Placeholder `sk_test_*` / `whsec_*` / `price_*` | `verify_stripe.sh` passes; checkout needs Dashboard keys |

---

## Issues found and fixed

### 1. `check_prod_env.sh` silently failed to load `.env` (launch blocker)

**Cause:** `scripts/lib/load_env.sh` used system `python3`, which lacked `python-dotenv`. Import failed with exit 0 → no env vars loaded.

**Fix:** Prefer `.venv/bin/python`; fail loudly if `python-dotenv` missing.

**Doc update:** [LAUNCH.md](LAUNCH.md) and [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) — add host venv step:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

### 2. Docker web build failed (launch blocker)

**Cause:** `web/Dockerfile` ran `npm install` without `package-lock.json` → `@next/swc` version mismatch vs Next.js 15.1.8.

**Fix:** `COPY package.json package-lock.json ./` + `npm ci`; added `web/.dockerignore`.

---

## Commands that work as documented

| Command | Status |
|---------|--------|
| `./scripts/check_prod_env.sh` | Works with `.venv` |
| `ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap` | Works; auto-runs verify |
| `./scripts/prod_verify_db.sh` | Works |
| `./scripts/prod_smoke.sh` | Works when API up; **WEB check needs web server on `WEB_URL`** |
| `./scripts/verify_stripe.sh` | Works (config check) |
| `./scripts/import_incentives_csv.sh` | Works with admin `TOKEN` |
| `./scripts/run_scheduled_jobs.sh --expire-pending` | Works with `.venv` + `DATABASE_URL` |
| `docker compose -f docker-compose.prod.yml build` | Works after Dockerfile fix |

## Commands requiring extra context (documented below)

| Command | When / where |
|---------|----------------|
| `docker compose … down -v` | **Production server only** — wipes Postgres volume |
| `./scripts/stripe_test_checkout.sh` | Requires **real** Stripe test keys + API running + `stripe listen` |
| Stripe webhook SQL check | After a real test payment |
| TLS / Caddy / nginx | **Production server** — not local |
| Manual browser QA (§9 checklist) | Human tester + deployed HTTPS URLs |
| `git checkout v1.0.0` | Replace with your release tag |

---

## Demo data safety

| Check | Result |
|-------|--------|
| `prod_migrate.sh --bootstrap` on empty DB | No demo buildings/incentives |
| `prod_verify_db.sh` | Fails if `is_demo=true` rows exist |
| `prod_migrate.sh` apply_sql blocklist | Refuses `seed.sql`, `seed_incentives.sql`, `seed_real_data_pilot.sql` |
| `bootstrap_db.sh` | **Dev only** — not invoked by prod scripts |

**Ops risk:** Running `psql -f sql/seed.sql` manually bypasses safeguards. Docs already warn; do not run on production.

---

## `.env.production.example` coverage

All variables required by `check_prod_env.sh` and `validate_production()` are present:

`APP_ENV`, `JWT_SECRET`, `MOCK_AUTH_MODE`, `MOCK_CHECKOUT_MODE`, `SHOW_DEMO_DATA`, `POSTGRES_*`, `DATABASE_URL`, `MIGRATE_DATABASE_URL`, `CORS_ORIGINS`, `APP_BASE_URL`, `API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `ADMIN_EMAILS`, `STRIPE_*`, rate limits, job flags.

---

## Known risks (unchanged from LAUNCH.md)

| Risk | Mitigation |
|------|------------|
| Empty search at launch | Import verified CSV before announcing |
| Webhook delay after payment | Success page polls; grant is webhook-only |
| Single-instance rate limits | Edge proxy limits for multi-replica |
| JWT in localStorage | HTTPS only |
| Crawler off by default | CSV import for inventory |
| Forward-only migrations | Postgres snapshot before first migrate |
| Stripe test/live mismatch | Switch key + webhook secret + price together |
| Host scripts need Python venv | `pip install -r requirements.txt` on server |
| `prod_smoke.sh` WEB check | Start web container or `npm run start` before smoke |

---

## Go / no-go recommendation

### GO for production deploy when:

1. Host has Docker, `psql`, and `.venv` with `requirements.txt` installed  
2. `.env` filled from `.env.production.example`; `check_prod_env.sh` passes  
3. Fresh bootstrap: `prod_verify_db.sh` shows zero demo incentives  
4. `docker compose -f docker-compose.prod.yml build` succeeds  
5. Real Stripe test checkout + webhook verified ([STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md))  
6. At least one verified incentive imported  
7. `prod_smoke.sh` passes against **HTTPS** API + web URLs  
8. Manual browser QA (LAUNCH_CHECKLIST §9) complete  

### NO-GO if:

- API won't start (`validate_production()` failure)  
- Demo data in production DB  
- Docker web build fails (verify `npm ci` in Dockerfile)  
- Admin cannot access `/admin/*`  
- CORS blocks browser auth from production web origin  

---

## Doc index (consistent)

| Document | Role |
|----------|------|
| [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) | Step-by-step launch day |
| [LAUNCH.md](LAUNCH.md) | Runbook + known risks |
| [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) | Pre-launch env/security |
| [docs/PRODUCTION_DEPLOY.md](docs/PRODUCTION_DEPLOY.md) | Full VPS + Docker guide |
| [docs/DATABASE.md](docs/DATABASE.md) | Dev vs prod DB |
| [docs/STRIPE_RUNBOOK.md](docs/STRIPE_RUNBOOK.md) | Hunt Pass verification |
| [docs/VERIFIED_INCENTIVES.md](docs/VERIFIED_INCENTIVES.md) | CSV import |
| [docs/SCHEDULED_JOBS.md](docs/SCHEDULED_JOBS.md) | Cron / jobs |
| [docs/ABUSE_PROTECTION.md](docs/ABUSE_PROTECTION.md) | Rate limits |

---

## Files changed during this audit

| File | Change |
|------|--------|
| `scripts/lib/load_env.sh` | Use `.venv` Python; fail if no dotenv |
| `web/Dockerfile` | `npm ci` + lockfile |
| `web/.dockerignore` | Exclude `node_modules`, `.next` |
| `LAUNCH.md` | Host venv prerequisite |
| `LAUNCH_CHECKLIST.md` | Host venv prerequisite |

No product behavior changes.
