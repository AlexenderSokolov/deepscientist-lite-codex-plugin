#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: run_transport_diagnostics.sh OUTPUT" >&2
  exit 2
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python 3.10+ was not found. Set PYTHON_BIN." >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/teaching/offline_acceptance.py" --output "$1"
