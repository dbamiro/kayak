#!/usr/bin/env bash
# Bulk import admin-verified incentives from CSV (CLI alternative to Admin UI).
#
# Usage:
#   TOKEN=<admin_jwt> ./scripts/import_incentives_csv.sh path/to/verified.csv
#   TOKEN=<admin_jwt> ./scripts/import_incentives_csv.sh --dry-run path/to/verified.csv
#
# Or register an admin and import in one step:
#   ADMIN_EMAIL=ops@example.com ADMIN_PASSWORD=secret ./scripts/import_incentives_csv.sh verified.csv
#
# Template: fixtures/incentives_import_template.csv → verified_specials.csv
# Workflow: docs/DMV_INCENTIVE_IMPORT.md (example file rows are rejected).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY_RUN=false
CSV_PATH=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    -*) echo "Unknown option: $arg" >&2; exit 2 ;;
    *) CSV_PATH="$arg" ;;
  esac
done

if [[ -z "$CSV_PATH" || ! -f "$CSV_PATH" ]]; then
  echo "Usage: TOKEN=<jwt> ./scripts/import_incentives_csv.sh [--dry-run] path/to.csv" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

API_URL="${API_URL:-http://127.0.0.1:8000}"
API_URL="${API_URL%/}"

TOKEN="${TOKEN:-}"
if [[ -z "$TOKEN" && -n "${ADMIN_EMAIL:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
  TOKEN="$(curl -sf -X POST "$API_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"
fi

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: Set TOKEN (admin JWT) or ADMIN_EMAIL + ADMIN_PASSWORD" >&2
  exit 1
fi

QUERY=""
if [[ "$DRY_RUN" == "true" ]]; then
  QUERY="?dry_run=true"
fi

RESP="$(curl -s -w "\n%{http_code}" -X POST "$API_URL/admin/incentives/import${QUERY}" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@${CSV_PATH};type=text/csv")"

BODY="$(echo "$RESP" | head -n -1)"
CODE="$(echo "$RESP" | tail -n 1)"

if [[ "$CODE" != "200" ]]; then
  echo "FAIL: HTTP $CODE" >&2
  echo "$BODY" >&2
  exit 1
fi

echo "$BODY" | python3 -m json.tool

CREATED="$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['created_count'])")"
ERRORS="$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['error_count'])")"

if [[ "$ERRORS" -gt 0 ]]; then
  echo ""
  echo "Import finished with $ERRORS error(s). Fix CSV and retry." >&2
  exit 1
fi

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  echo "Validation OK — $CREATED row(s) ready to import."
else
  echo "Import OK — $CREATED incentive(s) created (verified, is_demo=false)."
  echo "Verify: curl -s '$API_URL/incentives?include_demo=false' | python3 -m json.tool"
fi
