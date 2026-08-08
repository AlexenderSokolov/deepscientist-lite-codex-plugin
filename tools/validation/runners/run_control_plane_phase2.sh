#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
python_bin="${PYTHON_BIN:?set PYTHON_BIN to verified Python 3.13.5}"
dependency_root="${DBOS_DEPENDENCY_ROOT:?set DBOS_DEPENDENCY_ROOT to locked DBOS 2.29.0 root}"
evidence_root="${EVIDENCE_ROOT:?set EVIDENCE_ROOT to a new repository-local directory}"
codex_bin="${CODEX_BIN:?set CODEX_BIN to pinned Codex 0.128.0 binary}"
case "$evidence_root" in /*) ;; *) evidence_root="$root/$evidence_root" ;; esac
case "$evidence_root" in "$root"/*) ;; *) echo "EVIDENCE_ROOT must stay inside repository" >&2; exit 2 ;; esac
[[ ! -e "$evidence_root" ]] || { echo "EVIDENCE_ROOT already exists" >&2; exit 2; }
[[ "$($python_bin -c 'import platform; print(platform.python_version())')" == "3.13.5" ]] || { echo "Python 3.13.5 required" >&2; exit 2; }
[[ -d "$dependency_root/dbos-2.29.0.dist-info" ]] || { echo "DBOS 2.29.0 dependency root required" >&2; exit 2; }
[[ -x "$codex_bin" ]] || { echo "pinned Codex app-server binary required" >&2; exit 2; }
mkdir -p "$evidence_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$dependency_root:$root/plugins/deepscientist-lite-control-plane/controller${PYTHONPATH:+:$PYTHONPATH}"
"$python_bin" "$root/plugins/deepscientist-lite-control-plane/controller/phase2_fault_harness.py" --workdir "$evidence_root/fault-work" --output "$evidence_root/fault-matrix.json" --seed 20260731 --trials 100
set +e
"$python_bin" -m unittest tests.test_control_plane_phase2 tests.test_control_plane_phase2_app_server tests.test_control_plane_phase2_runner tests.test_control_plane_phase2_fault_harness tests.test_control_plane_phase1 tests.test_control_plane_phase1_cli -v >"$evidence_root/phase-tests.txt" 2>&1
phase_exit=$?
"$python_bin" teaching/controller_app_server_smoke.py --codex-bin "$codex_bin" --home "$evidence_root/codex-home" --workspace "$root" --schema-root "$root/plugins/deepscientist-lite-control-plane/schemas/codex/0.128.0" --output "$evidence_root/canonical-thread-smoke.json"
smoke_exit=$?
"$python_bin" -m teaching.control_plane_phase2_evidence managed --project "$evidence_root/managed-project" --backup "$evidence_root/managed-backup" --restore "$evidence_root/managed-restore" --output "$evidence_root/managed-probe.json"
managed_exit=$?
"$python_bin" -m ds_lite_control doctor --project "$evidence_root/managed-project" >"$evidence_root/doctor.txt" 2>&1
doctor_exit=$?
PYTHON_BIN="$python_bin" bash "$root/tools/validation/runners/run_validate_core.sh" --output "$evidence_root/core-validation.json"
core_exit=$?
"$python_bin" -c "import ast; from pathlib import Path; files=list(Path(r'$root/plugins/deepscientist-lite-control-plane/controller/ds_lite_control').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print('AST_OK', len(files))"
compile_exit=$?
set -e
"$python_bin" - "$evidence_root/run-summary.json" "$phase_exit" "$smoke_exit" "$managed_exit" "$doctor_exit" "$core_exit" "$compile_exit" <<'PY'
import json, sys
out, phase, smoke, managed, doctor, core, compile_ = sys.argv[1:]
with open(out, "x", encoding="utf-8") as handle:
    json.dump({"schema_version":"ds-lite.phase2-runner.v1","phase":"2","phase_tests_exit":int(phase),"canonical_smoke_exit":int(smoke),"managed_exit":int(managed),"doctor_exit":int(doctor),"core_exit":int(core),"compile_exit":int(compile_),"release_allowed":False}, handle, indent=2)
    handle.write("\n")
PY
"$python_bin" -m teaching.control_plane_phase2_evidence decision --fault "$evidence_root/fault-matrix.json" --smoke "$evidence_root/canonical-thread-smoke.json" --managed "$evidence_root/managed-probe.json" --tests "$evidence_root/phase-tests.txt" --core "$evidence_root/core-validation.json" --output "$evidence_root/phase2-decision.json"
(( phase_exit == 0 && smoke_exit == 0 && managed_exit == 0 && doctor_exit == 0 && core_exit == 0 && compile_exit == 0 ))
