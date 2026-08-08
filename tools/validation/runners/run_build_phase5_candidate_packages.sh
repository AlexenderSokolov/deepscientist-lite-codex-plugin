#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'usage: %s WINDOWS_PACKAGE_ROOT LINUX_PACKAGE_ROOT EVIDENCE_ROOT\n' "$0" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WINDOWS_PACKAGE_ROOT="$1"
LINUX_PACKAGE_ROOT="$2"
EVIDENCE_ROOT="$3"
PYTHON_BIN="${PYTHON_BIN:-python3}"
for path in "$WINDOWS_PACKAGE_ROOT" "$LINUX_PACKAGE_ROOT" "$EVIDENCE_ROOT"; do
  if [[ -e "$path" ]]; then
    printf 'Phase 5 package output already exists\n' >&2
    exit 2
  fi
done
mkdir -p "$EVIDENCE_ROOT"
BUILDER="$ROOT/tools/validation/phase5_release_package_builder.py"
"$PYTHON_BIN" "$BUILDER" --repository "$ROOT" --output-root "$WINDOWS_PACKAGE_ROOT" --receipt "$EVIDENCE_ROOT/windows-package-build.json"
"$PYTHON_BIN" "$BUILDER" --repository "$ROOT" --output-root "$LINUX_PACKAGE_ROOT" --receipt "$EVIDENCE_ROOT/linux-package-build.json"
"$PYTHON_BIN" -c 'import json,sys; a=json.load(open(sys.argv[1],encoding="utf-8")); b=json.load(open(sys.argv[2],encoding="utf-8")); raise SystemExit(0 if a["package_digest"] == b["package_digest"] else 2)' "$EVIDENCE_ROOT/windows-package-build.json" "$EVIDENCE_ROOT/linux-package-build.json"
