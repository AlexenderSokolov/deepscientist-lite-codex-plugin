#!/usr/bin/env bash
# Shared runtime resolution for DeepScientist Lite project scripts.
# This file is generated with the project. Keep machine-specific paths in
# environment variables, never in the saved script.

ds_lite_error() {
  echo "DS Lite runtime error: $$*" >&2
  return 1
}

ds_lite_project_root() {
  if [[ -z "$${DS_LITE_PROJECT_ROOT:-}" ]]; then
    ds_lite_error "DS_LITE_PROJECT_ROOT was not initialized by the calling script."
    return 1
  fi
  printf '%s\n' "$$DS_LITE_PROJECT_ROOT"
}

ds_lite_python() {
  local candidate=""
  if [[ -n "$${PYTHON_BIN:-}" ]]; then
    candidate="$$PYTHON_BIN"
  elif command -v python3 >/dev/null 2>&1; then
    candidate="python3"
  elif command -v python >/dev/null 2>&1; then
    candidate="python"
  else
    ds_lite_error "Python 3.10+ was not found. Set PYTHON_BIN to a usable interpreter."
    return 1
  fi

  if ! "$$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    ds_lite_error "Python 3.10+ is required; PYTHON_BIN resolved to: $$candidate"
    return 1
  fi
  printf '%s\n' "$$candidate"
}

ds_lite_cli() {
  local kind="$${1:-}"
  local explicit=""
  local script_name=""
  local env_label=""
  case "$$kind" in
    state)
      explicit="$${DS_LITE_STATE_CLI:-}"
      script_name="ds_lite_state.py"
      env_label="DS_LITE_STATE_CLI"
      ;;
    evidence)
      explicit="$${DS_LITE_EVIDENCE_CLI:-}"
      script_name="ds_lite_evidence.py"
      env_label="DS_LITE_EVIDENCE_CLI"
      ;;
    *)
      ds_lite_error "unknown CLI kind: $$kind"
      return 1
      ;;
  esac

  local candidate="$$explicit"
  if [[ -z "$$candidate" && -n "$${DS_LITE_PLUGIN_ROOT:-}" ]]; then
    candidate="$${DS_LITE_PLUGIN_ROOT%/}/scripts/$$script_name"
  fi
  if [[ -z "$$candidate" ]]; then
    ds_lite_error "Set $$env_label or DS_LITE_PLUGIN_ROOT before running this script."
    return 1
  fi

  case "$$candidate" in
    /*|[A-Za-z]:[\\/]*) ;;
    *) candidate="$$DS_LITE_PROJECT_ROOT/$$candidate" ;;
  esac
  if [[ ! -f "$$candidate" ]]; then
    ds_lite_error "resolved $$kind CLI does not exist: $$candidate"
    return 1
  fi
  printf '%s\n' "$$candidate"
}
