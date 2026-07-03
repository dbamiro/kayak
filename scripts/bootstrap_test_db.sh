#!/usr/bin/env bash
# Create/isolate kayak_test DB and load deterministic pytest seed.
# Safe to run repeatedly — does not touch dmv_apartments dev database.
#
# Usage:
#   ./scripts/bootstrap_test_db.sh
#   TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/kayak_test ./scripts/bootstrap_test_db.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://dmv_user:dmv_pass@localhost:5432/kayak_test}"

if ! pg_isready -h localhost -p 5432 -U dmv_user >/dev/null 2>&1; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "==> Starting postgres via docker compose..."
    docker compose up -d postgres
    for i in $(seq 1 30); do
      pg_isready -h localhost -p 5432 -U dmv_user >/dev/null 2>&1 && break
      sleep 1
    done
  fi
fi

export TEST_DATABASE_URL
export PYTHONPATH="$ROOT"
./.venv/bin/python -c "
from tests.db_bootstrap import bootstrap_test_database, get_test_database_url
url = bootstrap_test_database(get_test_database_url())
print(f'OK: test database ready at {url}')
"
