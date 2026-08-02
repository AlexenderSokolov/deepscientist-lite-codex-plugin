"""Write-once managed probe and deterministic Phase 1 decision receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
BASELINE = ROOT / "research" / ".validation-tmp" / "control-plane-evidence-20260731" / "spike-decision-05.json"
BASELINE_SHA256 = "ed9a005e8e7eca786ee1ae03a2984673bed0ef877361fb471b3d99c46108fe3c"


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _controller_source_digest() -> str:
    digest = hashlib.sha256()
    files = [Path(__file__).resolve(), *sorted((CONTROLLER_ROOT / "ds_lite_control").glob("*.py")),
             CONTROLLER_ROOT / "phase1_fault_harness.py"]
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def artifact_ref(path: Path, evidence_class: str) -> dict[str, str]:
    return {"name": path.name, "sha256": _hash_file(path), "evidence_class": evidence_class}


def _combined_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_json_event(output: str, *, required_key: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and required_key in value:
            return value
    return None


def write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def summarize_test_run(*, returncode: int, output: str) -> dict[str, Any]:
    count_match = re.search(r"Ran (\d+) tests?", output)
    failure_match = re.search(r"failures=(\d+)", output)
    error_match = re.search(r"errors=(\d+)", output)
    failures = int(failure_match.group(1)) if failure_match else 0
    errors = int(error_match.group(1)) if error_match else 0
    return {
        "schema_version": "ds-lite.phase1-tests.v1",
        "status": "passed" if returncode == 0 and failures == 0 and errors == 0 else "blocked",
        "tests_run": int(count_match.group(1)) if count_match else 0,
        "failures": failures + errors if returncode != 0 else 0,
        "exit_code": returncode,
        "output_sha256": _hash_bytes(output.encode("utf-8", errors="replace")),
        "raw_output_persisted": False,
        "release_allowed": False,
    }


def _run(command: list[str], env: dict[str, str], timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)


def run_managed_probe(args: argparse.Namespace) -> dict[str, Any]:
    if args.output.exists() or args.project.exists() or args.backup.exists() or args.restore.exists():
        raise FileExistsError("managed probe paths must be new")
    source_before = _controller_source_digest()
    env = os.environ.copy()
    paths = [str(args.dependency_root.resolve()), str(CONTROLLER_ROOT)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    base = [str(args.python_bin.resolve()), "-m", "ds_lite_control"]
    doctor_process = _run(base + ["doctor", "--project", str(args.project)], env)
    doctor = parse_json_event(doctor_process.stdout, required_key="managed_allowed")
    run_command = base + [
        "control", "run", "phase1-job", "--project", str(args.project),
        "--work-item-id", "phase1-work", "--action-id", "phase1-action",
        "--owner-id", "phase1-managed", "--once",
    ]
    first_process = _run(run_command, env)
    second_process = _run(run_command, env)
    first = parse_json_event(first_process.stdout, required_key="workflow_id")
    second = parse_json_event(second_process.stdout, required_key="workflow_id")
    status_process = _run(base + [
        "control", "status", "phase1-job", "--project", str(args.project), "--json"
    ], env)
    status = parse_json_event(status_process.stdout, required_key="next_durable_action")
    backup_process = _run(base + [
        "control", "backup", "--project", str(args.project), "--output", str(args.backup)
    ], env)
    restore_process = _run(base + [
        "control", "restore", "--backup", str(args.backup), "--output", str(args.restore)
    ], env)
    restore = parse_json_event(restore_process.stdout, required_key="valid")
    source_root = args.project / ".ds-lite"
    domain = sqlite3.connect(source_root / "control.sqlite3")
    runtime = sqlite3.connect(source_root / "runtime.sqlite3")
    restored_domain = sqlite3.connect(args.restore / "control.sqlite3")
    restored_runtime = sqlite3.connect(args.restore / "runtime.sqlite3")
    try:
        domain_integrity = domain.execute("PRAGMA integrity_check").fetchone()[0]
        runtime_integrity = runtime.execute("PRAGMA integrity_check").fetchone()[0]
        restored_domain_integrity = restored_domain.execute("PRAGMA integrity_check").fetchone()[0]
        restored_runtime_integrity = restored_runtime.execute("PRAGMA integrity_check").fetchone()[0]
        workflow_rows = runtime.execute(
            "SELECT status FROM workflow_status WHERE workflow_uuid='phase1-action'"
        ).fetchall()
    finally:
        restored_runtime.close()
        restored_domain.close()
        runtime.close()
        domain.close()
    same_identity = bool(
        first and second and first.get("workflow_id") == "phase1-action" and
        second.get("workflow_id") == "phase1-action"
    )
    backup_valid = bool(
        restore and restore.get("valid") is True and
        domain_integrity == restored_domain_integrity == "ok" and
        runtime_integrity == restored_runtime_integrity == "ok"
    )
    source_after = _controller_source_digest()
    source_stable = source_before == source_after
    passed = all((
        doctor_process.returncode == 0, doctor and doctor.get("managed_allowed") is True,
        first_process.returncode == 0, second_process.returncode == 0,
        status_process.returncode == 0, status and status.get("next_durable_action") == "none",
        backup_process.returncode == 0, restore_process.returncode == 0,
        same_identity, len(workflow_rows) == 1, backup_valid, source_stable,
    ))
    result = {
        "schema_version": "ds-lite.phase1-managed-probe.v1",
        "status": "passed" if passed else "blocked",
        "evidence_class": "real-dbos-sqlite+fake-host",
        "python_version": doctor.get("python_version") if doctor else platform.python_version(),
        "dbos_version": doctor.get("dbos_version") if doctor else "unknown",
        "doctor_managed_allowed": bool(doctor and doctor.get("managed_allowed")),
        "same_action_workflow_identity": same_identity,
        "workflow_row_count": len(workflow_rows),
        "workflow_status": workflow_rows[0][0] if len(workflow_rows) == 1 else None,
        "domain_integrity": domain_integrity,
        "runtime_integrity": runtime_integrity,
        "backup_restore_valid": backup_valid,
        "receipt_count": len(list((source_root / "receipts").glob("*.json"))),
        "status_projection": status,
        "action_id_sha256": _hash_bytes(b"phase1-action"),
        "control_database_sha256": _hash_file(source_root / "control.sqlite3"),
        "runtime_database_sha256": _hash_file(source_root / "runtime.sqlite3"),
        "raw_output_persisted": False,
        "network_or_service_used": False,
        "source_digest": source_after,
        "source_stable": source_stable,
        "release_allowed": False,
    }
    write_once(args.output, result)
    return result


def decide_phase1(*, fault: dict[str, Any], managed: dict[str, Any], tests: dict[str, Any],
                  core: dict[str, Any], baseline_hash_matches: bool) -> dict[str, Any]:
    fault_ok = (fault.get("status") == "passed" and fault.get("trials") == 100 and
                fault.get("source_stable") is True) and all(
        fault.get("cases", {}).get(name, {}).get("all_passed") is True and
        fault.get("cases", {}).get(name, {}).get("passed") == 100
        for name in ("K1", "K2", "K3", "K8", "K9")
    )
    managed_ok = all((
        managed.get("status") == "passed",
        managed.get("python_version") == "3.13.5",
        managed.get("dbos_version") == "2.29.0",
        managed.get("same_action_workflow_identity") is True,
        managed.get("workflow_row_count") == 1,
        managed.get("backup_restore_valid") is True,
        managed.get("domain_integrity") == "ok",
        managed.get("runtime_integrity") == "ok",
        managed.get("source_stable") is True,
    ))
    tests_ok = tests.get("status") == "passed" and tests.get("failures") == 0
    core_ok = core.get("status") == "passed" and core.get("failures", 0) == 0
    go = all((fault_ok, managed_ok, tests_ok, core_ok, baseline_hash_matches))
    workflow_digest = _hash_bytes(json.dumps(
        ["reconcile_job_v1", "run_action_v1", "project_status_v1"], separators=(",", ":")
    ).encode())
    return {
        "schema_version": "ds-lite.phase1-decision.v1",
        "phase1_decision": "go" if go else "no-go",
        "phase2_goal_allowed": go,
        "release_allowed": False,
        "checks": {
            "fault_matrix": fault_ok, "managed_durable_recovery": managed_ok,
            "phase_tests": tests_ok, "core_validation": core_ok,
            "phase05_baseline_unchanged": baseline_hash_matches,
        },
        "versions": {
            "python": managed.get("python_version"), "dbos": managed.get("dbos_version"),
            "codex_cli": "0.128.0", "domain_schema": 1,
        },
        "codex_schema_digest": "9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb",
        "phase05_baseline_sha256": BASELINE_SHA256,
        "workflow_registry_sha256": workflow_digest,
        "fault_seed": fault.get("seed"),
        "fault_identity_digests": {
            name: fault.get("cases", {}).get(name, {}).get("identity_digest")
            for name in ("K1", "K2", "K3", "K8", "K9")
        },
        "identity_summary": {
            "action_id_sha256": managed.get("action_id_sha256"),
            "workflow_id_equals_action_id": managed.get("same_action_workflow_identity"),
            "workflow_row_count": managed.get("workflow_row_count"),
        },
        "evidence_classes": {
            "K1-K3": "real-dbos-sqlite", "K8-K9": "fake-host-filesystem",
            "managed": "real-dbos-sqlite+fake-host", "real_codex": "not-observed-phase1",
        },
        "unresolved_risks": [
            "real Codex response-loss and canonical thread controller integration remain Phase 2",
            "non-Windows resource acceptance remains pending before release",
            "plugin_hooks is disabled by default in Codex 0.128.0",
            "supervisor, reviewer, scheduler, and release aggregate are not implemented",
        ],
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe")
    probe.add_argument("--dependency-root", required=True, type=Path)
    probe.add_argument("--python-bin", required=True, type=Path)
    probe.add_argument("--project", required=True, type=Path)
    probe.add_argument("--backup", required=True, type=Path)
    probe.add_argument("--restore", required=True, type=Path)
    probe.add_argument("--output", required=True, type=Path)
    decision = sub.add_parser("decision")
    decision.add_argument("--fault", required=True, type=Path)
    decision.add_argument("--managed", required=True, type=Path)
    decision.add_argument("--tests", required=True, type=Path)
    decision.add_argument("--core", required=True, type=Path)
    decision.add_argument("--output", required=True, type=Path)
    tests = sub.add_parser("tests")
    tests.add_argument("--python-bin", required=True, type=Path)
    tests.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "tests":
        modules = [
            "tests.test_control_plane_phase1", "tests.test_control_plane_phase1_cli",
            "tests.test_control_plane_phase1_evidence", "tests.test_control_plane_spike",
            "tests.test_dbos_sqlite_recovery_probe", "tests.test_control_plane_incident",
            "tests.test_hooks", "tests.test_autonomy_controller",
        ]
        process = subprocess.run(
            [str(args.python_bin.resolve()), "-m", "unittest", *modules, "-v"],
            capture_output=True, text=True, cwd=ROOT,
        )
        result = summarize_test_run(returncode=process.returncode, output=process.stdout + process.stderr)
        result["python_version"] = platform.python_version()
        result["modules"] = modules
        write_once(args.output, result)
        print(json.dumps({"status": result["status"], "tests_run": result["tests_run"]}))
        return 0 if result["status"] == "passed" else 2
    if args.command == "probe":
        result = run_managed_probe(args)
        print(json.dumps({"status": result["status"], "evidence_class": result["evidence_class"]}))
        return 0 if result["status"] == "passed" else 2
    baseline_matches = BASELINE.is_file() and _hash_file(BASELINE) == BASELINE_SHA256
    result = decide_phase1(
        fault=_read(args.fault), managed=_read(args.managed), tests=_read(args.tests),
        core=_read(args.core), baseline_hash_matches=baseline_matches,
    )
    result["artifacts"] = {
        "fault": artifact_ref(args.fault, "real-dbos-sqlite+fake-host-filesystem"),
        "managed": artifact_ref(args.managed, "real-dbos-sqlite+fake-host"),
        "tests": artifact_ref(args.tests, "offline-test"),
        "core": artifact_ref(args.core, "offline-package-validation"),
    }
    resource = BASELINE.parent / "resource-probe-02.json"
    result["phase05_resource_baseline"] = (
        artifact_ref(resource, "windows-resource-probe") if resource.is_file() else None
    )
    result["domain_schema_sha256"] = _hash_file(
        CONTROLLER_ROOT / "ds_lite_control" / "migrations.py"
    )
    result["hook_contract_sha256"] = _combined_digest([
        ROOT / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json",
        ROOT / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_hook.py",
    ])
    result["decision_runner_sha256"] = _hash_file(Path(__file__).resolve())
    write_once(args.output, result)
    print(json.dumps({"phase1_decision": result["phase1_decision"],
                      "release_allowed": result["release_allowed"]}))
    return 0 if result["phase1_decision"] == "go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
