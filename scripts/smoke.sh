#!/usr/bin/env bash
# Local smoke test: API health + core incentive/search endpoints + deal report preview.
#
# Usage:
#   ./scripts/smoke.sh
#   API_URL=http://127.0.0.1:8000 ./scripts/smoke.sh
#
# Expects API running (see README Quick start). DB should be bootstrapped for /search.

set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

echo "==> Kayak smoke test (API: $API_URL)"

# Health (no DB required)
HEALTH="$(curl -sf "$API_URL/health" || fail "GET /health — is the API running on :8000?")"
echo "$HEALTH" | grep -q '"status"' || fail "/health response unexpected: $HEALTH"
pass "/health"

# Calculator (no DB)
CALC="$(curl -sf -X POST "$API_URL/incentives/calculate" \
  -H 'Content-Type: application/json' \
  -d '{"listed_rent":2400,"lease_term_months":16,"free_months":4}' \
  || fail "POST /incentives/calculate")"
echo "$CALC" | grep -q '"effective_rent"' || fail "calculate response missing effective_rent"
pass "/incentives/calculate (effective rent)"

# Search (DB)
SEARCH="$(curl -sf "$API_URL/search" || fail "GET /search — run ./scripts/bootstrap_db.sh first?")"
if command -v jq >/dev/null 2>&1; then
  SEARCH_COUNT="$(echo "$SEARCH" | jq 'length')"
  pass "/search ($SEARCH_COUNT rows)"
  if [[ "$SEARCH_COUNT" -eq 0 ]]; then
    echo "WARN: /search returned 0 rows — run ./scripts/bootstrap_db.sh" >&2
  else
    BUILDING_ID="$(echo "$SEARCH" | jq -r '.[0].building_id')"
    BUILDING_NAME="$(echo "$SEARCH" | jq -r '.[0].name')"
    pass "sample building: $BUILDING_NAME ($BUILDING_ID)"
  fi
else
  pass "/search (install jq for richer checks)"
  BUILDING_ID=""
fi

# Incentives (DB)
INCENTIVES="$(curl -sf "$API_URL/incentives?limit=5" || fail "GET /incentives")"
if command -v jq >/dev/null 2>&1; then
  INC_COUNT="$(echo "$INCENTIVES" | jq 'length')"
  pass "/incentives ($INC_COUNT specials)"
else
  pass "/incentives"
fi

# Plans (DB)
curl -sf "$API_URL/plans" >/dev/null || fail "GET /plans"
pass "/plans"

# Building detail + deal report preview (DB)
if command -v jq >/dev/null 2>&1 && [[ -n "${BUILDING_ID:-}" && "$BUILDING_ID" != "null" ]]; then
  curl -sf "$API_URL/buildings/$BUILDING_ID" >/dev/null || fail "GET /buildings/{id}"
  pass "/buildings/{id}"

  DEAL="$(curl -sf "$API_URL/deal-reports/$BUILDING_ID" || fail "GET /deal-reports/{id}")"
  ACCESS="$(echo "$DEAL" | jq -r '.access')"
  [[ "$ACCESS" == "preview" || "$ACCESS" == "full" ]] || fail "deal report access unexpected: $ACCESS"
  pass "/deal-reports/{id} (access=$ACCESS)"
fi

echo ""
echo "Smoke test passed."
echo "Web UI: http://localhost:3000/search | /specials | /calculator"
echo "Run from repo root: cd web && npm run dev"
