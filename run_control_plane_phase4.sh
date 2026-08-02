#!/usr/bin/env bash
set -u
repo_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$repo_root"
evidence_root="${1:?usage: run_control_plane_phase4.sh EVIDENCE_ROOT DBOS_ROOT CODEX_BIN [PYTHON_BIN]}"
dbos_root="${2:?DBOS_ROOT required}"
codex_bin="${3:?CODEX_BIN required}"
python_bin="${4:-/opt/anaconda3/bin/python}"
model="${MODEL:-gpt-5.6-sol}"
codex_version="${CODEX_VERSION:-0.146.0-alpha.3.1}"
case "$(cd "$(dirname "$evidence_root")" 2>/dev/null && pwd)/$(basename "$evidence_root")" in "$repo_root"/*) ;; *) echo "evidence root must be inside repository" >&2; exit 2;; esac
[[ ! -e "$evidence_root" ]] || { echo "evidence root already exists" >&2; exit 2; }
[[ "$($python_bin -c 'import platform; print(platform.python_version())')" == "3.13.5" ]] || { echo "Python 3.13.5 required" >&2; exit 2; }
[[ "$($codex_bin --version)" == "codex-cli $codex_version" ]] || { echo "Codex $codex_version required" >&2; exit 2; }
[[ -d "$dbos_root/dbos-2.29.0.dist-info" ]] || { echo "DBOS 2.29.0 required" >&2; exit 2; }
mkdir "$evidence_root"
export PYTHONDONTWRITEBYTECODE=1
export PYTHON_BIN="$python_bin"
export PYTHONPATH="$dbos_root:$repo_root/plugins/deepscientist-lite-core/controller:$repo_root${PYTHONPATH:+:$PYTHONPATH}"
schema_root="$repo_root/plugins/deepscientist-lite-core/schemas/codex/$codex_version"
previous="$repo_root/research/.validation-tmp/control-plane-phase3-final-20260731-03/phase3-decision.json"
previous_hash="6fba9ca1417efa3a36faecf45d852b902ddc8a57481dfacc50be112b143a1341"

verifier_exit=0; "$python_bin" -m teaching.control_plane_phase4_evidence verifier-matrix --workdir "$evidence_root/verifier-work" --output "$evidence_root/verifier-matrix.json" || verifier_exit=$?
fault_exit=0; "$python_bin" "$repo_root/teaching/control_plane_phase4_fault_harness.py" --workdir "$evidence_root/fault-work" --output "$evidence_root/reviewer-fault-matrix.json" --python-bin "$python_bin" --seed 20260801 --trials 100 --timeout 20 || fault_exit=$?
real_exit=0; "$python_bin" "$repo_root/teaching/controller_phase4_reviewer_smoke.py" --codex-bin "$codex_bin" --codex-version "$codex_version" --schema-root "$schema_root" --runtime "$evidence_root/real-runtime" --output "$evidence_root/real-reviewer-smoke.json" --journal-summary "$evidence_root/broker-journal-summary.json" --aggregate-output "$evidence_root/project-release-aggregate.json" --model "$model" --ambient-home || real_exit=$?
status_exit=0; "$python_bin" -m teaching.control_plane_phase4_evidence status-traceability --state-root "$evidence_root/real-runtime" --output "$evidence_root/status-traceability.json" || status_exit=$?
backup_exit=0; "$python_bin" -m teaching.control_plane_phase4_evidence backup --state-root "$evidence_root/real-runtime" --workdir "$evidence_root/backup-work" --output "$evidence_root/backup-recovery.json" || backup_exit=$?
tests_exit=0; "$python_bin" -m unittest discover -s tests -p 'test_control_plane*.py' -v >"$evidence_root/phase-tests.txt" 2>&1 || tests_exit=$?
core_exit=0; PYTHON_BIN="$python_bin" "$repo_root/run_validate_core.sh" "$evidence_root/core-validation.json" || core_exit=$?
diff_exit=0; git diff --check >"$evidence_root/git-diff-check.txt" 2>&1 || diff_exit=$?
printf '{"schema_version":"ds-lite.phase4-runner.v1","verifier_exit":%s,"fault_exit":%s,"real_exit":%s,"status_exit":%s,"backup_exit":%s,"tests_exit":%s,"core_exit":%s,"diff_exit":%s,"ambient_home":true,"release_allowed":false}\n' "$verifier_exit" "$fault_exit" "$real_exit" "$status_exit" "$backup_exit" "$tests_exit" "$core_exit" "$diff_exit" >"$evidence_root/run-summary.json"
decision_exit=0; "$python_bin" -m teaching.control_plane_phase4_evidence decision --previous "$previous" --expected-previous-hash "$previous_hash" --verifier "$evidence_root/verifier-matrix.json" --fault "$evidence_root/reviewer-fault-matrix.json" --real-reviewer "$evidence_root/real-reviewer-smoke.json" --status "$evidence_root/status-traceability.json" --backup "$evidence_root/backup-recovery.json" --aggregate "$evidence_root/project-release-aggregate.json" --tests "$evidence_root/phase-tests.txt" --core "$evidence_root/core-validation.json" --output "$evidence_root/phase4-decision.json" || decision_exit=$?
(( verifier_exit == 0 && fault_exit == 0 && real_exit == 0 && status_exit == 0 && backup_exit == 0 && tests_exit == 0 && core_exit == 0 && diff_exit == 0 && decision_exit == 0 ))
