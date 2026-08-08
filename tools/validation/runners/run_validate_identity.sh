#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
: "${IDENTITY_OUTPUT:?IDENTITY_OUTPUT must point to a fresh receipt path}"
"${PYTHON_BIN:-python3}" "$ROOT/tools/validation/package_identity_receipt.py" --source "$ROOT/plugins/deepscientist-lite-core" --tag "v0.10.0-beta.2" --output "$IDENTITY_OUTPUT"
