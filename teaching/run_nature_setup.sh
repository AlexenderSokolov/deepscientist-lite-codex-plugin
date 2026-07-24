#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-onboarding}"
workspace="${2:-.}"
case "$command_name" in
  inventory|doctor|onboarding|apply|verify) ;;
  *) echo "invalid nature setup command" >&2; exit 2 ;;
esac
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
script="$repo_root/plugins/deepscientist-lite/scripts/ds_lite_nature_setup.py"
test -f "$script"
workspace_path="$(cd "$workspace" && pwd)"
if [[ "$command_name" == "inventory" ]]; then
  exec "$python_bin" "$script" inventory
fi
exec "$python_bin" "$script" "$command_name" --workspace "$workspace_path"
