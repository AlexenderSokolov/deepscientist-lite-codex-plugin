#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/bin:/bin:$PATH"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-}"
ARGS=(--lab evidence --mode student --case clean)
if [[ -n "$TARGET" ]]; then
  ARGS+=(--output "$TARGET")
fi

exec bash "$ROOT/teaching/run_lab.sh" "${ARGS[@]}"
