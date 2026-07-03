#!/usr/bin/env bash
# Back-compat wrapper — use prod_smoke.sh for new deploys.
exec "$(cd "$(dirname "$0")" && pwd)/prod_smoke.sh" "$@"
