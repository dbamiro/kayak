#!/usr/bin/env bash
# Bootstrap Postgres for local Kayak dev (schema + migrations + demo seed).
#
# Usage:
#   ./scripts/bootstrap_db.sh
#   DATABASE_URL=postgresql://... ./scripts/bootstrap_db.sh
#
# Requires: psql, pg_isready. Optionally uses docker compose to start postgres.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  line="$(grep -E '^DATABASE_URL=' .env | head -1 || true)"
  if [[ -n "$line" ]]; then
    DATABASE_URL="${line#DATABASE_URL=}"
    DATABASE_URL="${DATABASE_URL%\"}"
    DATABASE_URL="${DATABASE_URL#\"}"
    export DATABASE_URL
  fi
fi

DATABASE_URL="${DATABASE_URL:-postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments}"

pg_host="${PGHOST:-localhost}"
pg_port="${PGPORT:-5432}"
pg_user="${PGUSER:-dmv_user}"

wait_for_postgres() {
  local i
  for i in $(seq 1 30); do
    if pg_isready -h "$pg_host" -p "$pg_port" -U "$pg_user" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

maybe_start_docker_postgres() {
  if pg_isready -h "$pg_host" -p "$pg_port" -U "$pg_user" >/dev/null 2>&1; then
    echo "==> Postgres already accepting connections on ${pg_host}:${pg_port}"
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "==> Starting postgres via docker compose..."
    docker compose up -d postgres
    wait_for_postgres || {
      echo "ERROR: Postgres did not become ready in time." >&2
      exit 1
    }
    return 0
  fi
  echo "ERROR: Postgres is not running on ${pg_host}:${pg_port}." >&2
  echo "       Start it manually or run: docker compose up -d postgres" >&2
  exit 1
}

apply_sql() {
  local file="$1"
  echo "==> Applying $(basename "$file")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
}

maybe_start_docker_postgres

has_buildings="$(psql "$DATABASE_URL" -tAc "SELECT 1 FROM information_schema.tables WHERE table_name='buildings' LIMIT 1" 2>/dev/null || echo "")"

if [[ "$has_buildings" != "1" ]]; then
  echo "==> Fresh database — applying schema.sql"
  apply_sql sql/schema.sql
else
  echo "==> Existing database — skipping schema.sql (buildings table present)"
fi

for migration in sql/migrations/*.sql; do
  apply_sql "$migration"
done

echo "==> Seeding demo buildings + listing snapshots"
apply_sql sql/seed.sql

if [[ -f sql/seed_incentives.sql ]]; then
  echo "==> Seeding demo incentives"
  apply_sql sql/seed_incentives.sql
fi

echo ""
echo "Bootstrap complete."
echo "  DATABASE_URL=$DATABASE_URL"
echo "  Next: export PYTHONPATH=\"$ROOT\" && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8000"
