#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_ROOT="${TEMP_ROOT:-$ROOT/research/.validation-tmp}"
mkdir -p "$TEMP_ROOT"
export TEMP="$TEMP_ROOT" TMP="$TEMP_ROOT" PYTHONPYCACHEPREFIX="$TEMP_ROOT/pycache"
ACTION="${1:-}"
if [[ -z "$ACTION" ]]; then
  echo "usage: run_pilot.sh prepare|install|preflight|canary|run|resume|score" >&2
  exit 2
fi
shift
case "$ACTION" in
  prepare|install|preflight|canary|run|resume|score) ;;
  *) echo "unknown action: $ACTION" >&2; exit 2 ;;
esac

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

WINDOWS_ROOT="${PILOT_WINDOWS_ROOT:-}"
WSL_ROOT="${PILOT_WSL_ROOT:-}"
PILOT_ID="${PILOT_ID:-}"
AUTHORIZATION_REF="${PILOT_AUTHORIZATION_REF:-}"
AUTHORIZED_RETRY_CALL="${PILOT_AUTHORIZED_RETRY_CALL:-}"
CODEX_BIN="${CODEX_BIN:-}"
WSL_BIN="${WSL_BIN:-wsl.exe}"

if [[ -z "$WINDOWS_ROOT" ]]; then
  echo "PILOT_WINDOWS_ROOT is required" >&2
  exit 2
fi
if [[ "$ACTION" =~ ^(prepare|preflight|run|resume|score)$ && -z "$WSL_ROOT" ]]; then
  echo "PILOT_WSL_ROOT is required for $ACTION" >&2
  exit 2
fi
if [[ "$ACTION" == "prepare" && ( -z "$PILOT_ID" || -z "$AUTHORIZATION_REF" ) ]]; then
  echo "PILOT_ID and PILOT_AUTHORIZATION_REF are required for prepare" >&2
  exit 2
fi
if [[ "$ACTION" =~ ^(preflight|canary|run|resume)$ && -z "$CODEX_BIN" ]]; then
  echo "CODEX_BIN is required for $ACTION" >&2
  exit 2
fi

if [[ "$ACTION" == "score" ]]; then
  exec "$PYTHON" "$ROOT/teaching/pilot_score.py" score \
    --windows-root "$WINDOWS_ROOT" --wsl-root "$WSL_ROOT" "$@"
fi

ARGS=("$ROOT/teaching/pilot_runtime.py" "$ACTION" --windows-root "$WINDOWS_ROOT")
if [[ "$ACTION" == "prepare" || "$ACTION" == "preflight" || "$ACTION" == "run" || "$ACTION" == "resume" ]]; then
  ARGS+=(--wsl-root "$WSL_ROOT")
fi
if [[ "$ACTION" == "prepare" ]]; then
  ARGS+=(--pilot-id "$PILOT_ID" --authorization-ref "$AUTHORIZATION_REF")
fi
if [[ "$ACTION" == "preflight" || "$ACTION" == "canary" || "$ACTION" == "run" || "$ACTION" == "resume" ]]; then
  ARGS+=(--codex-bin "$CODEX_BIN")
fi
if [[ "$ACTION" == "preflight" ]]; then
  ARGS+=(--wsl-bin "$WSL_BIN")
fi
if [[ "$ACTION" == "canary" ]]; then
  ARGS+=(--timeout-seconds "${PILOT_TIMEOUT_SECONDS:-180}")
elif [[ "$ACTION" == "run" || "$ACTION" == "resume" ]]; then
  ARGS+=(--timeout-seconds "${PILOT_TIMEOUT_SECONDS:-900}")
fi
if [[ "$ACTION" == "resume" && -n "$AUTHORIZED_RETRY_CALL" ]]; then
  if [[ -z "$AUTHORIZATION_REF" ]]; then
    echo "PILOT_AUTHORIZATION_REF is required for an authorized retry" >&2
    exit 2
  fi
  ARGS+=(--authorized-retry-call "$AUTHORIZED_RETRY_CALL" --authorization-ref "$AUTHORIZATION_REF")
fi
exec "$PYTHON" "${ARGS[@]}" "$@"
