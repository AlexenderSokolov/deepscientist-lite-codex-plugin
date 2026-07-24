#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-verify}"
output="${2:-}"
case "$command_name" in
  inventory|check|diff|plan-update|verify) ;;
  *) echo "invalid upstream audit command" >&2; exit 2 ;;
esac
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
args=("$repo_root/tools/validation/upstream_manager.py" "$command_name" --repo-root "$repo_root")
if [[ -n "$output" ]]; then args+=(--output "$output"); fi
exec "$python_bin" "${args[@]}"
