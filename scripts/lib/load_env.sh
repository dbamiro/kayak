#!/usr/bin/env bash
# Safely load KEY=VALUE pairs from a dotenv file without bash `source` pitfalls
# (unquoted parentheses, spaces, etc.).
#
# Usage (from another script):
#   ROOT="$(cd "$(dirname "$0")/.." && pwd)"
#   # shellcheck disable=SC1091
#   source "$ROOT/scripts/lib/load_env.sh"
#   load_dotenv_file "$ROOT/.env"

load_dotenv_file() {
  local env_file="${1:-.env}"
  local python="${PYTHON:-}"

  if [[ -z "$python" ]]; then
    local root="${ROOT:-}"
    if [[ -z "$root" ]]; then
      root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    fi
    if [[ -x "${root}/.venv/bin/python" ]]; then
      python="${root}/.venv/bin/python"
    else
      python="$(command -v python3 || true)"
    fi
  fi

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  if [[ -z "$python" ]]; then
    echo "ERROR: python3 not found; cannot load $env_file" >&2
    return 1
  fi

  local exports
  if ! exports="$(
    ENV_FILE="$env_file" "$python" <<'PY'
import os
import shlex
import sys
from pathlib import Path

try:
    from dotenv import dotenv_values
except ImportError:
    print(
        "ERROR: python-dotenv required to load .env on the host. "
        "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(1)

path = Path(os.environ["ENV_FILE"])
for key, value in dotenv_values(path).items():
    if value is None:
        continue
    if key in os.environ and os.environ[key]:
        continue
    print(f"export {key}={shlex.quote(value)}")
PY
  )"; then
    return 1
  fi

  if [[ -n "$exports" ]]; then
    # shellcheck disable=SC2046
    eval "$exports"
  fi
}
