#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
temp_root="${1:-${TEMP_ROOT:-$repo_root/research/.validation-tmp}}"
run_id="$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}"
run_temp="$temp_root/loop-acceptance-$run_id"
if ! mkdir -p "$run_temp"; then
  printf '%s\n' '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
  exit 2
fi
export TEMP="$run_temp" TMP="$run_temp" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$run_temp/pycache"
python_bin="${PYTHON_BIN:-python3}"
loop_cli="$repo_root/plugins/deepscientist-lite-core/scripts/ds_lite_loop.py"
loop_tests="$repo_root/tests/test_loop_runner.py"
offline_cli="$repo_root/teaching/offline_loop_acceptance.py"

"$python_bin" "$offline_cli" --output "$run_temp/offline-loop"

"$python_bin" -m unittest discover -s "$repo_root/tests" -p 'test_loop_runner.py' -v
"$python_bin" "$loop_cli" --help >/dev/null
"$python_bin" -m py_compile "$loop_cli" "$loop_tests"
printf '%s\n' '{"status":"passed","adapter":"fake","test_suite":"test_loop_runner.py","external_request_observed":false}'
