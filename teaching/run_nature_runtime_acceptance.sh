#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
script="$repo_root/teaching/nature_runtime_acceptance.py"
output="${1:-}"
test -f "$script"
if [[ "$output" == *"<"* || "$output" == *">"* ]]; then
  echo "output path contains a placeholder" >&2
  exit 2
fi
if [[ -z "$output" ]]; then
  run_id="$(date -u +%Y%m%dT%H%M%S)-$$-${RANDOM:-0}"
  output_root="${TEMP_ROOT:-$repo_root/research/.validation-tmp}/nature-runtime-$run_id"
  mkdir -p "$output_root"
  output="$output_root/receipt.json"
fi
exec "$python_bin" "$script" --repo-root "$repo_root" --output "$output"
