#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" "$ROOT/tools/validation/validate_packages.py" --package control-plane
"$PYTHON_BIN" -m unittest discover -s "$ROOT/tests" -p 'test_control_plane*.py' -v
