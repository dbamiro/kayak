#!/usr/bin/env bash
# Local preflight for importing manually verified apartment specials.
#
# Usage:
#   TOKEN=<admin-jwt> ./scripts/check_real_data_ready.sh
#   ADMIN_EMAIL=ops@example.com ADMIN_PASSWORD='...' ./scripts/check_real_data_ready.sh
#   ./scripts/check_real_data_ready.sh path/to/file.real.csv

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

CSV_PATH="${1:-verified_specials.csv}"
API_URL="${API_URL:-http://127.0.0.1:8000}"
API_URL="${API_URL%/}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

echo "==> Kayak real-data import preflight"

if [[ "${SHOW_DEMO_DATA:-}" != "false" ]]; then
  fail "SHOW_DEMO_DATA must be exactly false in .env (or exported), then restart the API"
fi
pass "SHOW_DEMO_DATA=false"

curl -sf "$API_URL/health" >/dev/null \
  || fail "API is not reachable at $API_URL/health; start or restart it after changing .env"
pass "API reachable at $API_URL"

if [[ -n "${TOKEN:-}" ]]; then
  pass "admin TOKEN supplied"
elif [[ -n "${ADMIN_EMAIL:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
  pass "ADMIN_EMAIL and ADMIN_PASSWORD supplied"
else
  fail "pass TOKEN=<admin-jwt>, or ADMIN_EMAIL=<admin-email> and ADMIN_PASSWORD=<password>"
fi

[[ -f "$CSV_PATH" ]] || fail "$CSV_PATH does not exist; run: cp fixtures/incentives_import_template.csv verified_specials.csv"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi
[[ -n "$PYTHON_BIN" ]] || fail "python3 is required to validate the CSV"

CSV_PATH="$CSV_PATH" "$PYTHON_BIN" <<'PY'
import csv
import io
import os
import sys
from pathlib import Path

path = Path(os.environ["CSV_PATH"])
try:
    text = path.read_text(encoding="utf-8-sig")
except UnicodeDecodeError:
    print(f"FAIL: {path} must be UTF-8 CSV", file=sys.stderr)
    raise SystemExit(1)

lower = text.lower()
blocked = [
    marker
    for marker in ("example.com", "example.org", "example.net", "[example only]")
    if marker in lower
]
if blocked:
    print(f"FAIL: {path} contains blocked example marker(s): {', '.join(blocked)}", file=sys.stderr)
    raise SystemExit(1)

reader = csv.reader(io.StringIO(text))
rows = [row for row in reader if any(cell.strip() for cell in row)]
if not rows:
    print(f"FAIL: {path} is empty", file=sys.stderr)
    raise SystemExit(1)
if len(rows) < 2:
    print(f"FAIL: {path} has a header but no data rows", file=sys.stderr)
    raise SystemExit(1)

required = {"building_name", "source_url", "listed_rent", "lease_months"}
headers = {cell.strip().lower() for cell in rows[0]}
missing = sorted(required - headers)
if missing:
    print(f"FAIL: {path} is missing required columns: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(1)

print(f"OK: {path} has {len(rows) - 1} non-empty data row(s)")
print("OK: no blocked example domains or [EXAMPLE ONLY] markers")
PY

pass "preflight complete"
echo ""
echo "Next (no DB writes):"
echo "  ./scripts/import_incentives_csv.sh --dry-run \"$CSV_PATH\""
