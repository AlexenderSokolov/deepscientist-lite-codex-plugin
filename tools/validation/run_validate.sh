#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python 3.10+ was not found. Set PYTHON_BIN to the interpreter path." >&2
  exit 1
fi

"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" tools/validation/validate_repo.py
"$PYTHON" -m py_compile \
  plugins/deepscientist-lite/scripts/ds_lite_evidence.py \
  plugins/deepscientist-lite/scripts/ds_lite_state.py \
  teaching/lab_runner.py \
  tools/validation/validate_repo.py \
  tests/test_evidence_pack.py \
  tests/test_state_kernel.py \
  tests/test_teaching_labs.py
