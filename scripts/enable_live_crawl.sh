#!/usr/bin/env bash
# Configure a building source with a real URL, test parse, persist snapshots, optionally hide demo sources.
#
# Usage:
#   ./scripts/enable_live_crawl.sh "https://YOUR-BUILDING-FLOORPLANS-URL"
#   ./scripts/enable_live_crawl.sh "https://..." the-hepburn-dc
#
# Env:
#   DATABASE_URL     default postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments
#   CRAWL_STRATEGY   playwright (default) | http
#   CRAWL_PARSER     next_data (default) | registry | generic_html
#   WAIT_SELECTOR    optional CSS selector for Playwright
#   DEACTIVATE_DEMO  true — set active=false on placeholder/demo sources
#   SKIP_CRAWL       true — only update DB + test_parse, no daily_run

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
SLUG="${2:-real-data-pilot-dc}"
DATABASE_URL="${DATABASE_URL:-postgresql://dmv_user:dmv_pass@localhost:5432/dmv_apartments}"
export DATABASE_URL
CRAWL_STRATEGY="${CRAWL_STRATEGY:-playwright}"
CRAWL_PARSER="${CRAWL_PARSER:-next_data}"
# Dominion / RentCafe floorplan pages (no __NEXT_DATA__):
#   CRAWL_PARSER=rentcafe_html CRAWL_STRATEGY=playwright ./scripts/enable_live_crawl.sh "https://www.dominionapts.com/floorplans/b1a"
DEACTIVATE_DEMO="${DEACTIVATE_DEMO:-false}"
SKIP_CRAWL="${SKIP_CRAWL:-false}"

if [[ -z "$URL" ]]; then
  echo "Usage: $0 <floorplans-or-availability-url> [building_slug]" >&2
  echo "Example: $0 'https://example-property.com/floorplans' real-data-pilot-dc" >&2
  exit 1
fi

if [[ "$URL" == *example.com* ]] || [[ "$URL" == *PLACEHOLDER* ]]; then
  echo "Error: replace with a real floorplans/availability URL (not example.com / PLACEHOLDER)." >&2
  exit 1
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

echo "==> Ensuring pilot building exists (safe to re-run)"
cat "$ROOT/sql/seed_real_data_pilot.sql" | psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q

echo "==> Updating source for slug: $SLUG"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q <<SQL
UPDATE buildings b
SET
  property_url = COALESCE(NULLIF(property_url, ''), '$URL'),
  metadata = b.metadata || '{"live_crawl": true}'::jsonb
WHERE b.slug = '$SLUG';

UPDATE sources s
SET
  url = '$URL',
  crawl_strategy = '$CRAWL_STRATEGY'::fetch_mode,
  wait_selector = NULLIF('${WAIT_SELECTOR:-}', ''),
  active = true,
  metadata = s.metadata || jsonb_build_object(
    'live_crawl_configured_at', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
  )
FROM buildings b
WHERE s.building_id = b.id AND b.slug = '$SLUG';
SQL

SOURCE_ID="$(psql "$DATABASE_URL" -t -A -c "
  SELECT s.id FROM sources s
  JOIN buildings b ON b.id = s.building_id
  WHERE b.slug = '$SLUG'
  ORDER BY s.created_at DESC NULLS LAST
  LIMIT 1;
")"
BUILDING_ID="$(psql "$DATABASE_URL" -t -A -c "SELECT id FROM buildings WHERE slug = '$SLUG' LIMIT 1;")"

if [[ -z "$SOURCE_ID" || -z "$BUILDING_ID" ]]; then
  echo "Error: could not resolve source/building for slug $SLUG" >&2
  exit 1
fi

echo "    building_id: $BUILDING_ID"
echo "    source_id:   $SOURCE_ID"

echo "==> test_parse (no DB write)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
PARSE_ARGS=(--url "$URL" --strategy "$CRAWL_STRATEGY" --parser "$CRAWL_PARSER")
if [[ -n "${WAIT_SELECTOR:-}" ]]; then
  PARSE_ARGS+=(--wait-selector "$WAIT_SELECTOR")
fi

PARSE_JSON="$("$PYTHON" -m crawler.test_parse "${PARSE_ARGS[@]}")"
LISTING_COUNT="$(echo "$PARSE_JSON" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('count',0))" 2>/dev/null || echo 0)"

echo "    listings extracted: $LISTING_COUNT"
if [[ "$LISTING_COUNT" == "0" ]]; then
  echo ""
  echo "Parse returned 0 listings. Fix URL/strategy/parser before crawling:"
  echo "$PARSE_JSON" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(d.get('zero_listings_help',[])))" 2>/dev/null || true
  exit 2
fi

if [[ "$SKIP_CRAWL" == "true" ]]; then
  echo "==> SKIP_CRAWL=true — done after test_parse"
  exit 0
fi

echo "==> daily_run --source-id $SOURCE_ID"
"$PYTHON" jobs/daily_run.py --source-id "$SOURCE_ID" --mode "$CRAWL_STRATEGY"

if [[ "$DEACTIVATE_DEMO" == "true" ]]; then
  echo "==> Deactivating placeholder/demo sources"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q <<'SQL'
UPDATE sources
WHERE url ILIKE '%example.com%'
   OR url ILIKE '%PLACEHOLDER%'
   OR url ILIKE '%replace-with%';
SQL
fi

echo ""
echo "==> Done. Verify:"
echo "    curl -s \"http://127.0.0.1:8000/search\" | head"
echo "    Open http://localhost:3000/search and find building slug: $SLUG"
echo "    Building page: http://localhost:3000/buildings/$BUILDING_ID"
