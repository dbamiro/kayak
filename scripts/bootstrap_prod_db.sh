#!/usr/bin/env bash
# Production database bootstrap (first deploy only).
# Delegates to prod_migrate.sh — never runs demo seeds.
#
# Usage:
#   ALLOW_PROD_BOOTSTRAP=yes ./scripts/bootstrap_prod_db.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export ALLOW_PROD_BOOTSTRAP="${ALLOW_PROD_BOOTSTRAP:-}"
exec "$ROOT/scripts/prod_migrate.sh" --bootstrap
