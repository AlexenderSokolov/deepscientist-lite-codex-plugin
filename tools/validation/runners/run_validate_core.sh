#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
exec "$python_bin" "$root/tools/validation/validate_packages.py" --repo-root "$root" --package core "$@"
