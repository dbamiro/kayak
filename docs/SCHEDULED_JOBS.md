# Kayak scheduled jobs (production)

Background jobs run **without the web server**. They only need `DATABASE_URL` (and crawler env for optional crawl).

## What to run and how often

| Job | Module | Schedule | Required? |
|-----|--------|----------|-----------|
| **Expire Hunt Pass** | `jobs.expire_entitlements` | Daily 06:00 UTC | **Yes** |
| **Expire pending incentives** | `jobs.expire_pending_incentives` | Daily 06:15 UTC | Optional (recommended) |
| **Daily crawl** | `jobs.daily_run` | Daily 06:30 UTC | Optional — **disabled** unless configured |

### 1. Expire entitlements (required)

Marks `customer_entitlements` as `expired` when `expires_at < now()`. Without this, Hunt Pass access continues after the 30-day window until the next API read triggers expiry.

```bash
PYTHONPATH=. python -m jobs.expire_entitlements
# exit 0 — logs: job=expire_entitlements status=ok count=N
```

### 2. Expire pending incentives (optional)

Marks `pending_review` incentives as `expired` when:

- `expires_at` is in the past, or
- no `expires_at` and `created_at` older than `PENDING_INCENTIVE_TTL_DAYS` (default **90**)

Keeps the admin review queue clean. Does **not** affect verified/active specials.

```bash
PYTHONPATH=. python -m jobs.expire_pending_incentives
PYTHONPATH=. python -m jobs.expire_pending_incentives --stale-days 60
```

### 3. Daily crawl (optional, off by default)

Crawls **active** `sources` rows when permitted. Skipped unless:

```bash
ENABLE_DAILY_CRAWL=true
```

in `.env`, or you pass `--force` / `--source-id` for manual pilot runs.

```bash
# Scheduled (respects ENABLE_DAILY_CRAWL)
PYTHONPATH=. python -m jobs.daily_run --limit 20

# Manual pilot (single source, ignores ENABLE_DAILY_CRAWL)
PYTHONPATH=. python -m jobs.daily_run --source-id <uuid> --mode playwright --force
```

---

## Orchestrator (recommended for cron)

Run multiple jobs in one process:

```bash
# Minimum production cron — Hunt Pass expiry only
PYTHONPATH=. python -m jobs.run_scheduled

# Recommended — entitlements + pending incentive cleanup
PYTHONPATH=. python -m jobs.run_scheduled --expire-pending

# Full — add crawl when ENABLE_DAILY_CRAWL=true
PYTHONPATH=. python -m jobs.run_scheduled --expire-pending --crawl --crawl-limit 20
```

Shell wrapper (loads `.env`):

```bash
./scripts/run_scheduled_jobs.sh
./scripts/run_scheduled_jobs.sh --expire-pending
./scripts/run_scheduled_jobs.sh --all
```

---

## Production cron examples

Replace `/home/deploy/Kayak` and user `deploy` with your paths.

```cron
# /etc/cron.d/kayak-jobs
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# Required — Hunt Pass expiry daily 06:00 UTC
0 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh >> /var/log/kayak-jobs.log 2>&1

# Recommended — pending incentive cleanup 06:15 UTC
15 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh --expire-pending >> /var/log/kayak-jobs.log 2>&1

# Optional crawl — only when ENABLE_DAILY_CRAWL=true in .env
30 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh --crawl >> /var/log/kayak-jobs.log 2>&1
```

**Single combined cron** (alternative):

```cron
0 6 * * * deploy cd /home/deploy/Kayak && ./scripts/run_scheduled_jobs.sh --all >> /var/log/kayak-jobs.log 2>&1
```

Crawl lines are no-ops when `ENABLE_DAILY_CRAWL` is unset (logged as `status=skipped`).

---

## Docker Compose jobs profile

```bash
docker compose -f docker-compose.prod.yml --profile jobs up -d jobs
```

Runs `jobs.run_scheduled` every 24 hours (entitlements only). For pending/crawl, override command:

```yaml
command: ["python", "-m", "jobs.run_scheduled", "--expire-pending", "--crawl", "--crawl-limit", "20"]
```

---

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | — | **Required** for all jobs |
| `ENABLE_DAILY_CRAWL` | `false` | Must be `true` for scheduled crawl |
| `CRAWL_LIMIT` | `20` | Used by `run_scheduled_jobs.sh --crawl` |
| `PENDING_INCENTIVE_TTL_DAYS` | `90` | Stale pending_review without expires_at |
| `CRAWLER_USER_AGENT` | — | Identifiable crawler string when crawling |

Jobs do **not** require `JWT_SECRET`, Stripe keys, or the Next.js web app.

---

## Exit codes and logging

| Code | Meaning |
|------|---------|
| `0` | All jobs succeeded or were intentionally skipped |
| `1` | At least one job failed (check logs / DB connectivity) |

Logs go to stdout in format:

```
2026-07-02T06:00:01+0000 INFO [kayak.jobs] job=expire_entitlements status=ok count=3 expired_entitlements=3
```

Monitor cron mail or ship `/var/log/kayak-jobs.log` to your log aggregator.

---

## Verify locally

```bash
export PYTHONPATH="$(pwd)"
python -m jobs.expire_entitlements
python -m jobs.expire_pending_incentives
python -m jobs.run_scheduled --expire-pending
ENABLE_DAILY_CRAWL=false python -m jobs.run_scheduled --crawl   # status=skipped
```

See also [PRODUCTION_DEPLOY.md](./PRODUCTION_DEPLOY.md).
