from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerAdapter, ProtocolSpool  # noqa: E402
from ds_lite_control.dbos_bridge import DBOSBridge, PHASE5_CODEX_VERSION  # noqa: E402
from ds_lite_control.runtime_pin import verify_runtime_selection  # noqa: E402
from ds_lite_control.store import ControlStore  # noqa: E402


ACTION_ID = "phase5-real-codex-action-v2"
ATTEMPT_ID = "phase5-real-codex-attempt-v2"
WORK_ITEM_ID = "phase5-real-codex-gate-v2"
JOB_ID = "phase5-real-codex-job-v2"
OWNER_ID = "phase5-real-codex-owner-v2"


def _hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def evaluate_v2_observation(
    *, runtime_pin_valid: bool, action_id: str, workflow_id: str,
    workflow_rows: int, terminal_status: str, terminal_host_events: int,
    canonical_thread_count: int, turn_start_count: int, bootstrap_terminal: bool,
) -> dict[str, Any]:
    checks = {
        "runtime_pin_valid": runtime_pin_valid,
        "bootstrap_terminal": bootstrap_terminal,
        "single_action_workflow_identity": (
            bool(action_id) and workflow_id == action_id and workflow_rows == 1
        ),
        "terminal_completed": terminal_status == "completed",
        "single_terminal_host_event": terminal_host_events == 1,
        "single_canonical_thread": canonical_thread_count == 1,
        "single_turn_start": turn_start_count == 1,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "release_allowed": False,
    }


def _start_canonical_thread(
    codex_bin: Path, schema_root: Path, codex_home: Path, workspace: Path,
    spool_path: Path, model: str,
) -> tuple[str, int, bool]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home.resolve())
    process = subprocess.Popen(
        [str(codex_bin.resolve()), "app-server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", env=env,
    )
    try:
        adapter = AppServerAdapter(
            process, schema_root, response_timeout=30.0,
            spool=ProtocolSpool(spool_path),
        )
        adapter.initialize(request_id="phase5-v2-initialize")
        started = adapter.start_thread({
            "cwd": str(workspace.resolve()),
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "model": model,
            "developerInstructions": "Return only the requested short token. Do not use tools.",
            "ephemeral": False,
        }, request_id="phase5-v2-thread-start")
        if not started.thread_id:
            raise RuntimeError("stable canonical thread identity missing")
        bootstrap = adapter.start_turn(
            started.thread_id,
            [{"type": "text", "text": "Return exactly READY."}],
            request_id="phase5-v2-bootstrap-turn", model=model,
        )
        if not bootstrap.turn_id:
            raise RuntimeError("stable bootstrap turn identity missing")
        terminal = adapter.observe_turn(
            started.thread_id, bootstrap.turn_id, timeout=300.0
        )
        return started.thread_id, process.pid, terminal.disposition == "terminal"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.ambient_home:
        raise ValueError("explicit --ambient-home is required")
    for path in (args.runtime, args.output):
        if path.exists():
            raise FileExistsError(f"Phase 5 real-host path already exists: {path}")
    args.runtime.mkdir(parents=True, exist_ok=False)
    pin = verify_runtime_selection(
        args.codex_bin, args.schema_root, expected_version=PHASE5_CODEX_VERSION,
        expected_platform=args.codex_platform,
    )
    if not pin["valid"]:
        raise RuntimeError("stable runtime pin failed")

    setup_spool = args.runtime / "thread-setup-protocol.jsonl"
    workflow_spool = args.runtime / "workflow-protocol.jsonl"
    thread_id, setup_app_server_pid, bootstrap_terminal = _start_canonical_thread(
        args.codex_bin, args.schema_root, Path.home() / ".codex", args.workspace,
        setup_spool, args.model,
    )
    domain_path = args.runtime / "control.sqlite3"
    store = ControlStore(domain_path)
    bridge = None
    try:
        epoch = store.create_job_work_item(JOB_ID, WORK_ITEM_ID, OWNER_ID, lease_ttl_seconds=600)
        store.plan_attempt_action(
            job_id=JOB_ID, work_item_id=WORK_ITEM_ID, attempt_id=ATTEMPT_ID,
            action_id=ACTION_ID, kind="codex-turn-v2",
            payload_hash=_hash({"input": "Return exactly PHASE5_OK."}),
            owner_id=OWNER_ID, fence_epoch=epoch,
        )
        store.bind_canonical_thread(
            ATTEMPT_ID, "codex-app-server", thread_id,
            str(pin["schema"]["manifest_digest"]), OWNER_ID, epoch,
        )
        store.transition_outbox(ACTION_ID, "workflow_submitting", OWNER_ID, epoch)
        bridge = DBOSBridge(args.runtime / "dbos.sqlite3")
        handle = bridge.start_codex_action_v2(
            ACTION_ID, domain_path, OWNER_ID, epoch, args.codex_bin,
            args.schema_root, Path.home() / ".codex", workflow_spool,
            [{"type": "text", "text": "Return exactly PHASE5_OK."}],
            observe_timeout=args.timeout, codex_platform=args.codex_platform,
        )
        binding = store.attach_workflow(
            ACTION_ID, "run_codex_action_v2", OWNER_ID, epoch, "RUNNING"
        )
        result = handle.get_result()
        store.attach_workflow(
            ACTION_ID, "run_codex_action_v2", OWNER_ID, epoch,
            "SUCCESS" if result.get("terminal_status") == "completed" else "ERROR",
        )
        workflow_rows = int(store.connection.execute(
            "SELECT COUNT(*) FROM workflow_bindings WHERE action_id=?", (ACTION_ID,)
        ).fetchone()[0])
        terminal_events = int(store.connection.execute(
            "SELECT COUNT(*) FROM host_events WHERE action_id=? AND event_type='terminal'",
            (ACTION_ID,),
        ).fetchone()[0])
        canonical_threads = int(store.connection.execute(
            "SELECT COUNT(*) FROM thread_bindings WHERE attempt_id=?", (ATTEMPT_ID,)
        ).fetchone()[0])
        integrity = store.integrity_check()
    finally:
        if bridge is not None:
            bridge.close()
        store.close()

    rows = [json.loads(line) for line in workflow_spool.read_text(encoding="utf-8").splitlines()]
    turn_start_count = sum(
        row.get("direction") == "outbound" and row.get("method") == "turn/start"
        for row in rows
    )
    evaluated = evaluate_v2_observation(
        runtime_pin_valid=bool(pin["valid"]), action_id=ACTION_ID,
        workflow_id=str(binding["workflow_id"]), workflow_rows=workflow_rows,
        terminal_status=str(result.get("terminal_status")),
        terminal_host_events=terminal_events,
        canonical_thread_count=canonical_threads, turn_start_count=turn_start_count,
        bootstrap_terminal=bootstrap_terminal,
    )
    checks = {**evaluated["checks"], "domain_integrity": integrity == "ok"}
    receipt = {
        "schema_version": "ds-lite.phase5-real-codex-action-v2.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "evidence_class": "real-codex-ambient-provider",
        "codex_version": PHASE5_CODEX_VERSION,
        "codex_platform": args.codex_platform,
        "codex_binary_sha256": _file_hash(args.codex_bin),
        "schema_manifest_sha256": str(pin["schema"]["manifest_digest"]),
        "model": args.model,
        "action_id_sha256": _hash(ACTION_ID),
        "workflow_id_sha256": _hash(str(binding["workflow_id"])),
        "thread_id_sha256": _hash(thread_id),
        "setup_app_server_pid_sha256": _hash(setup_app_server_pid),
        "workflow_spool_sha256": _file_hash(workflow_spool),
        "raw_model_text_in_receipt": False,
        "controller_inspected_copied_or_modified_credentials": False,
        "release_allowed": False,
    }
    _write_once(args.output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--codex-platform", default="windows-x86_64")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ambient-home", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {
            "schema_version": "ds-lite.phase5-real-codex-action-v2.v1",
            "status": "failed", "failure_layer": type(exc).__name__,
            "evidence_class": "real-codex-not-complete", "release_allowed": False,
        }
        if not args.output.exists():
            _write_once(args.output, result)
    print(json.dumps({"status": result["status"], "checks": result.get("checks", {})}, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
