#!/usr/bin/env bash
# Start the Kayak API on :8000 (loads .env from repo root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
# app.config loads .env via pydantic-settings when uvicorn imports the app
exec ./.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
