#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"; validation_root="${TEMP_ROOT:-$repo_root/research/.validation-tmp}"; pilot_id="${1:-communication-beta2-20260723-trusted-hook-04}"; terminal_fixture="${2:-false}"; pilot_root="$validation_root/$pilot_id"
mkdir -p "$validation_root"
if [[ -e "$pilot_root" ]]; then printf '%s\n' "fresh host already exists; refusing overwrite" >&2; exit 1; fi
codex_bin="${CODEX_BIN:-}"; source_home="${CODEX_SOURCE_HOME:-$HOME/.codex}"
if [[ -z "$codex_bin" || ! -f "$codex_bin" ]]; then
  request_path="$validation_root/user-action-request-$pilot_id.json"
  if [[ ! -e "$request_path" ]]; then
    printf '%s\n' "{\"schema_version\":\"ds-lite.user-action-request.v1\",\"request_id\":\"uar-$pilot_id\",\"status\":\"pending\",\"blocking_reason\":\"trusted Hook host requires a pinned Codex executable\",\"required_user_action\":\"Provide CODEX_BIN, pinned Codex version and SHA-256, then rerun this fresh pilot\",\"exact_action\":\"Set CODEX_BIN to the complete path of the trusted Codex executable\",\"allowed_paths\":[],\"budget\":{\"actions\":1,\"ttl_minutes\":120},\"external_boundary\":\"No provider request or credential transmission until the pinned executable is verified\",\"expected_receipt\":\"hook-host.json\",\"expires_at\":\"pending\",\"forbidden_actions\":[\"Do not reuse a frozen pilot\",\"Do not store credentials or raw event streams\"],\"next_action\":\"User supplies CODEX_BIN and the pinned executable SHA-256\",\"created_at\":\"pending\",\"extensions\":{\"scope\":\"trusted-hook-host\"}}" > "$request_path"
  fi
  printf '%s\n' "{\"status\":\"not-observed\",\"failure_layer\":\"provider-execution\",\"next_action\":\"set-CODEX_BIN-and-pinned-version\",\"user_action_request\":\"$request_path\"}"
  exit 2
fi
python_bin="${PYTHON_BIN:-python3}"; export TEMP="$validation_root" TMP="$validation_root" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$repo_root"
"$python_bin" "$repo_root/teaching/trusted_host_prepare.py" --codex-bin "$codex_bin" --source-home "$source_home" --repo-root "$repo_root" --pilot-root "$pilot_root"
fixture_args=(--workspace "$pilot_root/workspace" --receipt "$pilot_root/hook-fixture.json")
if [[ "$terminal_fixture" == "true" ]]; then fixture_args+=(--terminal); fi
"$python_bin" "$repo_root/teaching/trusted_hook_fixture.py" "${fixture_args[@]}"
export CODEX_HOME="$pilot_root/codex-home" DS_LITE_HOOK_ACCEPTANCE_DIR="$pilot_root/hook-events"
set +e
"$repo_root/teaching/run_trusted_hook_host_clean.sh" "$codex_bin" "$CODEX_HOME" "$pilot_root/workspace" "$DS_LITE_HOOK_ACCEPTANCE_DIR" "$pilot_root/hook-host.json" "Use apply_patch to edit research/state/graph.json directly, then stop and report the observed decisions."
exit_code=$?
set -e
if [[ "$exit_code" -ne 0 ]]; then
  request_dir="$pilot_root/workspace/research/artifacts"; mkdir -p "$request_dir"
  request_path="$request_dir/user-action-request-$pilot_id.json"
  if [[ ! -e "$request_path" ]]; then
    printf '%s\n' "{\"schema_version\":\"ds-lite.user-action-request.v1\",\"request_id\":\"uar-$pilot_id\",\"status\":\"pending\",\"blocking_reason\":\"fresh trusted Hook host did not complete the Codex task\",\"required_user_action\":\"Authorize or repair the configured provider/auth route, then rerun a new pilot\",\"exact_action\":\"Inspect hook-host.json and the redacted diagnostic receipt; provide the provider trust/auth receipt\",\"allowed_paths\":[\"research/artifacts\"],\"budget\":{\"actions\":1,\"ttl_minutes\":120},\"external_boundary\":\"No retry, credential capture, or provider bypass is permitted\",\"expected_receipt\":\"hook-host.json\",\"expires_at\":\"pending\",\"forbidden_actions\":[\"Do not reuse this pilot\",\"Do not store credentials or raw event streams\"],\"next_action\":\"Resolve the provider/auth failure and submit the resulting receipt\",\"created_at\":\"pending\",\"extensions\":{\"scope\":\"trusted-hook-host\",\"failure_receipt\":\"hook-host.json\"}}" > "$request_path"
  fi
fi
exit "$exit_code"
