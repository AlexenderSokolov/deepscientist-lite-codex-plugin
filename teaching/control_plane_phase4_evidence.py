from __future__ import annotations

import argparse
import codecs
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.backup import backup_control_plane, restore_control_plane, verify_backup  # noqa: E402
from ds_lite_control.broker import DurableWireJournal  # noqa: E402
from ds_lite_control.cli import CURRENT_CODEX_SCHEMA_DIGEST, doctor_report  # noqa: E402
from ds_lite_control.evidence import EvidenceManager  # noqa: E402
from ds_lite_control.errors import IntegrityIncident  # noqa: E402
from ds_lite_control.store import ControlStore  # noqa: E402
from ds_lite_control.verification import DeterministicVerifier  # noqa: E402


FAULT_CASES = (
    "verifier-receipt-before-index", "review-terminal-before-sidecar",
    "sidecar-before-index", "aggregate-receipt-before-index",
)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _optional_json(path: Path) -> dict[str, Any]:
    try:
        return _json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return {"status": "missing-or-invalid", "artifact_present": path.is_file()}


def _test_log(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig", errors="replace")


def _tests_passed(path: Path) -> bool:
    try:
        text = _test_log(path)
    except OSError:
        return False
    return bool(re.search(r"(?m)^OK\s*$", text)) and not bool(re.search(r"(?m)^(FAILED|ERROR)\b", text))


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def verifier_matrix(workdir: Path, output: Path) -> dict[str, Any]:
    if workdir.exists() or output.exists():
        raise FileExistsError("verifier matrix paths must be new")
    workdir.mkdir(parents=True, exist_ok=False)
    cases: dict[str, bool] = {}
    for name, measurement, tamper, policy_mismatch in (
        ("valid-protected-claims-ignored", 42, False, False),
        ("required-field-negative", 0, False, False),
        ("artifact-hash-drift", 42, True, False),
        ("policy-digest-conflict", 42, False, True),
    ):
        root = workdir / name
        root.mkdir()
        artifacts = root / "artifacts"
        artifacts.mkdir()
        artifact = artifacts / "result.json"
        artifact.write_text(json.dumps({
            "schema_version": "ds-lite.phase4-verifier-fixture.v1",
            "measurement": measurement, "passed": True, "release_allowed": True,
        }, sort_keys=True), encoding="utf-8")
        policy = {
            "schema_version": "ds-lite.gate-policy.v1", "policy_id": f"policy-{name}",
            "minimum_evidence_class": "offline", "required_artifacts": [{
                "path": "result.json", "schema_version": "ds-lite.phase4-verifier-fixture.v1",
                "required_fields": {"measurement": 42},
            }],
        }
        store = ControlStore(root / "control.sqlite3")
        try:
            epoch = store.create_job_work_item("job", "gate", "owner")
            manifest = EvidenceManager(store, root / "evidence", root / "private-spool").freeze(
                "job", "gate", artifacts, policy, evidence_class="offline",
                owner_id="owner", fence_epoch=epoch,
            )
            if tamper:
                artifact.write_text("{}", encoding="utf-8")
            verify_policy = dict(policy)
            if policy_mismatch:
                verify_policy = {**policy, "policy_id": "different-policy"}
            try:
                receipt = DeterministicVerifier(store, root / "receipts").verify(
                    "gate", manifest["evidence_set_id"], verify_policy,
                    owner_id="owner", fence_epoch=epoch,
                )
                if name == "valid-protected-claims-ignored":
                    cases[name] = receipt["status"] == "passed" and "protected-claim-ignored" in receipt["check_codes"]
                else:
                    cases[name] = receipt["status"] == "blocked"
            except IntegrityIncident:
                cases[name] = policy_mismatch
        finally:
            store.close()
    result = {
        "schema_version": "ds-lite.phase4-verifier-matrix.v1",
        "status": "passed" if all(cases.values()) else "failed",
        "cases": cases,
        "protected_claims_ignored": cases.get("valid-protected-claims-ignored", False),
        "evidence_class": "offline-deterministic",
        "release_allowed": False,
    }
    _write_once(output, result)
    return result


def status_traceability(state_root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    store = ControlStore(state_root / "control.sqlite3")
    try:
        gate = store.connection.execute(
            "SELECT decision_id,status,receipt_id FROM gate_decisions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        release = store.connection.execute(
            "SELECT decision_id,status,release_allowed,receipt_id FROM release_decisions "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conclusions = []
        for kind, row in (("gate", gate), ("release", release)):
            if row is None:
                conclusions.append(False)
                continue
            receipt_id = str(row[-1])
            indexed = store.connection.execute(
                "SELECT path,content_hash FROM receipt_index WHERE receipt_id=?", (receipt_id,)
            ).fetchone()
            path = state_root / "receipts" / f"{receipt_id}.json"
            conclusions.append(bool(indexed and path.is_file() and indexed[1] == file_hash(path)))
        journal = DurableWireJournal(state_root / "protocol-journal.jsonl").verify()
        doctor = doctor_report(
            python_version=platform.python_version(),
            dbos_version=importlib.metadata.version("dbos"),
            schema_version=store.schema_version,
            integrity=store.integrity_check(),
            codex_schema_digest=CURRENT_CODEX_SCHEMA_DIGEST,
            protocol_present=True,
            broker_configured=True,
            broker_journal_valid=bool(journal["valid"]),
        )
        projection = store.project_job_status("phase4-real-job")
        release_projection = projection["release"]
        result = {
            "schema_version": "ds-lite.phase4-status-traceability.v1",
            "status": "passed" if (
                all(conclusions) and release is not None and int(release[2]) == 0
                and doctor["managed_allowed"] and projection["release_allowed"] is False
                and bool(release_projection["blockers"]) and bool(release_projection["sources"])
            ) else "failed",
            "all_conclusions_sourced": all(conclusions),
            "managed_doctor_allowed": bool(doctor["managed_allowed"]),
            "doctor_checks": doctor["checks"],
            "project_status_schema": projection["schema_version"],
            "release_blockers": release_projection["blockers"],
            "release_sources": release_projection["sources"],
            "gate_status": str(gate[1]) if gate else "missing",
            "release_status": str(release[1]) if release else "missing",
            "release_allowed": bool(release[2]) if release else False,
            "integrity_check": store.integrity_check(),
        }
    finally:
        store.close()
    _write_once(output, result)
    return result


def backup_probe(state_root: Path, workdir: Path, output: Path) -> dict[str, Any]:
    if workdir.exists() or output.exists():
        raise FileExistsError("backup probe paths must be new")
    workdir.mkdir(parents=True, exist_ok=False)
    backup = workdir / "backup"
    restored = workdir / "restored"
    manifest = backup_control_plane(
        state_root, backup, require_protocol=True, require_broker=True,
        require_supervisor=True, require_evidence=True,
    )
    verified = verify_backup(backup)
    recovery = restore_control_plane(backup, restored)
    result = {
        "schema_version": "ds-lite.phase4-backup-recovery.v1",
        "status": "passed" if verified["valid"] and recovery["valid"] else "failed",
        "backup_schema": manifest["schema_version"],
        "manifest_sha256": file_hash(backup / "manifest.json"),
        "restore_valid": bool(recovery["valid"]),
        "runtime_evidence_class": "sqlite-backup-contract",
        "release_allowed": False,
    }
    _write_once(output, result)
    return result


def decide(
    *, previous: Path, expected_previous_hash: str, verifier: Path, fault: Path,
    real_reviewer: Path, status: Path, backup: Path, aggregate: Path,
    tests: Path, core: Path, output: Path,
) -> dict[str, Any]:
    inputs = {
        name: _optional_json(path) for name, path in (
            ("verifier", verifier), ("fault", fault), ("real_reviewer", real_reviewer),
            ("status", status), ("backup", backup), ("aggregate", aggregate), ("core", core),
        )
    }
    real_checks = inputs["real_reviewer"].get("checks", {})
    required_real_checks = (
        "independent_reviewer_thread", "single_reviewer_turn", "read_only_wire",
        "never_approve_wire", "single_canary_thread", "single_canary_turn",
        "canary_read_only_wire", "canary_never_approve_wire",
        "write_canary_command_observed", "write_canary_denied",
        "artifact_digest_unchanged", "terminal_sidecar", "project_aggregate_blocked",
    )
    fault_data = inputs["fault"]
    checks = {
        "phase3_receipt_unchanged": file_hash(previous) == expected_previous_hash,
        "deterministic_verifier": inputs["verifier"].get("status") == "passed"
            and inputs["verifier"].get("protected_claims_ignored") is True,
        "fault_matrix_100_trials": fault_data.get("status") == "passed"
            and fault_data.get("trials") == 100
            and all(fault_data.get("cases", {}).get(case, {}).get("all_passed") is True for case in FAULT_CASES),
        "real_independent_reviewer": inputs["real_reviewer"].get("status") == "passed"
            and inputs["real_reviewer"].get("evidence_class") == "real-codex-independent-reviewer"
            and all(real_checks.get(name) is True for name in required_real_checks)
            and inputs["real_reviewer"].get("home_mode") == "ambient"
            and inputs["real_reviewer"].get("raw_model_text_in_receipt") is False
            and inputs["real_reviewer"].get("controller_inspected_copied_or_modified_credentials") is False,
        "real_schema_pinned": inputs["real_reviewer"].get("codex_version") == "0.146.0-alpha.3.1"
            and isinstance(inputs["real_reviewer"].get("schema_sha256"), str)
            and len(inputs["real_reviewer"].get("schema_sha256", "")) == 64,
        "status_traceable": inputs["status"].get("status") == "passed"
            and inputs["status"].get("all_conclusions_sourced") is True
            and inputs["status"].get("managed_doctor_allowed") is True
            and inputs["status"].get("project_status_schema") == "ds-lite.project-status.v3"
            and inputs["status"].get("release_allowed") is False,
        "backup_v5_recovery": inputs["backup"].get("status") == "passed"
            and inputs["backup"].get("backup_schema") == "ds-lite.control-backup.v5"
            and inputs["backup"].get("restore_valid") is True,
        "project_aggregate_blocked": inputs["aggregate"].get("status") == "blocked"
            and inputs["aggregate"].get("release_allowed") is False
            and inputs["aggregate"].get("fixture_only") is False,
        "phase_tests": _tests_passed(tests),
        "core_validation": inputs["core"].get("status") == "passed",
    }
    go = all(checks.values())
    result = {
        "schema_version": "ds-lite.phase4-decision.v1",
        "phase4_decision": "go" if go else "no-go",
        "phase5_goal_allowed": go,
        "release_allowed": False,
        "checks": checks,
        "versions": {
            "python": platform.python_version(), "dbos": "2.29.0",
            "codex_cli": inputs["real_reviewer"].get("codex_version"),
        },
        "digests": {
            "phase3_decision_sha256": file_hash(previous),
            "codex_schema_sha256": inputs["real_reviewer"].get("schema_sha256"),
            "workflow_registry_sha256": inputs["real_reviewer"].get("workflow_registry_sha256"),
        },
        "identities": {
            name: inputs["real_reviewer"].get(name)
            for name in (
                "action_id_sha256", "review_id_sha256", "owner_id_sha256", "fence_epoch",
                "worker_thread_sha256", "reviewer_thread_sha256", "reviewer_turn_sha256",
                "workflow_identity_rule",
            )
        },
        "fault_seed": inputs["fault"].get("seed"),
        "artifacts": {
            name: {
                "name": path.name,
                "present": path.is_file(),
                "sha256": file_hash(path) if path.is_file() else None,
            }
            for name, path in (
                ("phase3_decision", previous), ("verifier_matrix", verifier),
                ("reviewer_fault_matrix", fault), ("real_reviewer_smoke", real_reviewer),
                ("status_traceability", status), ("backup_recovery", backup),
                ("project_release_aggregate", aggregate), ("phase_tests", tests),
                ("core_validation", core),
            )
        },
        "evidence_classes": {
            "verifier": "offline-deterministic",
            "faults": "sqlite-filesystem-external-process",
            "reviewer": inputs["real_reviewer"].get("evidence_class"),
        },
        "unresolved_risks": [
            "real project release remains blocked until Phase 5",
            "non-Windows and full release-profile host acceptance remain Phase 5 work",
        ],
    }
    _write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    decision = sub.add_parser("decision")
    for name in ("previous", "verifier", "fault", "real-reviewer", "status", "backup", "aggregate", "tests", "core", "output"):
        decision.add_argument(f"--{name}", type=Path, required=True)
    decision.add_argument("--expected-previous-hash", required=True)
    verifier = sub.add_parser("verifier-matrix")
    verifier.add_argument("--workdir", type=Path, required=True)
    verifier.add_argument("--output", type=Path, required=True)
    status = sub.add_parser("status-traceability")
    status.add_argument("--state-root", type=Path, required=True)
    status.add_argument("--output", type=Path, required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--state-root", type=Path, required=True)
    backup.add_argument("--workdir", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verifier-matrix":
        result = verifier_matrix(args.workdir.resolve(), args.output.resolve())
        status_value = result["status"]
    elif args.command == "status-traceability":
        result = status_traceability(args.state_root.resolve(), args.output.resolve())
        status_value = result["status"]
    elif args.command == "backup":
        result = backup_probe(args.state_root.resolve(), args.workdir.resolve(), args.output.resolve())
        status_value = result["status"]
    else:
        result = decide(
            previous=args.previous, expected_previous_hash=args.expected_previous_hash,
            verifier=args.verifier, fault=args.fault, real_reviewer=args.real_reviewer,
            status=args.status, backup=args.backup, aggregate=args.aggregate,
            tests=args.tests, core=args.core, output=args.output,
        )
        status_value = result["phase4_decision"]
    print(json.dumps({"status": status_value}, sort_keys=True))
    return 0 if status_value in {"passed", "go"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
