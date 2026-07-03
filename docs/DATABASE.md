# Kayak database setup

Kayak v1 uses **PostgreSQL**. Schema changes are applied in two layers:

| Layer | Path | Role |
|-------|------|------|
| **Baseline** | `sql/schema.sql` | Full initial schema for an **empty** database (buildings through monetization). Applied once on first production bootstrap. |
| **Migrations** | `sql/migrations/*.sql` | **Source of truth** for all incremental changes (incentives, auth, review workflow). Applied on **every** deploy; files are idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). |
| **Production seed** | `sql/seed_plans.sql` | Hunt Pass / plan catalog only. No buildings, listings, or demo incentives. |
| **Dev seeds** | `seed.sql`, `seed_incentives.sql` | Demo buildings and incentives — **dev only**. |

Do **not** consolidate everything into `schema.sql`. New changes belong in numbered migrations so existing production databases upgrade safely.

## Production (fresh database)

From the repo root, with Postgres reachable and `.env` containing `DATABASE_URL` (or `MIGRATE_DATABASE_URL` for host-side `psql`):

```bash
# 1. Bootstrap: schema + migrations + plans (requires explicit opt-in)
ALLOW_PROD_BOOTSTRAP=yes ./scripts/bootstrap_prod_db.sh

# 2. Verify required tables and no demo incentives
./scripts/prod_verify_db.sh
```

Equivalent single command:

```bash
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
./scripts/prod_verify_db.sh
```

`prod_migrate.sh --bootstrap` **never** runs `seed.sql`, `seed_incentives.sql`, or `seed_real_data_pilot.sql`.

## Production (subsequent deploys)

Apply pending migrations only (skips `schema.sql` unless `--bootstrap`):

```bash
./scripts/prod_migrate.sh
./scripts/prod_verify_db.sh
```

## Local development

Demo buildings, listing snapshots, and sample incentives:

```bash
./scripts/bootstrap_db.sh
```

Uses `schema.sql` → migrations → `seed.sql` → `seed_incentives.sql`.

Pytest uses an isolated `kayak_test` database via `tests/db_bootstrap.py` (schema + migrations + `tests/fixtures/test_seed.sql`).

## Manual verification (psql)

```bash
psql "$DATABASE_URL" -c "
  SELECT table_name
  FROM information_schema.tables
  WHERE table_schema = 'public'
    AND table_name IN (
      'buildings','listings','listing_snapshots','sources',
      'incentives','incentive_snapshots','incentive_sources',
      'users','customer_entitlements','plans'
    )
  ORDER BY 1;
"

psql "$DATABASE_URL" -c "SELECT COUNT(*) AS demo_incentives FROM incentives WHERE is_demo = true;"
```

Expected after production bootstrap: all listed tables exist; `demo_incentives = 0`.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | App and default migrate target |
| `MIGRATE_DATABASE_URL` | Host-side migrate URL (e.g. `127.0.0.1` instead of Docker service name) |
| `ALLOW_PROD_BOOTSTRAP` | Must be `yes` to run `--bootstrap` on an empty DB |
| `ALLOW_DEMO_INCENTIVES` | Set to `yes` for `prod_verify_db.sh` on dev DBs with demo incentives |

See also: [PRODUCTION_DEPLOY.md](PRODUCTION_DEPLOY.md), [PRODUCTION_CHECKLIST.md](../PRODUCTION_CHECKLIST.md).
