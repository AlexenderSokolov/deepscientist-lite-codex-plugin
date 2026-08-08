#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 6 ]]; then
  printf '%s\n' "usage: run_trusted_hook_host_clean.sh CODEX_BIN CODEX_HOME WORKSPACE HOOK_EVENTS OUTPUT PROMPT" >&2
  exit 2
fi
for value in "$1" "$2" "$3" "$4" "$5"; do
  if [[ "$value" == \<*\> ]]; then printf '%s\n' "placeholder path is not allowed" >&2; exit 2; fi
done
for value in "$1" "$2" "$3" "$4"; do
  [[ -e "$value" ]] || { printf '%s\n' "required host path does not exist" >&2; exit 2; }
done
python_bin="${PYTHON_BIN:-python3}"
export CODEX_HOME="$2" DS_LITE_HOOK_ACCEPTANCE_DIR="$4" PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
export PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd)"
expected_version="${CODEX_EXPECTED_VERSION:-0.144.5}"
expected_sha256="${CODEX_EXPECTED_SHA256:-EFDB3540EF74B9909408C8D38DA79483454797B36F471E3E004FC2BF2B70E22A}"
exec "$python_bin" -m teaching.trusted_hook_run --codex-bin "$1" --codex-home "$2" --workspace "$3" --hook-events "$4" --output "$5" --prompt "$6" --expected-version "$expected_version" --expected-sha256 "$expected_sha256"
