#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${EVIDENCE_ROOT:?set EVIDENCE_ROOT}"
: "${DBOS_DEPENDENCY_ROOT:?set DBOS_DEPENDENCY_ROOT}"
: "${CODEX_BIN:?set CODEX_BIN to Codex 0.128.0}"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python}"
PREVIOUS_DECISION="${PREVIOUS_DECISION:-$ROOT/research/.validation-tmp/control-plane-phase2-20260731-03/phase2-decision-02.json}"
PREVIOUS_SMOKE="${PREVIOUS_SMOKE:-$ROOT/research/.validation-tmp/control-plane-phase2-20260731-02/canonical-thread-smoke.json}"
case "$(cd "$(dirname "$EVIDENCE_ROOT")" && pwd)/$(basename "$EVIDENCE_ROOT")" in "$ROOT"/*) ;; *) echo "Evidence root must stay inside repository" >&2; exit 2;; esac
test ! -e "$EVIDENCE_ROOT"
test "$($PYTHON_BIN -c 'import platform; print(platform.python_version())')" = "3.13.5"
test "$($CODEX_BIN --version)" = "codex-cli 0.128.0"
test -d "$DBOS_DEPENDENCY_ROOT/dbos-2.29.0.dist-info"
test "$(sha256sum "$PREVIOUS_DECISION" | cut -d' ' -f1)" = "9e3187a2f16e922a6e6360000c914dfabbb57e38695250de9c5be3a5a085372b"
mkdir "$EVIDENCE_ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$DBOS_DEPENDENCY_ROOT:$ROOT/plugins/deepscientist-lite-core/controller${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" "$ROOT/plugins/deepscientist-lite-core/controller/phase2_fault_harness.py" --workdir "$EVIDENCE_ROOT/fault-work" --output "$EVIDENCE_ROOT/fault-matrix.json" --seed 20260731 --trials 100
"$PYTHON_BIN" -m unittest tests.test_control_plane_phase2 tests.test_control_plane_phase2_app_server tests.test_control_plane_phase2_broker tests.test_control_plane_phase2_runner tests.test_control_plane_phase2_fault_harness tests.test_control_plane_phase2_evidence tests.test_control_plane_phase1 tests.test_control_plane_phase1_cli tests.test_control_plane_spike -v >"$EVIDENCE_ROOT/phase-tests.txt" 2>&1
"$PYTHON_BIN" -m teaching.control_plane_phase_tests --output "$EVIDENCE_ROOT/phase0-phase05-tests.json"
"$PYTHON_BIN" "$ROOT/teaching/controller_broker_smoke.py" --codex-bin "$CODEX_BIN" --schema-root "$ROOT/plugins/deepscientist-lite-core/schemas/codex/0.128.0" --workspace "$ROOT" --runtime "$EVIDENCE_ROOT/real-runtime" --output "$EVIDENCE_ROOT/real-fault-broker-smoke.json" --journal-summary "$EVIDENCE_ROOT/broker-journal-summary.json"
"$PYTHON_BIN" -m teaching.control_plane_phase2_evidence managed --project "$EVIDENCE_ROOT/managed-project" --backup "$EVIDENCE_ROOT/managed-backup" --restore "$EVIDENCE_ROOT/managed-restore" --output "$EVIDENCE_ROOT/managed-probe.json"
"$PYTHON_BIN" -m ds_lite_control doctor --project "$EVIDENCE_ROOT/managed-project" >"$EVIDENCE_ROOT/doctor.txt"
"$ROOT/tools/validation/runners/run_validate_core.sh" "$EVIDENCE_ROOT/core-validation.json"
git -C "$ROOT" diff --check >"$EVIDENCE_ROOT/git-diff-check.txt"
"$PYTHON_BIN" -m teaching.control_plane_phase2_evidence decision --fault "$EVIDENCE_ROOT/fault-matrix.json" --smoke "$PREVIOUS_SMOKE" --managed "$EVIDENCE_ROOT/managed-probe.json" --tests "$EVIDENCE_ROOT/phase-tests.txt" --phase-contract "$EVIDENCE_ROOT/phase0-phase05-tests.json" --core "$EVIDENCE_ROOT/core-validation.json" --real-broker "$EVIDENCE_ROOT/real-fault-broker-smoke.json" --broker-journal "$EVIDENCE_ROOT/broker-journal-summary.json" --previous-decision "$PREVIOUS_DECISION" --output "$EVIDENCE_ROOT/phase2-decision-03.json"
printf '%s\n' '{"schema_version":"ds-lite.phase2-continuation-runner.v1","status":"completed","release_allowed":false}' >"$EVIDENCE_ROOT/run-summary.json"
