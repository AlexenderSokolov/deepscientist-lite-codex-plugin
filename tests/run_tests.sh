#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
temp_root="${TEMP_ROOT:-$repo_root/research/.validation-tmp}"
run_id="$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}"
run_temp="$temp_root/tests-$run_id"
mkdir -p "$run_temp"

# Keep every Python temporary file and bytecode cache on the project volume.
export TEMP="$run_temp" TMP="$run_temp" TEMP_ROOT="$run_temp" DS_LITE_TEST_ROOT="$run_temp"
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONPYCACHEPREFIX="$run_temp/pycache"

python_bin="${PYTHON_BIN:-python3}"
cd "$repo_root"
"$python_bin" tests/run_unittest.py
