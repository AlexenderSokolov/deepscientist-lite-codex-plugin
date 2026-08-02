#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:?set PYTHON_BIN to the verified Python 3.13.5 executable}"
dependency_root="${DBOS_DEPENDENCY_ROOT:?set DBOS_DEPENDENCY_ROOT to the locked DBOS 2.29.0 target}"
evidence_root="${EVIDENCE_ROOT:?set EVIDENCE_ROOT to a new repository-local directory}"

case "$evidence_root" in /*) ;; *) evidence_root="$root/$evidence_root" ;; esac
case "$evidence_root" in "$root"/*) ;; *) echo "EVIDENCE_ROOT must stay inside the repository" >&2; exit 2 ;; esac
if [[ -e "$evidence_root" ]]; then echo "EVIDENCE_ROOT already exists" >&2; exit 2; fi
if [[ "$($python_bin -c 'import platform; print(platform.python_version())')" != "3.13.5" ]]; then
  echo "Phase 1 managed verification requires Python 3.13.5" >&2; exit 2
fi
if [[ ! -d "$dependency_root/dbos-2.29.0.dist-info" ]]; then
  echo "locked DBOS 2.29.0 dependency root is required" >&2; exit 2
fi

mkdir -p "$evidence_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$dependency_root:$root/plugins/deepscientist-lite-core/controller${PYTHONPATH:+:$PYTHONPATH}"

"$python_bin" "$root/plugins/deepscientist-lite-core/controller/phase1_fault_harness.py" \
  --dependency-root "$dependency_root" --python-bin "$python_bin" \
  --workdir "$evidence_root/fault-work" --output "$evidence_root/fault-matrix.json" \
  --seed 20260731 --trials 100
"$python_bin" -m teaching.control_plane_phase1_evidence probe \
  --dependency-root "$dependency_root" --python-bin "$python_bin" \
  --project "$evidence_root/managed-project" --backup "$evidence_root/managed-backup" \
  --restore "$evidence_root/managed-restore" --output "$evidence_root/managed-probe.json"
"$python_bin" -m teaching.control_plane_phase1_evidence tests \
  --python-bin "$python_bin" --output "$evidence_root/phase-tests.json"
PYTHON_BIN="$python_bin" bash "$root/tools/validation/runners/run_validate_core.sh" --output "$evidence_root/core-validation.json"
"$python_bin" -m teaching.control_plane_phase1_evidence decision \
  --fault "$evidence_root/fault-matrix.json" --managed "$evidence_root/managed-probe.json" \
  --tests "$evidence_root/phase-tests.json" --core "$evidence_root/core-validation.json" \
  --output "$evidence_root/phase1-decision.json"
