#!/usr/bin/env bash
set -u
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$repo_root"
evidence_root="${1:?usage: run_control_plane_phase3.sh EVIDENCE_ROOT DBOS_ROOT CODEX_BIN [PYTHON_BIN]}"
dbos_root="${2:?DBOS_ROOT required}"
codex_bin="${3:?CODEX_BIN required}"
python_bin="${4:-/opt/anaconda3/bin/python}"
model="${MODEL:-gpt-5.6-sol}"
codex_version="${CODEX_VERSION:-0.146.0-alpha.3.1}"
ambient_home="${AMBIENT_HOME:-0}"
case "$(cd "$(dirname "$evidence_root")" 2>/dev/null && pwd)/$(basename "$evidence_root")" in "$repo_root"/*) ;; *) echo "evidence root must be inside repository" >&2; exit 2;; esac
[[ ! -e "$evidence_root" ]] || { echo "evidence root already exists" >&2; exit 2; }
[[ "$($python_bin -c 'import platform; print(platform.python_version())')" == "3.13.5" ]] || { echo "Python 3.13.5 required" >&2; exit 2; }
[[ "$($codex_bin --version)" == "codex-cli $codex_version" ]] || { echo "Codex $codex_version required" >&2; exit 2; }
mkdir "$evidence_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$dbos_root:$repo_root/plugins/deepscientist-lite-control-plane/controller:$repo_root${PYTHONPATH:+:$PYTHONPATH}"
schema_root="$repo_root/plugins/deepscientist-lite-control-plane/schemas/codex/$codex_version"
previous="$repo_root/research/.validation-tmp/control-plane-phase2-continuation-20260731-06/phase2-decision-03.json"

fault_exit=0; "$python_bin" "$repo_root/plugins/deepscientist-lite-control-plane/controller/phase3_fault_harness.py" --workdir "$evidence_root/fault-work" --output "$evidence_root/fault-matrix.json" --python-bin "$python_bin" --dependency-root "$dbos_root" --seed 20260731 --trials 100 --timeout 20 || fault_exit=$?
supervised_exit=0; "$python_bin" -m teaching.control_plane_phase3_evidence supervised --project "$evidence_root/managed-project" --runtime "$evidence_root/managed-runtime" --output "$evidence_root/supervised-recovery.json" || supervised_exit=$?
resource_exit=0; "$python_bin" -m teaching.control_plane_phase3_evidence resource --output "$evidence_root/resource-windows.json" || resource_exit=$?
real_args=("$repo_root/teaching/controller_phase3_multigate_smoke.py" --codex-bin "$codex_bin" --codex-version "$codex_version" --schema-root "$schema_root" --task-workspace "$evidence_root/real-workspace" --runtime "$evidence_root/real-runtime" --output "$evidence_root/real-multigate-smoke.json" --journal-summary "$evidence_root/broker-journal-summary.json" --model "$model")
if [[ "$ambient_home" == "1" ]]; then real_args+=(--ambient-home); fi
real_exit=0; "$python_bin" "${real_args[@]}" || real_exit=$?
tests_exit=0; "$python_bin" -m unittest discover -s tests -p 'test_control_plane*.py' -v >"$evidence_root/phase-tests.txt" 2>&1 || tests_exit=$?
support_exit=0; "$python_bin" -m unittest tests.test_hook_in_turn_repair tests.test_controller_broker_worker_lease tests.test_phase3_side_effect_tool -v >"$evidence_root/support-tests.txt" 2>&1 || support_exit=$?
core_exit=0; PYTHON_BIN="$python_bin" "$repo_root/tools/validation/runners/run_validate_core.sh" "$evidence_root/core-validation.json" || core_exit=$?
diff_exit=0; git diff --check >"$evidence_root/git-diff-check.txt" 2>&1 || diff_exit=$?
printf '{"schema_version":"ds-lite.phase3-runner.v1","fault_exit":%s,"supervised_exit":%s,"resource_exit":%s,"real_exit":%s,"tests_exit":%s,"support_exit":%s,"core_exit":%s,"diff_exit":%s,"release_allowed":false}\n' "$fault_exit" "$supervised_exit" "$resource_exit" "$real_exit" "$tests_exit" "$support_exit" "$core_exit" "$diff_exit" >"$evidence_root/run-summary.json"
decision_exit=0; "$python_bin" -m teaching.control_plane_phase3_evidence decision --previous "$previous" --fault "$evidence_root/fault-matrix.json" --real-smoke "$evidence_root/real-multigate-smoke.json" --supervised "$evidence_root/supervised-recovery.json" --resource "$evidence_root/resource-windows.json" --tests "$evidence_root/phase-tests.txt" --support-tests "$evidence_root/support-tests.txt" --core "$evidence_root/core-validation.json" --output "$evidence_root/phase3-decision.json" || decision_exit=$?
(( fault_exit == 0 && supervised_exit == 0 && resource_exit == 0 && real_exit == 0 && tests_exit == 0 && support_exit == 0 && core_exit == 0 && diff_exit == 0 && decision_exit == 0 ))
