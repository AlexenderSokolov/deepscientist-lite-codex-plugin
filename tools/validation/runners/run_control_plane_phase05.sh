#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
codex_bin="${CODEX_BIN:?set CODEX_BIN to the pinned Codex 0.128.0 executable}"
source_home="${SOURCE_CODEX_HOME:-$HOME/.codex}"
dependency_root="${DBOS_DEPENDENCY_ROOT:?set DBOS_DEPENDENCY_ROOT to the locked DBOS 2.29.0 target}"
evidence_root="${EVIDENCE_ROOT:?set EVIDENCE_ROOT to a new write-once directory}"

case "$evidence_root" in
  /*) ;;
  *) evidence_root="$root/$evidence_root" ;;
esac
if [[ -e "$evidence_root" ]]; then
  printf '%s\n' "EVIDENCE_ROOT already exists; refusing overwrite" >&2
  exit 2
fi
case "$evidence_root" in
  "$root"/*) ;;
  *) printf '%s\n' "EVIDENCE_ROOT must stay inside the repository" >&2; exit 2 ;;
esac
if [[ "$($codex_bin --version)" != "codex-cli 0.128.0" ]]; then
  printf '%s\n' "CODEX_BIN must report codex-cli 0.128.0" >&2
  exit 2
fi
if [[ ! -d "$dependency_root" || ! -f "$source_home/config.toml" || -z "${OPENAI_API_KEY:-}" ]]; then
  printf '%s\n' "locked dependency root, source config, and provider environment are required" >&2
  exit 2
fi

mkdir -p "$evidence_root"
schema_root="$root/plugins/deepscientist-lite-control-plane/schemas/codex/0.128.0"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$dependency_root${PYTHONPATH:+:$PYTHONPATH}"

"$python_bin" "$root/teaching/canonical_thread_smoke.py" \
  --codex-bin "$codex_bin" --home "$evidence_root/canonical-home" --workspace "$root" \
  --schema-root "$schema_root" --output "$evidence_root/canonical-thread.json"
"$python_bin" -m teaching.hook_in_turn_repair_smoke \
  --codex-bin "$codex_bin" --home "$evidence_root/hook-home" --workspace "$evidence_root/hook-workspace" \
  --schema-root "$schema_root" --marketplace-root "$root" --source-home "$source_home" \
  --output "$evidence_root/hook-in-turn-repair.json"
"$python_bin" "$root/teaching/dbos_sqlite_recovery_probe.py" \
  --dependency-root "$dependency_root" --python-bin "$python_bin" \
  --workdir "$evidence_root/dbos-work" --output "$evidence_root/dbos-sqlite-recovery.json" \
  --action-id "phase05-$(date -u +%Y%m%dT%H%M%SZ)"
(cd "$root/plugins/deepscientist-lite-control-plane/controller" && \
  "$python_bin" run_spike.py --dependency-root "$dependency_root" --seed 20260731 --trials 100 \
    --output "$evidence_root/fault-harness.json")
"$python_bin" "$root/plugins/deepscientist-lite-control-plane/controller/resource_probe.py" \
  --dependency-root "$dependency_root" --output "$evidence_root/resource-probe.json"
(cd "$root" && "$python_bin" -m teaching.control_plane_phase_tests --output "$evidence_root/phase-tests.json")
PYTHON_BIN="$python_bin" bash "$root/tools/validation/runners/run_validate_core.sh" --output "$evidence_root/core-validation.json"
(cd "$root" && "$python_bin" -m teaching.control_plane_spike_decision \
  --repo-root "$root" --evidence-root "$evidence_root" --output "$evidence_root/spike-decision.json" \
  --canonical "$evidence_root/canonical-thread.json" --hook "$evidence_root/hook-in-turn-repair.json" \
  --dbos "$evidence_root/dbos-sqlite-recovery.json" --fault "$evidence_root/fault-harness.json" \
  --resource "$evidence_root/resource-probe.json" --phase-tests "$evidence_root/phase-tests.json" \
  --core "$evidence_root/core-validation.json")
