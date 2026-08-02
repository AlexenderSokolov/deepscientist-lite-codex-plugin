#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
output_root="${TEMP_ROOT:-$repo_root/research/.validation-tmp/codex-pin-$$}"
exec "$python_bin" "$repo_root/tools/validation/acquire_pinned_codex.py" --output-root "$output_root"
