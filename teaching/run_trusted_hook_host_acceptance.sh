#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"; validation_root="$repo_root/.validation-tmp"; pilot_id="${1:-communication-beta2-20260723-trusted-hook-04}"; pilot_root="$validation_root/$pilot_id"
if [[ -e "$pilot_root" ]]; then printf '%s\n' "fresh host already exists; refusing overwrite" >&2; exit 1; fi
codex_bin="${CODEX_BIN:-}"; source_home="${CODEX_SOURCE_HOME:-$HOME/.codex}"
if [[ -z "$codex_bin" || ! -f "$codex_bin" ]]; then printf '%s\n' "set CODEX_BIN to pinned Codex 0.144.5" >&2; exit 2; fi
python_bin="${PYTHON_BIN:-python3}"; export TEMP="$validation_root" TMP="$validation_root" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$repo_root"
"$python_bin" "$repo_root/teaching/trusted_host_prepare.py" --codex-bin "$codex_bin" --source-home "$source_home" --repo-root "$repo_root" --pilot-root "$pilot_root"
"$python_bin" "$repo_root/teaching/trusted_hook_fixture.py" --workspace "$pilot_root/workspace" --receipt "$pilot_root/hook-fixture.json"
export CODEX_HOME="$pilot_root/codex-home" DS_LITE_HOOK_ACCEPTANCE_DIR="$pilot_root/hook-events"
exec "$repo_root/teaching/run_trusted_hook_host_clean.sh" "$codex_bin" "$CODEX_HOME" "$pilot_root/workspace" "$DS_LITE_HOOK_ACCEPTANCE_DIR" "$pilot_root/hook-host.json" "Use apply_patch to edit research/state/graph.json directly, then stop and report the observed decisions."
