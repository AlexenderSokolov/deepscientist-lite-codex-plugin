#!/usr/bin/env bash
set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <fresh-output-directory>" >&2
  exit 1
fi

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

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT="$1"

"$PYTHON" "$SCRIPT_DIR/prepare_codex_acceptance.py" --repo-root "$REPO_ROOT" --output "$OUTPUT"

AUDIT_ARGS=(--root "$OUTPUT" --record "$OUTPUT/acceptance-audit.json")
if command -v codex >/dev/null 2>&1; then
  AUDIT_ARGS+=(--codex-bin "$(command -v codex)")
fi
"$PYTHON" "$SCRIPT_DIR/audit_codex_acceptance.py" "${AUDIT_ARGS[@]}"

echo "Package prepared and structurally audited. Installation still requires /plugins in a new Codex session."
