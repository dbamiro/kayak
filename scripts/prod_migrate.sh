#!/usr/bin/env bash
# Apply database migrations before serving traffic.
#
# Every deploy (existing DB):
#   ./scripts/prod_migrate.sh
#   ./scripts/prod_verify_db.sh
#
# First deploy on empty Postgres (schema + migrations + plans only — no demo seed):
#   ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap
#   ./scripts/prod_verify_db.sh
#
# Uses MIGRATE_DATABASE_URL when set (host → 127.0.0.1), else DATABASE_URL from .env.
# Requires: psql (install postgresql-client on the VPS)
#
# Source of truth: sql/migrations/*.sql (always applied). sql/schema.sql is baseline
# for empty databases only. See docs/DATABASE.md.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BOOTSTRAP=false
if [[ "${1:-}" == "--bootstrap" ]]; then
  BOOTSTRAP=true
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

DB_URL="${MIGRATE_DATABASE_URL:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "ERROR: Set DATABASE_URL (containers) or MIGRATE_DATABASE_URL (host psql) in .env" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql not found. Install postgresql-client (e.g. apt install postgresql-client)" >&2
  exit 1
fi

apply_sql() {
  local file="$1"
  local base
  base="$(basename "$file")"
  case "$base" in
    seed.sql|seed_incentives.sql|seed_real_data_pilot.sql)
      echo "ERROR: Refusing to apply demo seed in production: $base" >&2
      exit 1
      ;;
  esac
  echo "==> Applying $base"
  psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$file"
}

if [[ "$BOOTSTRAP" == "true" ]]; then
  if [[ "${ALLOW_PROD_BOOTSTRAP:-}" != "yes" ]]; then
    echo "ERROR: --bootstrap requires ALLOW_PROD_BOOTSTRAP=yes" >&2
    echo "This never runs demo seeds (seed.sql / seed_incentives.sql)." >&2
    exit 1
  fi
  has_buildings="$(psql "$DB_URL" -tAc "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='buildings' LIMIT 1" 2>/dev/null || echo "")"
  if [[ "$has_buildings" != "1" ]]; then
    echo "==> Fresh database — applying schema.sql"
    apply_sql sql/schema.sql
  else
    echo "==> Existing database — skipping schema.sql (buildings table present)"
  fi
fi

shopt -s nullglob
migrations=(sql/migrations/*.sql)
shopt -u nullglob
if [[ ${#migrations[@]} -eq 0 ]]; then
  echo "ERROR: No migration files found in sql/migrations/" >&2
  exit 1
fi

for migration in "${migrations[@]}"; do
  apply_sql "$migration"
done

echo "==> Seeding monetization plans (idempotent, no demo buildings or incentives)"
apply_sql sql/seed_plans.sql

if [[ "${SKIP_PROD_VERIFY:-}" != "yes" ]]; then
  echo ""
  echo "==> Verifying production schema"
  export DATABASE_URL="$DB_URL"
  if ! env PYTHONPATH="$ROOT" "${ROOT}/scripts/prod_verify_db.sh"; then
    echo "ERROR: Post-migration verification failed." >&2
    exit 1
  fi
fi

echo ""
echo "Migration complete."
