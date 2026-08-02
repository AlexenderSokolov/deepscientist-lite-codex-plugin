#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$$(cd -- "$$(dirname -- "$${BASH_SOURCE[0]}")" && pwd)"
export DS_LITE_PROJECT_ROOT="$$SCRIPT_DIR"
# shellcheck source=tools/ds_lite_runtime.sh
source "$$SCRIPT_DIR/tools/ds_lite_runtime.sh"

if [[ $$# -ne 1 ]]; then
  echo "Usage: bash run_review.sh <run-id>" >&2
  exit 2
fi

PYTHON="$$(ds_lite_python)"
EVIDENCE_CLI="$$(ds_lite_cli evidence)"
exec "$$PYTHON" "$$EVIDENCE_CLI" verify --root "$$DS_LITE_PROJECT_ROOT" --run-id "$$1" --strict
