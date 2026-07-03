#!/usr/bin/env bash
# Cron-friendly wrapper for Kayak scheduled jobs (no web server required).
#
# Usage:
#   ./scripts/run_scheduled_jobs.sh                    # expire Hunt Pass entitlements (required daily)
#   ./scripts/run_scheduled_jobs.sh --expire-pending   # + stale pending_review incentives
#   ./scripts/run_scheduled_jobs.sh --crawl            # + daily crawl if ENABLE_DAILY_CRAWL=true
#   ./scripts/run_scheduled_jobs.sh --all              # entitlements + pending + crawl

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/load_env.sh"
load_dotenv_file "$ROOT/.env"

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

ARGS=()
RUN_PENDING=false
RUN_CRAWL=false

for arg in "$@"; do
  case "$arg" in
    --expire-pending) RUN_PENDING=true ;;
    --crawl) RUN_CRAWL=true ;;
    --all)
      RUN_PENDING=true
      RUN_CRAWL=true
      ;;
    *)
      echo "Unknown arg: $arg (use --expire-pending, --crawl, or --all)" >&2
      exit 2
      ;;
  esac
done

if [[ "$RUN_PENDING" == "true" ]]; then
  ARGS+=(--expire-pending)
fi
if [[ "$RUN_CRAWL" == "true" ]]; then
  ARGS+=(--crawl --crawl-limit "${CRAWL_LIMIT:-20}")
fi

exec "$PYTHON" -m jobs.run_scheduled "${ARGS[@]}"
