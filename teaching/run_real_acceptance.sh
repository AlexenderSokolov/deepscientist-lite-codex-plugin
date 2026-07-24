#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: run_real_acceptance.sh prepare|preflight|network|responses [arguments...]" >&2
  exit 2
fi

ACTION="$1"
shift
case "$ACTION" in
  prepare|preflight|network|responses) ;;
  *)
    echo "unsupported action: $ACTION" >&2
    exit 2
    ;;
esac

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  PYTHON="python"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
"$PYTHON" "$SCRIPT_DIR/real_acceptance.py" "$ACTION" "$@"
