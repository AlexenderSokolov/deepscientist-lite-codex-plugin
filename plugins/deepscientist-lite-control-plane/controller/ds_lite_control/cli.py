from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .backup import backup_control_plane, restore_control_plane
from .broker import BrokerAppServerAdapter, DurableWireJournal, serve_broker
from .codex_actions import CodexActionRunner
from .dbos_bridge import DBOSBridge
from .receipts import ReceiptStore
from .failure_policy import FailureClassifier
from .evidence import EvidenceManager
from .release import GateDecisionEngine, StrictReleaseAggregate
from .review import BrokerReviewRunner, ReviewCoordinator
from .scheduler import DagScheduler
from .store import ControlStore
from .verification import DeterministicVerifier
from .runtime_pin import _version_key, schema_manifest_version, verify_runtime_selection
from .supervisor import (
    RepoSupervisor, read_supervisor_status, render_service_template,
    request_supervisor_stop,
)


VERIFIED_PYTHON = "3.13.5"
VERIFIED_PYTHON_BY_PLATFORM = {
    "windows-x86_64": "3.13.5",
    "linux-x86_64": "3.12.3",
}
VERIFIED_DBOS = "2.29.0"
CODEX_SCHEMA_DIGEST = "9e22b7c4174cdaa87fc3240bce6bfecf8855f263eddfed3e97e49cb165527afb"
CURRENT_CODEX_SCHEMA_DIGEST = "0e79541ba5af824864df3bd14c35ea2678009bce1a6864a3ce6213d9f0228509"


def doctor_report(*, python_version: str, dbos_version: str, schema_version: int,
                  integrity: str, codex_schema_digest: str,
                  protocol_present: bool = True, broker_configured: bool = False,
                  broker_journal_valid: bool = True,
                  expected_codex_schema_digest: str | None = None,
                  codex_binary_version: str | None = None,
                  expected_codex_version: str | None = None,
                  codex_schema_valid: bool = True,
                  runtime_platform: str | None = None) -> dict[str, Any]:
    expected_python = VERIFIED_PYTHON_BY_PLATFORM.get(runtime_platform, VERIFIED_PYTHON)
    schema_matches = (
        codex_schema_digest == expected_codex_schema_digest
        if expected_codex_schema_digest is not None
        else codex_schema_digest in {CODEX_SCHEMA_DIGEST, CURRENT_CODEX_SCHEMA_DIGEST}
    )
    binary_matches = (
        codex_binary_version == expected_codex_version
        if expected_codex_version is not None
        else True
    )
    checks = {
        "python": python_version == expected_python,
        "dbos": dbos_version == VERIFIED_DBOS,
        "domain_schema": schema_version == 4,
        "protocol_journal": protocol_present,
        "broker_journal": not broker_configured or broker_journal_valid,
        "domain_integrity": integrity == "ok",
        "codex_binary": binary_matches,
        "codex_schema": schema_matches and codex_schema_valid,
    }
    return {
        "schema_version": "ds-lite.control-doctor.v1",
        "checks": checks,
        "python_version": python_version,
        "runtime_platform": runtime_platform,
        "dbos_version": dbos_version,
        "plugin_hooks_default": "disabled",
        "managed_allowed": all(checks.values()),
        "release_allowed": False,
        "broker": {
            "configured": broker_configured,
            "journal_valid": broker_journal_valid if broker_configured else None,
        },
    }


def _paths(project: Path) -> tuple[Path, Path, Path]:
    root = project.resolve() / ".ds-lite"
    return root / "control.sqlite3", root / "runtime.sqlite3", root / "receipts"


def _dbos_version() -> str:
    try:
        return importlib.metadata.version("dbos")
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def resolve_schema_root(explicit: Path | None = None, *, codex_version: str | None = None) -> Path:
    """Choose explicit, bundled, then source-development schema roots."""
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_dir():
            raise ValueError("explicit schema root is unavailable")
        return candidate
    bundled_root = Path(__file__).resolve().parents[2] / "schemas" / "codex"
    if codex_version is None:
        candidates = [
            path for path in bundled_root.iterdir()
            if path.is_dir() and schema_manifest_version(path) is not None
        ] if bundled_root.is_dir() else []
        if candidates:
            bundled = max(candidates, key=lambda path: _version_key(schema_manifest_version(path)))
            return bundled
    else:
        bundled = bundled_root / codex_version
        if bundled.is_dir():
            return bundled
    if os.environ.get("DS_LITE_SOURCE_DEVELOPMENT") == "1":
        fallback_root = Path(__file__).resolve().parents[3] / "deepscientist-lite-core" / "schemas" / "codex"
        if codex_version is None:
            candidates = [
                path for path in fallback_root.iterdir()
                if path.is_dir() and schema_manifest_version(path) is not None
            ] if fallback_root.is_dir() else []
            if candidates:
                return max(candidates, key=lambda path: _version_key(schema_manifest_version(path)))
        else:
            fallback = fallback_root / codex_version
            if fallback.is_dir():
                return fallback
    raise ValueError("control-plane schema root is unavailable")


def _observed_schema_digest(schema_root: Path | None = None) -> str:
    sums = resolve_schema_root(schema_root) / "SHA256SUMS"
    return hashlib.sha256(sums.read_bytes()).hexdigest() if sums.is_file() else "missing"


def _run_once(args: argparse.Namespace) -> dict[str, Any]:
    control_path, runtime_path, receipt_root = _paths(args.project)
    store = ControlStore(control_path)
    bridge = None
    try:
        epoch = store.create_job_work_item(args.job_id, args.work_item_id, args.owner_id)
        payload_hash = hashlib.sha256(args.action_id.encode()).hexdigest()
        store.plan_attempt_action(
            job_id=args.job_id, work_item_id=args.work_item_id,
            attempt_id=f"attempt-{args.action_id}", action_id=args.action_id,
            kind="fake-turn", payload_hash=payload_hash,
            owner_id=args.owner_id, fence_epoch=epoch,
        )
        bridge = DBOSBridge(runtime_path)
        if store.action_state(args.action_id) == "terminal":
            handle = bridge.retrieve(args.action_id)
        else:
            store.transition_outbox(args.action_id, "workflow_submitting", args.owner_id, epoch)
            handle = bridge.start_action(args.action_id, control_path, args.owner_id, epoch)
            store.attach_workflow(args.action_id, "run_action_v1", args.owner_id, epoch, "active")
        result = handle.get_result()
        store.attach_workflow(args.action_id, "run_action_v1", args.owner_id, epoch, "SUCCESS")
        receipt_store = ReceiptStore(receipt_root, store)
        payload = receipt_store.terminal_payload(args.action_id, args.owner_id, epoch)
        receipt = receipt_store.write_and_index(
            f"terminal-{args.action_id}", payload, args.owner_id, epoch
        )
        return {"status": "completed", "workflow_id": handle.workflow_id,
                "workflow_result": result, "receipt_hash": receipt["content_hash"],
                "release_allowed": False}
    finally:
        if bridge is not None:
            bridge.close()
        store.close()


def _broker_connection(args: argparse.Namespace) -> tuple[tuple[str, int], str]:
    if getattr(args, "broker_ready", None):
        ready = json.loads(args.broker_ready.read_text(encoding="utf-8"))
        return (str(ready["host"]), int(ready["port"])), str(ready["token"])
    if not args.broker_endpoint or not args.broker_token_file:
        raise ValueError("broker connection requires --broker-ready or endpoint plus token file")
    host, separator, port = args.broker_endpoint.rpartition(":")
    if not separator or not host:
        raise ValueError("broker endpoint must be host:port")
    token_path = args.broker_token_file
    token_text = token_path.read_text(encoding="utf-8").strip()
    try:
        token_payload = json.loads(token_text)
        token = str(token_payload["token"])
    except (json.JSONDecodeError, TypeError, KeyError):
        token = token_text
    return (host, int(port)), token


def _run_codex_once(args: argparse.Namespace) -> dict[str, Any]:
    endpoint, token = _broker_connection(args)
    control_path, _, _ = _paths(args.project)
    store = ControlStore(control_path)
    try:
        epoch = store.create_job_work_item(args.job_id, args.work_item_id, args.owner_id)
        attempt_id = f"attempt-{args.action_id}"
        payload = [{"type": "text", "text": args.input_text}]
        store.plan_attempt_action(
            job_id=args.job_id, work_item_id=args.work_item_id, attempt_id=attempt_id,
            action_id=args.action_id, kind="codex-turn",
            payload_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            owner_id=args.owner_id, fence_epoch=epoch,
        )
        store.bind_canonical_thread(
            attempt_id, "codex-app-server-broker", args.thread_id, CODEX_SCHEMA_DIGEST,
            args.owner_id, epoch,
        )
        adapter = BrokerAppServerAdapter(
            endpoint, token, args.schema_root, response_timeout=args.response_timeout,
            connection_id=args.owner_id,
        )
        runner = CodexActionRunner(store, adapter)
        request_id = f"{args.action_id}:turn-start"
        try:
            request = store.rpc_request(request_id)
        except ValueError:
            request = None
        if request is not None and request["state"] == "ambiguous":
            observation = runner.reconcile_turn(args.action_id, args.owner_id, epoch)
        else:
            if args.drop_response:
                adapter.transport.drop_next_response("turn/start")
            observation = runner.dispatch_turn(
                args.action_id, attempt_id, payload, args.owner_id, epoch,
            )
        return {
            "status": observation.disposition,
            "evidence_class": "real-app-server-broker",
            "action_id": args.action_id,
            "thread_id": observation.thread_id,
            "turn_id": observation.turn_id,
            "release_allowed": False,
        }
    finally:
        store.close()


def _serve_scheduler(args: argparse.Namespace) -> dict[str, Any]:
    control_path, _, _ = _paths(args.project)
    store = ControlStore(control_path)
    scheduler = DagScheduler(
        store, FailureClassifier(seed=args.seed),
        max_concurrency=args.max_concurrency, retry_concurrency=args.retry_concurrency,
    )
    try:
        while True:
            scheduler.requeue_due(args.job_id)
            recovered = scheduler.recover_expired(args.job_id, args.owner_id)
            claims = scheduler.claim_ready(args.job_id, args.owner_id)
            result = {
                "status": "scheduled",
                "job_id": args.job_id,
                "claimed_action_ids": [claim.action_id for claim in claims],
                "recovered_action_ids": [claim.action_id for claim in recovered],
                "evidence_class": "domain-scheduler",
                "release_allowed": False,
            }
            if args.once:
                return result
            time.sleep(args.poll_seconds)
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ds_lite_control")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--project", type=Path, default=Path.cwd())
    doctor.add_argument("--codex-bin", type=Path)
    doctor.add_argument("--schema-root", type=Path)
    doctor.add_argument("--codex-version")
    doctor.add_argument("--codex-platform")
    broker = sub.add_parser("broker")
    broker_sub = broker.add_subparsers(dest="broker_command", required=True)
    serve = broker_sub.add_parser("serve")
    serve.add_argument("--codex-bin", type=Path, required=True)
    serve.add_argument("--home", type=Path, required=True)
    serve.add_argument("--schema-root", type=Path, required=True)
    serve.add_argument("--journal", type=Path, required=True)
    serve.add_argument("--ready-file", type=Path, required=True)
    serve.add_argument("--host-response-timeout", type=float, default=120.0)
    serve.add_argument("--ambient-home", action="store_true")
    control = sub.add_parser("control")
    control_sub = control.add_subparsers(dest="control_command", required=True)
    run = control_sub.add_parser("run")
    run.add_argument("job_id")
    run.add_argument("--project", required=True, type=Path)
    run.add_argument("--work-item-id", default="work-1")
    run.add_argument("--action-id", default="action-1")
    run.add_argument("--owner-id", default="controller-managed")
    run.add_argument("--once", action="store_true")
    run.add_argument("--broker-endpoint")
    run.add_argument("--broker-ready", type=Path)
    run.add_argument("--broker-token-file", type=Path)
    run.add_argument("--schema-root", type=Path)
    run.add_argument("--thread-id")
    run.add_argument("--input-text", default="Return OK without tools.")
    run.add_argument("--response-timeout", type=float, default=120.0)
    run.add_argument("--drop-response", action="store_true")
    control_serve = control_sub.add_parser("serve")
    control_serve.add_argument("job_id")
    control_serve.add_argument("--project", required=True, type=Path)
    control_serve.add_argument("--owner-id", default="controller-supervised")
    control_serve.add_argument("--max-concurrency", type=int, default=2)
    control_serve.add_argument("--retry-concurrency", type=int, default=1)
    control_serve.add_argument("--seed", type=int, default=20260731)
    control_serve.add_argument("--poll-seconds", type=float, default=1.0)
    control_serve.add_argument("--once", action="store_true")
    status = control_sub.add_parser("status")
    status.add_argument("job_id")
    status.add_argument("--project", required=True, type=Path)
    status.add_argument("--json", action="store_true")
    backup = control_sub.add_parser("backup")
    backup.add_argument("--project", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)
    restore = control_sub.add_parser("restore")
    restore.add_argument("--backup", required=True, type=Path)
    restore.add_argument("--output", required=True, type=Path)
    evidence = control_sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    freeze = evidence_sub.add_parser("freeze")
    freeze.add_argument("job_id")
    freeze.add_argument("gate_id")
    freeze.add_argument("--project", required=True, type=Path)
    freeze.add_argument("--artifact-root", required=True, type=Path)
    freeze.add_argument("--policy", required=True, type=Path)
    freeze.add_argument("--evidence-class", default="offline",
                        choices=("offline", "real-host", "cross-epoch", "independent-review"))
    freeze.add_argument("--owner-id", default="controller-managed")
    verify = control_sub.add_parser("verify")
    verify.add_argument("job_id")
    verify.add_argument("gate_id")
    verify.add_argument("--project", required=True, type=Path)
    verify.add_argument("--evidence-set", required=True)
    verify.add_argument("--policy", required=True, type=Path)
    verify.add_argument("--owner-id", default="controller-managed")
    review = control_sub.add_parser("review")
    review.add_argument("job_id")
    review.add_argument("gate_id")
    review.add_argument("--project", required=True, type=Path)
    review.add_argument("--evidence-set", required=True)
    review.add_argument("--broker-endpoint", required=True)
    review.add_argument("--broker-token-file", required=True, type=Path)
    review.add_argument("--schema-root", required=True, type=Path)
    review.add_argument("--model", default="gpt-5.6-sol")
    review.add_argument("--owner-id", default="controller-managed")
    review.add_argument("--response-timeout", type=float, default=120.0)
    aggregate = control_sub.add_parser("aggregate")
    aggregate.add_argument("job_id")
    aggregate.add_argument("--project", required=True, type=Path)
    aggregate.add_argument("--profile", required=True, type=Path)
    aggregate.add_argument("--owner-id", default="controller-managed")
    supervisor = sub.add_parser("supervisor")
    supervisor_sub = supervisor.add_subparsers(dest="supervisor_command", required=True)
    supervisor_run = supervisor_sub.add_parser("run")
    supervisor_run.add_argument("--project", required=True, type=Path)
    supervisor_run.add_argument("--job-id", required=True)
    supervisor_run.add_argument("--supervisor-id", default="ds-lite-supervisor")
    supervisor_run.add_argument("--owner-id", default="controller-supervised")
    supervisor_run.add_argument("--worker-command-file", type=Path)
    supervisor_run.add_argument("--poll-seconds", type=float, default=1.0)
    supervisor_status = supervisor_sub.add_parser("status")
    supervisor_status.add_argument("--project", required=True, type=Path)
    supervisor_stop = supervisor_sub.add_parser("stop")
    supervisor_stop.add_argument("--project", required=True, type=Path)
    supervisor_stop.add_argument("--supervisor-id", default="ds-lite-supervisor")
    supervisor_render = supervisor_sub.add_parser("render")
    supervisor_render.add_argument("--project", required=True, type=Path)
    supervisor_render.add_argument("--platform", choices=("windows", "systemd"), required=True)
    supervisor_render.add_argument("--output", required=True, type=Path)
    supervisor_render.add_argument("--python-bin", type=Path, default=Path(sys.executable))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "broker":
        return serve_broker(
            codex_bin=args.codex_bin, home=args.home, schema_root=args.schema_root,
            journal_path=args.journal, ready_file=args.ready_file,
            host_response_timeout=args.host_response_timeout,
            ambient_home=args.ambient_home,
        )
    if args.command == "supervisor":
        runtime_root = args.project.resolve() / ".ds-lite" / "supervisor"
        if args.supervisor_command == "status":
            print(json.dumps(read_supervisor_status(runtime_root), ensure_ascii=True, sort_keys=True))
            return 0
        if args.supervisor_command == "stop":
            path = request_supervisor_stop(runtime_root, args.supervisor_id)
            print(json.dumps({
                "status": "stop-requested",
                "request_ref": path.relative_to(args.project.resolve()).as_posix(),
                "release_allowed": False,
            }, ensure_ascii=True, sort_keys=True))
            return 0
        if args.supervisor_command == "render":
            output = render_service_template(
                args.platform, args.output, project=args.project, python_bin=args.python_bin,
            )
            print(json.dumps({
                "status": "rendered-not-installed", "path": str(output),
                "release_allowed": False,
            }, ensure_ascii=True, sort_keys=True))
            return 0
        control_path, _, _ = _paths(args.project)
        store = ControlStore(control_path)
        try:
            if args.worker_command_file is not None:
                worker_command = json.loads(args.worker_command_file.read_text(encoding="utf-8"))
                if not isinstance(worker_command, list) or not worker_command or not all(
                    isinstance(item, str) and item for item in worker_command
                ):
                    raise ValueError("worker command file must contain a non-empty string array")
            else:
                worker_command = [
                    sys.executable, "-m", "ds_lite_control", "control", "serve", args.job_id,
                    "--project", str(args.project.resolve()), "--owner-id", args.owner_id,
                ]
            service = RepoSupervisor(
                store, runtime_root=runtime_root, supervisor_id=args.supervisor_id,
                owner_id=args.owner_id, worker_command=worker_command,
            )
            return service.run(poll_seconds=args.poll_seconds)
        finally:
            store.close()
    if args.command == "doctor":
        control_path, _, _ = _paths(args.project)
        journal_path = control_path.parent / "protocol-journal.jsonl"
        broker_metadata = control_path.parent / "broker-metadata.json"
        broker_configured = broker_metadata.is_file()
        broker_journal_valid = False
        if broker_configured and journal_path.is_file():
            try:
                broker_journal_valid = DurableWireJournal(journal_path).verify()["valid"]
            except (OSError, ValueError, json.JSONDecodeError):
                broker_journal_valid = False
        selected = (args.codex_bin, args.schema_root, args.codex_version, args.codex_platform)
        if any(item is not None for item in selected) and not all(item is not None for item in selected):
            raise ValueError(
                "doctor runtime selection requires codex bin, schema root, version, and platform"
            )
        runtime = None
        if all(item is not None for item in selected):
            runtime = verify_runtime_selection(
                args.codex_bin, args.schema_root, expected_version=args.codex_version,
                expected_platform=args.codex_platform,
            )
        store = ControlStore(control_path)
        try:
            report = doctor_report(
                python_version=platform.python_version(), dbos_version=_dbos_version(),
                schema_version=store.schema_version, integrity=store.integrity_check(),
                protocol_present=journal_path.is_file(),
                codex_schema_digest=(
                    runtime["schema"]["observed_bundle_digest"]
                    if runtime is not None else _observed_schema_digest(args.schema_root)
                ),
                expected_codex_schema_digest=(
                    runtime["schema"]["expected_bundle_digest"]
                    if runtime is not None else None
                ),
                codex_binary_version=(runtime["codex_binary_version"] if runtime is not None else None),
                expected_codex_version=(runtime["expected_codex_version"] if runtime is not None else None),
                codex_schema_valid=(runtime["schema"]["valid"] if runtime is not None else True),
                runtime_platform=(runtime["expected_platform"] if runtime is not None else None),
                broker_configured=broker_configured,
                broker_journal_valid=broker_journal_valid,
            )
        finally:
            store.close()
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0 if report["managed_allowed"] else 2
    if args.control_command == "run":
        if platform.python_version() != VERIFIED_PYTHON or _dbos_version() != VERIFIED_DBOS:
            print(json.dumps({"status": "blocked", "failure_layer": "runtime-init", "release_allowed": False}))
            return 2
        using_broker = bool(args.broker_endpoint or args.broker_ready)
        if using_broker and (args.schema_root is None or not args.thread_id):
            print(json.dumps({"status": "blocked", "failure_layer": "broker-config", "release_allowed": False}))
            return 2
        print(json.dumps(_run_codex_once(args) if using_broker else _run_once(args), ensure_ascii=True, sort_keys=True))
        return 0
    if args.control_command == "serve":
        print(json.dumps(_serve_scheduler(args), ensure_ascii=True, sort_keys=True))
        return 0
    if args.control_command == "evidence":
        control_path, _, _ = _paths(args.project)
        state_root = control_path.parent
        store = ControlStore(control_path)
        try:
            epoch = store.create_job_work_item(args.job_id, args.gate_id, args.owner_id)
            policy = json.loads(args.policy.read_text(encoding="utf-8-sig"))
            result = EvidenceManager(
                store, state_root / "evidence", state_root / "private-spool"
            ).freeze(
                args.job_id, args.gate_id, args.artifact_root, policy,
                evidence_class=args.evidence_class, owner_id=args.owner_id,
                fence_epoch=epoch,
            )
        finally:
            store.close()
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    if args.control_command == "verify":
        control_path, _, receipt_root = _paths(args.project)
        store = ControlStore(control_path)
        try:
            epoch = store.create_job_work_item(args.job_id, args.gate_id, args.owner_id)
            policy = json.loads(args.policy.read_text(encoding="utf-8-sig"))
            result = DeterministicVerifier(store, receipt_root).verify(
                args.gate_id, args.evidence_set, policy,
                owner_id=args.owner_id, fence_epoch=epoch,
            )
        finally:
            store.close()
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["status"] == "passed" else 2
    if args.control_command == "aggregate":
        control_path, _, receipt_root = _paths(args.project)
        store = ControlStore(control_path)
        try:
            profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
            epoch = store.acquire_lease(args.job_id, args.owner_id)
            result = StrictReleaseAggregate(store, receipt_root).materialize(
                args.job_id, profile, owner_id=args.owner_id, fence_epoch=epoch,
            )
        finally:
            store.close()
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0 if result["release_allowed"] else 2
    if args.control_command == "review":
        control_path, _, receipt_root = _paths(args.project)
        store = ControlStore(control_path)
        try:
            epoch = store.create_job_work_item(args.job_id, args.gate_id, args.owner_id)
            verifier = store.connection.execute(
                "SELECT verifier_id FROM verifier_runs WHERE work_item_id=? AND evidence_set_id=? "
                "ORDER BY created_at DESC LIMIT 1", (args.gate_id, args.evidence_set)
            ).fetchone()
            if verifier is None:
                raise ValueError("review requires a terminal verifier")
            result = ReviewCoordinator(store, receipt_root).prepare(
                args.gate_id, args.evidence_set, str(verifier[0]),
                schema_digest=CURRENT_CODEX_SCHEMA_DIGEST, model=args.model,
                owner_id=args.owner_id, fence_epoch=epoch,
            )
            endpoint, token = _broker_connection(args)
            coordinator = ReviewCoordinator(store, receipt_root)
            adapter = BrokerAppServerAdapter(
                endpoint, token, args.schema_root,
                response_timeout=args.response_timeout, connection_id=args.owner_id,
            )
            sidecar = BrokerReviewRunner(
                store, coordinator, adapter,
                private_spool_root=control_path.parent / "private-spool",
            ).run(
                result["review_id"], owner_id=args.owner_id, fence_epoch=epoch,
                observe_timeout=args.response_timeout,
            )
            decision = GateDecisionEngine(store, receipt_root).decide(
                args.gate_id, args.evidence_set, result["review_id"],
                owner_id=args.owner_id, fence_epoch=epoch,
            )
        finally:
            store.close()
        result = {
            **result,
            "status": "terminal",
            "review_verdict": sidecar["verdict"],
            "sidecar_receipt_id": sidecar["receipt_id"],
            "gate_decision": decision["status"],
            "gate_decision_receipt_id": decision["receipt_id"],
            "release_allowed": False,
        }
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 0
    if args.control_command == "status":
        control_path, _, _ = _paths(args.project)
        store = ControlStore(control_path)
        try:
            result = store.project_job_status(
                args.job_id, supervisor_id="ds-lite-supervisor"
            )
        finally:
            store.close()
        journal_path = control_path.parent / "protocol-journal.jsonl"
        metadata_path = control_path.parent / "broker-metadata.json"
        if journal_path.is_file() and metadata_path.is_file():
            try:
                result["broker"] = DurableWireJournal(journal_path).summary()
            except (OSError, ValueError, json.JSONDecodeError):
                result["broker"] = {"valid": False}
        print(json.dumps(result, ensure_ascii=True, sort_keys=True) if args.json else
              f"job={result['job_id']} gates={len(result['gates'])} "
              f"continuation_confirmed={str(result['continuation_confirmed']).lower()}")
        return 0
    if args.control_command == "backup":
        print(json.dumps(backup_control_plane(args.project.resolve() / ".ds-lite", args.output), sort_keys=True))
        return 0
    print(json.dumps(restore_control_plane(args.backup, args.output), sort_keys=True))
    return 0
