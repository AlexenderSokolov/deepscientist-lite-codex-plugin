#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$$(cd -- "$$(dirname -- "$${BASH_SOURCE[0]}")" && pwd)"
export DS_LITE_PROJECT_ROOT="$$SCRIPT_DIR"
# shellcheck source=tools/ds_lite_runtime.sh
source "$$SCRIPT_DIR/tools/ds_lite_runtime.sh"

PYTHON="$$(ds_lite_python)"
AUTONOMY_CLI="$$(ds_lite_cli autonomy)"
ARGS=(--root "$$DS_LITE_PROJECT_ROOT" --contract "$$DS_LITE_PROJECT_ROOT/research/autonomy/contract.json" --output "$$DS_LITE_PROJECT_ROOT/research/autonomy/run")
if [[ "$${1:-}" == "--resume" ]]; then
  ARGS+=(--resume)
  shift
fi
if [[ $$# -ne 0 ]]; then
  echo "Usage: bash run_autonomy.sh [--resume]" >&2
  exit 2
fi

exec "$$PYTHON" "$$AUTONOMY_CLI" "$${ARGS[@]}"
