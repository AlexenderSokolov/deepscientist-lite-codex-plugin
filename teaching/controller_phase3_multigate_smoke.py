from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.broker import BrokerClientTransport, DurableWireJournal, SchemaRegistry
from ds_lite_control.broker import BrokerAppServerAdapter
from ds_lite_control.app_server import RpcObservation
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler, GateClaim
from ds_lite_control.store import ControlStore
from teaching.controller_model_catalog_probe import summarize as summarize_model_catalog


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def select_requested_model(catalog: list[dict[str, Any]], requested: str) -> str:
    matches = [
        str(row["model"])
        for row in catalog
        if isinstance(row, dict)
        and row.get("model") == requested
        and row.get("hidden") is False
    ]
    if matches != [requested]:
        raise RuntimeError("requested-model-not-visible-in-catalog")
    return requested


def record_terminal_failure(
    store: ControlStore, claim: GateClaim, observation: RpcObservation,
) -> dict[str, Any]:
    if observation.disposition != "failed":
        raise ValueError("terminal failure observation required")
    decision = DagScheduler(store, FailureClassifier(seed=20260731)).record_failure(
        claim,
        layer="provider-unavailable",
        evidence_hash=_hash(observation.turn_id or claim.action_id),
    )
    return {
        "disposition": decision.disposition,
        "next_action": decision.next_action,
        "signature": decision.signature,
    }


def evaluate_records(
    records: dict[str, dict[str, Any]], *, turn_start_count: int,
    dropped_response_count: int, side_effect_count: int,
) -> dict[str, Any]:
    first = records["gate_a_drop"]
    second = records["gate_b"]
    recovered = records["gate_a_recover"]
    checks = {
        "single_app_server": len({row["app_server_pid"] for row in records.values()}) == 1,
        "three_controller_processes": len({row["controller_pid"] for row in records.values()}) == 3,
        "independent_canonical_threads": first["thread_id"] != second["thread_id"],
        "gate_a_same_thread_after_restart": first["thread_id"] == recovered["thread_id"],
        "gate_a_same_turn_after_restart": first["turn_id"] == recovered["turn_id"],
        "ttl_owner_takeover": (
            first["owner_id"] != recovered["owner_id"]
            and int(recovered["fence_epoch"]) > int(first["fence_epoch"])
        ),
        "gate_a_response_was_dropped": first["disposition"] == "ambiguous" and dropped_response_count >= 1,
        "gate_b_completed_while_gate_a_unresolved": second["disposition"] == "terminal",
        "gate_a_reconciled_terminal": recovered["disposition"] == "terminal",
        "exactly_two_turn_starts": turn_start_count == 2,
        "single_tool_side_effect": side_effect_count == 1,
    }
    return {"passed": all(checks.values()), "checks": checks}


def reconcile_dropped_turn_identity(
    records: dict[str, dict[str, Any]], rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    reconciled = copy.deepcopy(records)
    first = reconciled["gate_a_drop"]
    recovered = reconciled["gate_a_recover"]
    request_id = f"{first['action_id']}:turn-start"
    host_turns = {
        str(row["turn_id"])
        for row in rows
        if row.get("direction") == "inbound"
        and row.get("request_id") == request_id
        and row.get("host_observed") is True
        and row.get("turn_id")
    }
    if len(host_turns) != 1:
        raise RuntimeError("dropped-response-turn-identity-not-unique")
    host_turn = next(iter(host_turns))
    if recovered.get("turn_id") != host_turn:
        raise RuntimeError("recovered-turn-conflicts-with-host-response")
    if first.get("turn_id") not in {None, host_turn}:
        raise RuntimeError("initial-turn-conflicts-with-host-response")
    first["turn_id"] = host_turn
    return reconciled


def _wait_json(path: Path, process: subprocess.Popen, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"worker-exited:{process.returncode}:{path.name}")
        time.sleep(0.05)
    raise TimeoutError(path.name)


def _worker_command(args: argparse.Namespace, mode: str, output: Path, worker_id: str, hold: bool) -> list[str]:
    return [
        sys.executable, str(ROOT / "teaching" / "controller_phase3_multigate_worker.py"),
        "--mode", mode, "--ready-file", str(args.runtime / "broker-ready.json"),
        "--manifest", str(args.runtime / "claims.json"),
        "--domain", str(args.runtime / "control.sqlite3"),
        "--schema-root", str(args.schema_root), "--workspace", str(args.task_workspace),
        "--side-effect-root", str(args.runtime / "side-effect"),
        "--output", str(output), "--worker-id", worker_id,
        *(["--hold-after"] if hold else []),
    ]


def _launch_worker(
    args: argparse.Namespace, mode: str, worker_id: str, *, hold: bool,
) -> tuple[dict[str, Any], int]:
    output = args.runtime / f"{worker_id}.json"
    with (args.runtime / f"{worker_id}.stdout.log").open("x", encoding="utf-8") as stdout_log, \
            (args.runtime / f"{worker_id}.stderr.log").open("x", encoding="utf-8") as stderr_log:
        process = subprocess.Popen(
            _worker_command(args, mode, output, worker_id, hold),
            stdout=stdout_log, stderr=stderr_log,
            env={
                **os.environ,
                "PYTHONPATH": str(CONTROLLER_ROOT)
                + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
            },
        )
        record = _wait_json(output, process, 300)
        pid = process.pid
        if hold:
            process.terminate()
            process.wait(timeout=20)
        elif process.wait(timeout=20) != 0:
            raise RuntimeError(f"worker-failed:{worker_id}")
    return record, pid


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime.exists() or args.output.exists() or args.journal_summary.exists():
        raise FileExistsError("phase3 real smoke paths must be new")
    args.runtime.mkdir(parents=True, exist_ok=False)
    args.task_workspace.mkdir(parents=True, exist_ok=True)
    version = subprocess.run(
        [str(args.codex_bin.resolve()), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    ).stdout.strip()
    if version != f"codex-cli {args.codex_version}":
        raise RuntimeError("pinned-codex-version-mismatch")
    schema_bundle = args.schema_root / "codex_app_server_protocol.v2.schemas.json"
    if not schema_bundle.is_file():
        raise RuntimeError("generated-schema-bundle-missing")
    schema_sha256 = hashlib.sha256(schema_bundle.read_bytes()).hexdigest()

    store = ControlStore(args.runtime / "control.sqlite3")
    try:
        scheduler = DagScheduler(store, FailureClassifier(seed=20260731))
        scheduler.register_job(
            "phase3-real-job",
            [
                {"id": "phase3-real-gate-a", "type": "experiment", "priority": 2,
                 "evidence_class": "real-app-server"},
                {"id": "phase3-real-gate-b", "type": "analysis", "priority": 1,
                 "evidence_class": "real-app-server"},
            ],
            [],
        )
        claims = scheduler.claim_ready("phase3-real-job", "phase3-real-owner")
        for claim in claims:
            store.heartbeat_lease(
                claim.work_item_id, claim.owner_id, claim.fence_epoch, ttl_seconds=600
            )
        by_id = {claim.work_item_id: claim for claim in claims}
        claims_payload = {
            "gate_a": asdict(by_id["phase3-real-gate-a"]),
            "gate_b": asdict(by_id["phase3-real-gate-b"]),
        }
    finally:
        store.close()

    ready_file = args.runtime / "broker-ready.json"
    journal_path = args.runtime / "protocol-journal.jsonl"
    broker_stdout = (args.runtime / "broker.stdout.log").open("x", encoding="utf-8")
    broker_stderr = (args.runtime / "broker.stderr.log").open("x", encoding="utf-8")
    broker = subprocess.Popen([
        sys.executable, "-m", "ds_lite_control", "broker", "serve",
        "--codex-bin", str(args.codex_bin), "--home", str(args.runtime / "codex-home"),
        "--schema-root", str(args.schema_root), "--journal", str(journal_path),
        "--ready-file", str(ready_file),
        *(["--ambient-home"] if args.ambient_home else []),
    ], stdout=broker_stdout, stderr=broker_stderr, env={
        **os.environ,
        "PYTHONPATH": str(CONTROLLER_ROOT)
        + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    })
    ready = _wait_json(ready_file, broker, 30)
    try:
        catalog_adapter = BrokerAppServerAdapter(
            (str(ready["host"]), int(ready["port"])), str(ready["token"]),
            args.schema_root, response_timeout=30.0, connection_id="phase3-catalog",
        )
        catalog_adapter.initialize(request_id="phase3-real-initialize")
        catalog_observation = catalog_adapter.list_models(
            include_hidden=True, request_id="phase3-real-model-list",
        )
        if catalog_observation.response is None:
            raise RuntimeError("model-catalog-response-missing")
        model_catalog = summarize_model_catalog(catalog_observation.response)
        selected_model = select_requested_model(model_catalog["models"], args.model)
        claims_payload.update({
            "model": selected_model,
            "model_catalog_sha256": model_catalog["catalog_sha256"],
            "codex_version": args.codex_version,
        })
        _write_once(args.runtime / "claims.json", claims_payload)
        gate_a, pid_a = _launch_worker(args, "gate-a-drop", "gate-a-drop", hold=True)
        gate_b, pid_b = _launch_worker(args, "gate-b", "gate-b", hold=False)
        recovered, pid_c = _launch_worker(args, "gate-a-recover", "gate-a-recover", hold=False)
        records = {
            "gate_a_drop": gate_a,
            "gate_b": gate_b,
            "gate_a_recover": recovered,
        }
    finally:
        try:
            client = BrokerClientTransport(
                (str(ready["host"]), int(ready["port"])), str(ready["token"]),
                SchemaRegistry(args.schema_root), response_timeout=10,
                connection_id="phase3-driver",
            )
            client.shutdown()
        finally:
            try:
                broker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                broker.terminate()
                broker.wait(timeout=20)
            broker_stdout.close()
            broker_stderr.close()

    journal = DurableWireJournal(journal_path)
    rows = journal.snapshot()
    records = reconcile_dropped_turn_identity(records, rows)
    gate_a = records["gate_a_drop"]
    gate_b = records["gate_b"]
    turn_start_count = sum(
        row.get("direction") == "outbound" and row.get("method") == "turn/start"
        for row in rows
    )
    summary = journal.summary()
    invocation_path = args.runtime / "side-effect" / "side-effect-invocations.jsonl"
    side_effect_count = len(invocation_path.read_text(encoding="utf-8").splitlines()) if invocation_path.is_file() else 0
    decision = evaluate_records(
        records, turn_start_count=turn_start_count,
        dropped_response_count=int(summary["dropped_response_count"]),
        side_effect_count=side_effect_count,
    )
    store = ControlStore(args.runtime / "control.sqlite3")
    try:
        domain_terminal = all(
            store.work_item(gate)["state"] == "terminal"
            for gate in ("phase3-real-gate-a", "phase3-real-gate-b")
        )
        domain_integrity = store.integrity_check()
    finally:
        store.close()
    decision["checks"]["domain_terminal"] = domain_terminal
    decision["checks"]["domain_integrity"] = domain_integrity == "ok"
    decision["passed"] = all(decision["checks"].values())
    journal_receipt = {
        "schema_version": "ds-lite.phase3-journal-summary.v1",
        **summary,
        "turn_start_count": turn_start_count,
        "app_server_pid": int(ready["app_server_pid"]),
        "release_allowed": False,
    }
    _write_once(args.journal_summary, journal_receipt)
    receipt = {
        "schema_version": "ds-lite.phase3-real-multigate-smoke.v1",
        "status": "passed" if decision["passed"] else "failed",
        "failure_layer": "none" if decision["passed"] else "real-host-observation",
        "checks": decision["checks"],
        "evidence_class": "real-app-server-external-controller-processes",
        "app_server_pid": int(ready["app_server_pid"]),
        "controller_pids": [pid_a, pid_b, pid_c],
        "action_id_sha256": [_hash(record["action_id"]) for record in records.values()],
        "thread_id_sha256": [_hash(gate_a["thread_id"]), _hash(gate_b["thread_id"])],
        "turn_id_sha256": [_hash(gate_a["turn_id"]), _hash(gate_b["turn_id"])],
        "turn_start_count": turn_start_count,
        "dropped_response_count": int(summary["dropped_response_count"]),
        "side_effect_invocation_count": side_effect_count,
        "model": selected_model,
        "codex_version": args.codex_version,
        "model_catalog_sha256": model_catalog["catalog_sha256"],
        "schema_sha256": schema_sha256,
        "home_mode": str(ready["home_mode"]),
        "used_last": False,
        "implicit_thread_start_after_failure": False,
        "release_allowed": False,
    }
    _write_once(args.output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--task-workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal-summary", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--ambient-home", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {
            "schema_version": "ds-lite.phase3-real-multigate-smoke.v1",
            "status": "failed", "failure_layer": type(exc).__name__,
            "evidence_class": "real-app-server-not-complete",
            "release_allowed": False,
        }
        if not args.output.exists():
            _write_once(args.output, result)
    print(json.dumps({"status": result["status"], "checks": result.get("checks", {})}, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
