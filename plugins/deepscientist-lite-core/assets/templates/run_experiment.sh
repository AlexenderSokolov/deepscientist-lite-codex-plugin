#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$$(cd -- "$$(dirname -- "$${BASH_SOURCE[0]}")" && pwd)"
export DS_LITE_PROJECT_ROOT="$$SCRIPT_DIR"
# shellcheck source=tools/ds_lite_runtime.sh
source "$$SCRIPT_DIR/tools/ds_lite_runtime.sh"

if [[ $$# -lt 1 ]]; then
  echo "Usage: bash run_experiment.sh <init|finalize|verify> [Evidence Pack arguments]" >&2
  echo "Example: bash run_experiment.sh verify --run-id <run-id> --strict" >&2
  exit 2
fi

PYTHON="$$(ds_lite_python)"
EVIDENCE_CLI="$$(ds_lite_cli evidence)"
COMMAND="$$1"
shift
exec "$$PYTHON" "$$EVIDENCE_CLI" "$$COMMAND" --root "$$DS_LITE_PROJECT_ROOT" "$$@"
