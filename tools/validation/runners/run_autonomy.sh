#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
exec "$python_bin" "$root/plugins/deepscientist-lite-core/scripts/ds_lite_autonomy.py" "$@"
