#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"
temp_root="${TEMP_ROOT:-$root/research/.validation-tmp}"
run_temp="$temp_root/web-validation-$$"
if ! mkdir -p "$run_temp"; then
  printf '%s\n' '{"status":"not-observed","failure_layer":"environment-write","next_action":"set-authorized-temp-root"}'
  exit 2
fi
export TEMP="$run_temp" TMP="$run_temp" PYTHONPYCACHEPREFIX="$run_temp/pycache"
export PYTHONDONTWRITEBYTECODE=1
"$python_bin" -m unittest discover -s "$root/tests" -p 'test_extension_protocols.py' -v
"$python_bin" -m py_compile "$root/plugins/deepscientist-lite-web/scripts/ds_lite_extensions.py"
exec "$python_bin" "$root/tools/validation/validate_packages.py" --repo-root "$root" --package web "$@"
