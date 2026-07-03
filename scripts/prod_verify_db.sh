#!/usr/bin/env bash
# Verify Kayak v1 production schema after bootstrap or migrate.
#
# Usage:
#   ./scripts/prod_verify_db.sh
#   MIGRATE_DATABASE_URL=postgresql://... ./scripts/prod_verify_db.sh
#
# Set ALLOW_DEMO_INCENTIVES=yes only for local dev databases that intentionally
# contain demo incentive rows.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

DB_URL="${MIGRATE_DATABASE_URL:-${DATABASE_URL:-}}"
if [[ -z "$DB_URL" ]]; then
  echo "ERROR: Set DATABASE_URL or MIGRATE_DATABASE_URL in .env" >&2
  exit 1
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

export DATABASE_URL="$DB_URL"
exec env PYTHONPATH="$ROOT" "$PYTHON" -m app.db_schema verify "$DB_URL"
