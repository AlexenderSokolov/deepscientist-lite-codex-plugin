#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

PYTHON=""
if [[ -n "${PYTHON_BIN:-}" ]]; then
  CANDIDATES=("$PYTHON_BIN")
else
  CANDIDATES=(python3 python)
fi

for candidate in "${CANDIDATES[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "Python 3.10+ was not found. Set PYTHON_BIN to the interpreter path." >&2
  exit 1
fi

"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" tools/validation/validate_repo.py
"$PYTHON" -m py_compile \
  plugins/deepscientist-lite/scripts/ds_lite_evidence.py \
  plugins/deepscientist-lite/scripts/ds_lite_protocol.py \
  plugins/deepscientist-lite/scripts/ds_lite_state.py \
  teaching/lab_runner.py \
  tools/validation/prepare_codex_acceptance.py \
  tools/validation/audit_codex_acceptance.py \
  tools/validation/validate_repo.py \
  tests/test_acceptance_tools.py \
  tests/test_evidence_pack.py \
  tests/test_protocols.py \
  tests/test_state_kernel.py \
  tests/test_teaching_labs.py
