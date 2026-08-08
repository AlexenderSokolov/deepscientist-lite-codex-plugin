#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
for candidate in "${PYTHON_BIN:-}" python3 python; do
  [[ -n "$candidate" ]] || continue
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" "$repo_root/tools/validation/validate_all.py" --repo-root "$repo_root" "$@"
  fi
done
echo "Python was not found. Set PYTHON_BIN to a supported interpreter." >&2
exit 1
