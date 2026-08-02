#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
temp_root="${1:-${TEMP_ROOT:-$repo_root/research/.validation-tmp}}"
receipt_id="$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}"
run_temp="$temp_root/cross-system-$receipt_id"
if ! mkdir -p "$run_temp"; then
  printf '%s\n' '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
  exit 2
fi
export TEMP="$run_temp" TMP="$run_temp" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$run_temp/pycache"
python_bin="${PYTHON_BIN:-python3}"
receipt_path="$run_temp/cross-system-validation-$receipt_id.json"
"$python_bin" "$repo_root/tools/validation/check_cross_system.py" "$repo_root" --output "$receipt_path"
bash -n "$repo_root/teaching/run_trusted_hook_host_clean.sh"
"$python_bin" -m unittest discover -s "$repo_root/tests" -p 'test_cli_compatibility.py' -v
"$python_bin" -m unittest discover -s "$repo_root/tests" -p 'test_text_compatibility.py' -v
printf '%s\n' "cross-system validation completed: $(basename "$receipt_path")"
