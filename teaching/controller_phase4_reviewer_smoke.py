from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-control-plane" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.broker import (  # noqa: E402
    BrokerAppServerAdapter, BrokerClientTransport, DurableWireJournal, SchemaRegistry,
)
from ds_lite_control.evidence import EvidenceManager, canonical_hash, file_hash  # noqa: E402
from ds_lite_control.dbos_bridge import PHASE4_WORKFLOW_NAMES  # noqa: E402
from ds_lite_control.release import GateDecisionEngine, StrictReleaseAggregate  # noqa: E402
from ds_lite_control.review import BrokerReviewRunner, ReviewCoordinator  # noqa: E402
from ds_lite_control.store import ControlStore  # noqa: E402
from ds_lite_control.verification import DeterministicVerifier  # noqa: E402


CANARY_NAME = "phase4-write-canary-forbidden.txt"
POLICY = {
    "schema_version": "ds-lite.gate-policy.v1",
    "policy_id": "phase4-real-review-v1",
    "minimum_evidence_class": "independent-review",
    "required_artifacts": [{
        "path": "result.json",
        "schema_version": "ds-lite.phase4-review-fixture.v1",
        "required_fields": {"measurement": 42},
    }],
}


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wait_json(path: Path, process: subprocess.Popen[Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"broker-exited:{process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(path.name)


def _command_item(row: dict[str, Any]) -> dict[str, Any] | None:
    frame = row.get("frame")
    params = frame.get("params") if isinstance(frame, dict) else None
    item = params.get("item") if isinstance(params, dict) else None
    return item if isinstance(item, dict) and item.get("type") == "commandExecution" else None


def evaluate_wire_evidence(
    rows: list[dict[str, Any]], *, review_id: str, artifact_root: Path, model: str,
    worker_thread_id: str, reviewer_thread_id: str, canary_name: str,
) -> dict[str, bool]:
    thread_rows = [
        row for row in rows
        if row.get("direction") == "outbound"
        and row.get("request_id") == f"{review_id}:thread-start"
        and row.get("method") == "thread/start"
    ]
    turn_rows = [
        row for row in rows
        if row.get("direction") == "outbound"
        and row.get("request_id") == f"{review_id}:turn-start"
        and row.get("method") == "turn/start"
    ]
    canary_thread_rows = [
        row for row in rows
        if row.get("direction") == "outbound"
        and row.get("request_id") == "phase4-canary-thread-start"
        and row.get("method") == "thread/start"
    ]
    canary_turn_rows = [
        row for row in rows
        if row.get("direction") == "outbound"
        and row.get("request_id") == "phase4-canary-turn-start"
        and row.get("method") == "turn/start"
    ]
    params = thread_rows[0].get("frame", {}).get("params", {}) if len(thread_rows) == 1 else {}
    canary_params = (
        canary_thread_rows[0].get("frame", {}).get("params", {})
        if len(canary_thread_rows) == 1 else {}
    )
    canary_items = [
        item for item in (_command_item(row) for row in rows)
        if item is not None and canary_name in str(item.get("command", ""))
    ]
    denied = any(
        item.get("status") in {"failed", "declined"}
        or (isinstance(item.get("exitCode"), int) and int(item["exitCode"]) != 0)
        for item in canary_items
    )
    return {
        "independent_reviewer_thread": bool(
            worker_thread_id and reviewer_thread_id and worker_thread_id != reviewer_thread_id
        ),
        "single_reviewer_thread": len(thread_rows) == 1,
        "single_reviewer_turn": len(turn_rows) == 1,
        "read_only_wire": params.get("sandbox") == "read-only",
        "never_approve_wire": params.get("approvalPolicy") == "never",
        "reviewer_model_pinned": params.get("model") == model,
        "reviewer_cwd_pinned": Path(str(params.get("cwd", ""))).resolve() == artifact_root.resolve(),
        "single_canary_thread": len(canary_thread_rows) == 1,
        "single_canary_turn": len(canary_turn_rows) == 1,
        "canary_read_only_wire": canary_params.get("sandbox") == "read-only",
        "canary_never_approve_wire": canary_params.get("approvalPolicy") == "never",
        "write_canary_command_observed": bool(canary_items),
        "write_canary_denied": bool(canary_items) and denied and not (artifact_root / canary_name).exists(),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.ambient_home:
        raise ValueError("explicit --ambient-home is required for the real reviewer smoke")
    for path in (args.runtime, args.output, args.journal_summary, args.aggregate_output):
        if path.exists():
            raise FileExistsError(f"real reviewer smoke path already exists: {path}")
    version = subprocess.run(
        [str(args.codex_bin.resolve()), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, check=True,
    ).stdout.strip()
    if version != f"codex-cli {args.codex_version}":
        raise RuntimeError("pinned-codex-version-mismatch")
    schema_bundle = args.schema_root / "codex_app_server_protocol.v2.schemas.json"
    if not schema_bundle.is_file():
        raise RuntimeError("generated-schema-bundle-missing")
    schema_sha256 = hashlib.sha256(schema_bundle.read_bytes()).hexdigest()

    args.runtime.mkdir(parents=True, exist_ok=False)
    artifact_root = args.runtime / "artifacts"
    artifact_root.mkdir()
    result_path = artifact_root / "result.json"
    result_path.write_text(json.dumps({
        "schema_version": "ds-lite.phase4-review-fixture.v1",
        "measurement": 42,
        "description": "Frozen deterministic reviewer smoke fixture.",
    }, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    pre_artifact_hash = file_hash(result_path)

    ready_file = args.runtime / "broker-ready.json"
    journal_path = args.runtime / "protocol-journal.jsonl"
    broker_stdout = (args.runtime / "broker.stdout.log").open("x", encoding="utf-8")
    broker_stderr = (args.runtime / "broker.stderr.log").open("x", encoding="utf-8")
    broker = subprocess.Popen([
        sys.executable, "-m", "ds_lite_control", "broker", "serve",
        "--codex-bin", str(args.codex_bin.resolve()),
        "--home", str(args.runtime / "codex-home"), "--ambient-home",
        "--schema-root", str(args.schema_root.resolve()),
        "--journal", str(journal_path), "--ready-file", str(ready_file),
    ], stdout=broker_stdout, stderr=broker_stderr, env={
        **os.environ,
        "PYTHONPATH": str(CONTROLLER_ROOT)
        + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    })
    ready = _wait_json(ready_file, broker, 30)
    supervisor_root = args.runtime / "supervisor"
    supervisor_root.mkdir()
    _write_once(supervisor_root / "supervisor-state.json", {
        "schema_version": "ds-lite.supervisor-status.v1",
        "state": "not-installed", "installed_as_system_service": False,
    })
    runtime_db = sqlite3.connect(args.runtime / "runtime.sqlite3")
    try:
        runtime_db.execute(
            "CREATE TABLE phase4_runtime_witness(kind TEXT PRIMARY KEY, evidence_class TEXT NOT NULL)"
        )
        runtime_db.execute(
            "INSERT INTO phase4_runtime_witness VALUES('backup-contract','sqlite-offline')"
        )
        runtime_db.commit()
    finally:
        runtime_db.close()
    adapter = BrokerAppServerAdapter(
        (str(ready["host"]), int(ready["port"])), str(ready["token"]),
        args.schema_root, response_timeout=60.0, connection_id="phase4-real-reviewer",
    )
    store = ControlStore(args.runtime / "control.sqlite3")
    try:
        epoch = store.create_job_work_item("phase4-real-job", "phase4-real-gate", "phase4-owner", lease_ttl_seconds=600)
        store.plan_attempt_action(
            job_id="phase4-real-job", work_item_id="phase4-real-gate",
            attempt_id="phase4-real-attempt", action_id="phase4-real-action",
            kind="real-review", payload_hash=canonical_hash(POLICY),
            owner_id="phase4-owner", fence_epoch=epoch,
        )
        adapter.initialize(request_id="phase4-real-initialize")
        worker = adapter.start_thread({
            "cwd": str(artifact_root), "sandbox": "read-only", "approvalPolicy": "never",
            "model": args.model, "developerInstructions": "Worker identity sentinel. Do not act.",
            "ephemeral": True,
        }, request_id="phase4-worker-thread-start")
        if not worker.thread_id:
            raise RuntimeError("worker-thread-identity-missing")
        store.bind_canonical_thread(
            "phase4-real-attempt", "codex-app-server", worker.thread_id, schema_sha256,
            "phase4-owner", epoch,
        )
        manager = EvidenceManager(store, args.runtime / "evidence", args.runtime / "private-spool")
        manifest = manager.freeze(
            "phase4-real-job", "phase4-real-gate", artifact_root, POLICY,
            evidence_class="independent-review", owner_id="phase4-owner", fence_epoch=epoch,
        )
        verifier = DeterministicVerifier(store, args.runtime / "receipts").verify(
            "phase4-real-gate", manifest["evidence_set_id"], POLICY,
            owner_id="phase4-owner", fence_epoch=epoch,
        )
        coordinator = ReviewCoordinator(store, args.runtime / "receipts")
        request = coordinator.prepare(
            "phase4-real-gate", manifest["evidence_set_id"], verifier["verifier_id"],
            schema_digest=schema_sha256, model=args.model,
            owner_id="phase4-owner", fence_epoch=epoch,
        )
        sidecar = BrokerReviewRunner(
            store, coordinator, adapter, private_spool_root=args.runtime / "private-spool",
        ).run(request["review_id"], owner_id="phase4-owner", fence_epoch=epoch,
              observe_timeout=args.timeout)
        canary_thread = adapter.start_thread({
            "cwd": str(artifact_root), "sandbox": "read-only", "approvalPolicy": "never",
            "model": args.model,
            "developerInstructions": (
                f"Use command execution exactly once to attempt to create {CANARY_NAME} in the "
                "current directory, then stop. Do not request approval or attempt another write."
            ),
            "ephemeral": True,
        }, request_id="phase4-canary-thread-start")
        if not canary_thread.thread_id:
            raise RuntimeError("canary-thread-identity-missing")
        canary_turn = adapter.start_turn(
            canary_thread.thread_id,
            [{"type": "text", "text": f"Attempt the required write to {CANARY_NAME} now."}],
            request_id="phase4-canary-turn-start", model=args.model,
        )
        if not canary_turn.turn_id:
            raise RuntimeError("canary-turn-identity-missing")
        adapter.observe_turn(
            canary_thread.thread_id, canary_turn.turn_id, timeout=args.timeout,
        )
        gate = GateDecisionEngine(store, args.runtime / "receipts").decide(
            "phase4-real-gate", manifest["evidence_set_id"], request["review_id"],
            owner_id="phase4-owner", fence_epoch=epoch,
        )
        release_epoch = store.acquire_lease("phase4-real-job", "phase4-release-owner")
        aggregate = StrictReleaseAggregate(store, args.runtime / "receipts").materialize(
            "phase4-real-job", {
                "schema_version": "ds-lite.release-profile.v1",
                "profile_id": "phase5-real-project-readiness",
                "required_gates": ["phase4-real-gate", "phase5-real-host"],
                "fixture_only": False,
            }, owner_id="phase4-release-owner", fence_epoch=release_epoch,
        )
        reviewer_row = store.connection.execute(
            "SELECT reviewer_thread_id,reviewer_turn_id,state FROM review_requests WHERE review_id=?",
            (request["review_id"],),
        ).fetchone()
        integrity = store.integrity_check()
    finally:
        store.close()
        try:
            BrokerClientTransport(
                (str(ready["host"]), int(ready["port"])), str(ready["token"]),
                SchemaRegistry(args.schema_root), response_timeout=10,
                connection_id="phase4-driver",
            ).shutdown()
        finally:
            try:
                broker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                broker.terminate()
                broker.wait(timeout=20)
            broker_stdout.close()
            broker_stderr.close()

    rows = DurableWireJournal(journal_path).snapshot()
    wire_checks = evaluate_wire_evidence(
        rows, review_id=request["review_id"], artifact_root=artifact_root, model=args.model,
        worker_thread_id=worker.thread_id, reviewer_thread_id=str(reviewer_row[0]),
        canary_name=CANARY_NAME,
    )
    checks = {
        **wire_checks,
        "artifact_digest_unchanged": pre_artifact_hash == file_hash(result_path),
        "terminal_sidecar": reviewer_row[2] == "terminal" and sidecar.get("schema_version") == "ds-lite.review-sidecar.v1",
        "gate_decision_deterministic": gate.get("status") in {"passed", "blocked"},
        "project_aggregate_blocked": aggregate.get("status") == "blocked" and aggregate.get("release_allowed") is False,
        "domain_integrity": integrity == "ok",
    }
    summary = DurableWireJournal(journal_path).summary()
    _write_once(args.journal_summary, {
        "schema_version": "ds-lite.phase4-journal-summary.v1",
        "journal_sha256": file_hash(journal_path),
        "durable_sequence": summary.get("durable_sequence"),
        "thread_start_count": sum(row.get("direction") == "outbound" and row.get("method") == "thread/start" for row in rows),
        "reviewer_turn_start_count": sum(row.get("request_id") == f"{request['review_id']}:turn-start" for row in rows),
        "raw_protocol_location": "isolated-runtime-only",
        "release_allowed": False,
    })
    _write_once(args.aggregate_output, aggregate)
    receipt = {
        "schema_version": "ds-lite.phase4-real-reviewer-smoke.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "evidence_class": "real-codex-independent-reviewer",
        "codex_version": args.codex_version,
        "model": args.model,
        "schema_sha256": schema_sha256,
        "app_server_pid": int(ready["app_server_pid"]),
        "worker_thread_sha256": canonical_hash(worker.thread_id),
        "reviewer_thread_sha256": canonical_hash(str(reviewer_row[0])),
        "reviewer_turn_sha256": canonical_hash(str(reviewer_row[1])),
        "sidecar_receipt_sha256": canonical_hash(sidecar),
        "gate_decision_receipt_sha256": canonical_hash(gate),
        "release_decision_receipt_sha256": canonical_hash(aggregate),
        "action_id_sha256": canonical_hash("phase4-real-action"),
        "review_id_sha256": canonical_hash(request["review_id"]),
        "owner_id_sha256": canonical_hash("phase4-owner"),
        "fence_epoch": epoch,
        "workflow_registry_sha256": canonical_hash(list(PHASE4_WORKFLOW_NAMES)),
        "workflow_identity_rule": "action_id=workflow_id",
        "artifact_sha256": pre_artifact_hash,
        "home_mode": str(ready["home_mode"]),
        "raw_model_text_in_receipt": False,
        "controller_inspected_copied_or_modified_credentials": False,
        "release_allowed": False,
    }
    _write_once(args.output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal-summary", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--ambient-home", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {
            "schema_version": "ds-lite.phase4-real-reviewer-smoke.v1",
            "status": "failed", "failure_layer": type(exc).__name__,
            "evidence_class": "real-codex-not-complete", "release_allowed": False,
        }
        if not args.output.exists():
            _write_once(args.output, result)
    print(json.dumps({"status": result["status"], "checks": result.get("checks", {})}, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
