"""Write-once Phase 2 managed probe and decision receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.backup import backup_control_plane, restore_control_plane
from ds_lite_control.store import ControlStore
from ds_lite_control.workflows import WORKFLOW_REGISTRY
from ds_lite_control.workflows import ManagedController


PHASE2_DECISION_02_SHA256 = "9e3187a2f16e922a6e6360000c914dfabbb57e38695250de9c5be3a5a085372b"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError("receipt already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())


def managed_probe(project: Path, backup: Path, restore: Path, output: Path) -> dict[str, Any]:
    for path in (project, backup, restore, output):
        if path.exists():
            raise FileExistsError("managed evidence paths must be new")
    project.mkdir(parents=True, exist_ok=False)
    state = project / ".ds-lite"
    state.mkdir(parents=True, exist_ok=False)
    (state / "protocol-journal.jsonl").write_text("", encoding="utf-8")
    (state / "broker-metadata.json").write_text(
        json.dumps({"schema_version": "ds-lite.fault-broker-metadata.v1",
                    "broker_id": "managed-probe", "app_server_pid": 0}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store = ControlStore(state / "control.sqlite3")
    try:
        controller = ManagedController(store, state / "receipts", owner_id="phase2-managed")
        result = controller.run_once("phase2-job", "phase2-work", "phase2-action")
        status = store.project_status("phase2-job")
        domain_integrity = store.integrity_check()
    finally:
        store.close()
    sqlite3.connect(state / "runtime.sqlite3").close()
    manifest = backup_control_plane(state, backup, require_protocol=True, require_broker=True)
    restored = restore_control_plane(backup, restore)
    receipt = {
        "schema_version": "ds-lite.phase2-managed-probe.v1",
        "status": "passed" if restored["valid"] and domain_integrity == "ok" else "blocked",
        "evidence_class": "sqlite-backup+fake-host",
        "python_version": platform.python_version(), "dbos_version": "2.29.0",
        "domain_schema": 2, "protocol_journal_present": True,
        "workflow_id": result.get("workflow_id"), "action_id": "phase2-action",
        "status_projection": status, "domain_integrity": domain_integrity,
        "backup_restore_valid": restored["valid"],
        "backup_manifest_sha256": _hash(backup / "manifest.json"),
        "restored_protocol_journal": (restore / "protocol-journal.jsonl").is_file(),
        "restored_broker_metadata": (restore / "broker-metadata.json").is_file(),
        "release_allowed": False,
    }
    write_once(output, receipt)
    return receipt


def decide(*, fault: Path, smoke: Path, managed: Path, tests: Path, core: Path,
           output: Path, real_broker: Path | None = None,
           broker_journal: Path | None = None, previous_decision: Path | None = None,
           phase_contract: Path | None = None,
           expected_previous_sha256: str = PHASE2_DECISION_02_SHA256) -> dict[str, Any]:
    fault_data = json.loads(fault.read_text(encoding="utf-8"))
    smoke_data = json.loads(smoke.read_text(encoding="utf-8"))
    managed_data = json.loads(managed.read_text(encoding="utf-8"))
    raw_tests = tests.read_bytes()
    if raw_tests.startswith((b"\xff\xfe", b"\xfe\xff")):
        test_text = raw_tests.decode("utf-16", errors="replace")
    else:
        test_text = raw_tests.decode("utf-8", errors="replace")
    core_data = json.loads(core.read_text(encoding="utf-8"))
    tests_ok = "FAILED" not in test_text and "OK" in test_text and "Ran " in test_text
    fault_ok = fault_data.get("status") == "passed" and fault_data.get("trials") == 100 and all(
        fault_data.get("cases", {}).get(name, {}).get("passed") == 100
        for name in ("K4", "K5", "K6", "K7", "K12")
    )
    smoke_ok = smoke_data.get("status") == "passed" and smoke_data.get("evidence_class") == "real-app-server"
    continuation = real_broker is not None or broker_journal is not None or previous_decision is not None
    real_data = json.loads(real_broker.read_text(encoding="utf-8")) if real_broker is not None else None
    journal_data = json.loads(broker_journal.read_text(encoding="utf-8")) if broker_journal is not None else None
    previous_ok = bool(previous_decision is not None and _hash(previous_decision) == expected_previous_sha256)
    phase_contract_data = json.loads(phase_contract.read_text(encoding="utf-8")) if phase_contract is not None else None
    phase_contract_ok = bool(isinstance(phase_contract_data, dict)
                             and phase_contract_data.get("status") == "passed")
    real_ok = bool(
        isinstance(real_data, dict)
        and real_data.get("status") == "passed"
        and real_data.get("evidence_class") == "real-app-server-external-controller-processes"
        and real_data.get("turn_start_count") == 3
        and real_data.get("checks", {}).get("single_canonical_thread") is True
        and real_data.get("checks", {}).get("exactly_three_turn_starts") is True
    )
    journal_ok = bool(
        isinstance(journal_data, dict) and journal_data.get("valid") is True
        and journal_data.get("dropped_response_count", 0) >= 2
        and journal_data.get("method_counts", {}).get("turn/start") == 3
        and journal_data.get("method_counts", {}).get("thread/archive") == 1
    )
    response_loss_ok = (real_ok and journal_ok and real_data.get("response_loss_injected") is True
                        and real_data.get("checks", {}).get("response_loss_reconciled") is True) if continuation else (
                            smoke_ok and smoke_data.get("response_loss_injected") is True)
    controller_restart_ok = (real_ok and real_data.get("controller_restart_observed") is True) if continuation else (
        smoke_ok and smoke_data.get("controller_restart_observed") is True)
    archive_ok = bool(real_ok and real_data.get("pending_archive_recovered") is True
                      and real_data.get("checks", {}).get("archive_not_redispatched") is True) if continuation else True
    managed_ok = managed_data.get("status") == "passed" and managed_data.get("backup_restore_valid") is True
    core_ok = core_data.get("status") == "passed"
    go = all((fault_ok, smoke_ok, response_loss_ok, controller_restart_ok, archive_ok,
              managed_ok, tests_ok, core_ok, previous_ok if continuation else True,
              journal_ok if continuation else True,
              phase_contract_ok if continuation else True))
    result = {
        "schema_version": "ds-lite.phase2-decision.v2" if continuation else "ds-lite.phase2-decision.v1",
        "phase2_decision": "go" if go else "no-go",
        "phase3_goal_allowed": go,
        "release_allowed": False,
        "checks": {"fault_matrix": fault_ok, "real_canonical_thread": smoke_ok,
                    "real_response_loss": response_loss_ok, "controller_restart": controller_restart_ok,
                    "real_pending_archive": archive_ok,
                    "broker_journal_integrity": journal_ok if continuation else False,
                    "previous_decision_unchanged": previous_ok if continuation else False,
                    "phase0_phase05_contracts": phase_contract_ok if continuation else False,
                    "managed_backup_restore": managed_ok, "phase_tests": tests_ok,
                    "core_validation": core_ok},
        "versions": {"python": platform.python_version(), "dbos": "2.29.0", "codex_cli": "0.128.0"},
        "fault_seed": fault_data.get("seed"), "fault_trials": fault_data.get("trials"),
        "evidence_classes": {"fault_matrix": fault_data.get("evidence_class"),
                             "canonical_thread": smoke_data.get("evidence_class"),
                             "managed": managed_data.get("evidence_class"),
                             "real_broker": real_data.get("evidence_class") if real_data else None,
                             "broker_journal": "real-app-server-wire-metadata" if journal_data else None},
        "digests": {
            "codex_schema_sha256": "9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
            "hooks_manifest_sha256": "443e21e7e1e8aae2979cb052bab4f303d0decc6c7d058285ff051d2b2286b5ba",
            "hook_script_sha256": "3f660e1d1f2c79bbbb376f583c22376e5659605a0cfd4e9ab56269972bcefbb1",
            "workflow_registry_sha256": hashlib.sha256(
                json.dumps(WORKFLOW_REGISTRY, ensure_ascii=True, sort_keys=True,
                           separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "identities": {
            "thread_id_sha256": real_data.get("thread_id_sha256") if real_data else None,
            "turn_id_sha256": real_data.get("turn_id_sha256") if real_data else [],
            "controller_pids": real_data.get("controller_pids") if real_data else [],
            "app_server_pid": real_data.get("app_server_pid") if real_data else None,
            "broker_id_sha256": real_data.get("broker_id_sha256") if real_data else None,
        },
        "artifacts": {name: {"name": path.name, "sha256": _hash(path)}
                      for name, path in (("fault", fault), ("smoke", smoke), ("managed", managed),
                                         ("tests", tests), ("core", core))},
        "unresolved_risks": [
            "release_allowed remains false",
            "Phase 3 scheduler/failure isolation and Phase 4 reviewer/release are not implemented",
            "non-Windows resource acceptance remains pending",
        ],
        "integrity": {
            "write_once": True,
            "previous_decision_sha256": _hash(previous_decision) if previous_decision else None,
            "raw_model_content_in_receipt": False,
        },
    }
    for name, path in (("real_broker", real_broker), ("broker_journal", broker_journal),
                       ("previous_decision", previous_decision), ("phase_contract", phase_contract)):
        if path is not None:
            result["artifacts"][name] = {"name": path.name, "sha256": _hash(path)}
    write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    managed = sub.add_parser("managed")
    managed.add_argument("--project", type=Path, required=True)
    managed.add_argument("--backup", type=Path, required=True)
    managed.add_argument("--restore", type=Path, required=True)
    managed.add_argument("--output", type=Path, required=True)
    decision = sub.add_parser("decision")
    for name in ("fault", "smoke", "managed", "tests", "core", "output"):
        decision.add_argument(f"--{name}", type=Path, required=True)
    decision.add_argument("--real-broker", type=Path)
    decision.add_argument("--broker-journal", type=Path)
    decision.add_argument("--previous-decision", type=Path)
    decision.add_argument("--phase-contract", type=Path)
    args = parser.parse_args()
    if args.command == "managed":
        result = managed_probe(args.project, args.backup, args.restore, args.output)
    else:
        result = decide(fault=args.fault, smoke=args.smoke, managed=args.managed,
                        tests=args.tests, core=args.core, output=args.output,
                        real_broker=args.real_broker, broker_journal=args.broker_journal,
                        previous_decision=args.previous_decision, phase_contract=args.phase_contract)
    print(json.dumps({"status": result.get("status", result.get("phase2_decision"))}))
    return 0 if result.get("status", result.get("phase2_decision")) in {"passed", "go"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
