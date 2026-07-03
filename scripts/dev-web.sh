#!/usr/bin/env bash
# Start the Kayak Next.js app on :3000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web"
if [[ ! -f .env.local ]] && [[ -f .env.local.example ]]; then
  echo "Creating web/.env.local from .env.local.example"
  cp .env.local.example .env.local
fi
exec npm run dev
