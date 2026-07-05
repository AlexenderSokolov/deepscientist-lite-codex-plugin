#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$$(cd -- "$$(dirname -- "$${BASH_SOURCE[0]}")" && pwd)"
export DS_LITE_PROJECT_ROOT="$$SCRIPT_DIR"
# shellcheck source=tools/ds_lite_runtime.sh
source "$$SCRIPT_DIR/tools/ds_lite_runtime.sh"

PYTHON="$$(ds_lite_python)"
STATE_CLI="$$(ds_lite_cli state)"
ARGS=(trace --root "$$DS_LITE_PROJECT_ROOT" --mode progression --format markdown)
if [[ $$# -gt 1 ]]; then
  echo "Usage: bash run_analysis.sh [node-id]" >&2
  exit 2
fi
if [[ $$# -eq 1 ]]; then
  ARGS+=(--node "$$1")
fi
exec "$$PYTHON" "$$STATE_CLI" "$${ARGS[@]}"
