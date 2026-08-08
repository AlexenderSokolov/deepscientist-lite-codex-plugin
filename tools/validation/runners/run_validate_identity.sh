#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
: "${IDENTITY_OUTPUT:?IDENTITY_OUTPUT must point to a fresh receipt path}"
PYTHON="${PYTHON_BIN:-python3}"
TAG="$(cd "$ROOT" && "$PYTHON" -c 'import json, pathlib; print(json.loads((pathlib.Path("release") / "package-set.json").read_text(encoding="utf-8"))["target_tag"])')"
"$PYTHON" "$ROOT/tools/validation/package_identity_receipt.py" --source "$ROOT/plugins/deepscientist-lite-core" --tag "$TAG" --output "$IDENTITY_OUTPUT"
