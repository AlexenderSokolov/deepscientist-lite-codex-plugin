#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"
schema_version="${FORMAL_GATE_SCHEMA_VERSION:-ds-lite.formal-release-gate.v2}"
exec "$python_bin" "$root/tools/validation/formal_release_gate.py" --schema-version "$schema_version" "$@"
