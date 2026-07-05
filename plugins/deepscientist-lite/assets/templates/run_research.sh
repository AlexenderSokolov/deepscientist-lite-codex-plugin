#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$$(cd -- "$$(dirname -- "$${BASH_SOURCE[0]}")" && pwd)"
export DS_LITE_PROJECT_ROOT="$$SCRIPT_DIR"
# shellcheck source=tools/ds_lite_runtime.sh
source "$$SCRIPT_DIR/tools/ds_lite_runtime.sh"

PYTHON="$$(ds_lite_python)"
STATE_CLI="$$(ds_lite_cli state)"
COMMAND="$${1:-status}"
if [[ $$# -gt 0 ]]; then
  shift
fi

# Examples:
#   bash run_research.sh status --json
#   bash run_research.sh validate --strict
exec "$$PYTHON" "$$STATE_CLI" "$$COMMAND" --root "$$DS_LITE_PROJECT_ROOT" "$$@"
