"""One bounded controller worker used by the real broker restart acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.broker import BrokerAppServerAdapter
from ds_lite_control.codex_actions import CodexActionRunner
from ds_lite_control.store import ControlStore, LeaseBusy


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _adapter(ready: dict[str, Any], schema_root: Path, worker_id: str) -> BrokerAppServerAdapter:
    return BrokerAppServerAdapter(
        (str(ready["host"]), int(ready["port"])), str(ready["token"]), schema_root,
        response_timeout=130.0, connection_id=worker_id,
    )


def take_over_expired_lease(
    store: ControlStore,
    work_item_id: str,
    owner_id: str,
    *,
    timeout: float = 15.0,
    wait: Callable[[float], None] = time.sleep,
) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return store.acquire_lease(work_item_id, owner_id)
        except LeaseBusy:
            if time.monotonic() >= deadline:
                raise
            wait(0.1)


def _plan_turn(store: ControlStore, adapter: BrokerAppServerAdapter, *, ordinal: int,
               thread_id: str, owner_id: str, codex_version: str,
               drop_response: bool = False) -> dict[str, Any]:
    work_id = f"work-{ordinal}"
    attempt_id = f"attempt-{ordinal}"
    action_id = f"phase2-real-turn-{ordinal}"
    epoch = store.create_job_work_item("phase2-real-job", work_id, owner_id)
    store.plan_attempt_action(
        job_id="phase2-real-job", work_item_id=work_id, attempt_id=attempt_id,
        action_id=action_id, kind="codex-turn", payload_hash=_hash({"ordinal": ordinal}),
        owner_id=owner_id, fence_epoch=epoch,
    )
    store.bind_canonical_thread(
        attempt_id, "codex-app-server-broker", thread_id, codex_version, owner_id, epoch,
    )
    if drop_response:
        adapter.transport.drop_next_response("turn/start")
    runner = CodexActionRunner(store, adapter)
    observation = runner.dispatch_turn(
        action_id, attempt_id, [{"type": "text", "text": "Return OK without tools."}],
        owner_id, epoch,
    )
    terminal = None
    if observation.turn_id:
        terminal = adapter.observe_turn(thread_id, observation.turn_id, timeout=120.0)
        if terminal.disposition == "terminal":
            store.transition_rpc_request(
                f"{action_id}:turn-start", "terminal", owner_id, epoch,
                thread_id=thread_id, turn_id=observation.turn_id,
            )
    return {
        "ordinal": ordinal, "work_id": work_id, "attempt_id": attempt_id,
        "action_id": action_id, "epoch": epoch,
        "turn_id": observation.turn_id,
        "disposition": terminal.disposition if terminal else observation.disposition,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    ready = json.loads(args.ready_file.read_text(encoding="utf-8"))
    adapter = _adapter(ready, args.schema_root, args.worker_id)
    store = ControlStore(args.domain)
    result: dict[str, Any] = {
        "schema_version": "ds-lite.controller-broker-worker.v1",
        "mode": args.mode, "worker_id": args.worker_id, "controller_pid": os.getpid(),
        "broker_id": ready["broker_id"], "app_server_pid": ready["app_server_pid"],
    }
    try:
        if args.mode == "bootstrap":
            adapter.initialize(request_id="phase2-real-initialize")
            started = adapter.start_thread(
                {"cwd": str(args.workspace.resolve()), "ephemeral": False},
                request_id="phase2-real-thread-start",
            )
            if not started.thread_id:
                raise RuntimeError("canonical-thread-id-missing")
            result["thread_id"] = started.thread_id
            result["turn"] = _plan_turn(
                store, adapter, ordinal=1, thread_id=started.thread_id, owner_id=args.worker_id,
                codex_version=args.codex_version,
            )
        elif args.mode == "continue-drop":
            result["thread_id"] = args.thread_id
            result["turn_2"] = _plan_turn(
                store, adapter, ordinal=2, thread_id=args.thread_id, owner_id=args.worker_id,
                codex_version=args.codex_version,
            )
            result["turn_3"] = _plan_turn(
                store, adapter, ordinal=3, thread_id=args.thread_id, owner_id=args.worker_id,
                codex_version=args.codex_version,
                drop_response=True,
            )
            store.heartbeat_lease(
                "work-3", args.worker_id, int(result["turn_3"]["epoch"]), ttl_seconds=2,
            )
        elif args.mode == "recover-archive":
            epoch = take_over_expired_lease(store, "work-3", args.worker_id)
            runner = CodexActionRunner(store, adapter)
            recovered = runner.reconcile_turn(
                "phase2-real-turn-3", args.worker_id, epoch, observe_timeout=120.0,
            )
            result["thread_id"] = args.thread_id
            result["recovered_turn"] = {
                "turn_id": recovered.turn_id, "disposition": recovered.disposition, "epoch": epoch,
            }
            adapter.transport.drop_next_response("thread/archive")
            archived = runner.dispatch_archive(
                "phase2-real-turn-3", "attempt-3", args.worker_id, epoch,
            )
            result["archive"] = {"disposition": archived.disposition}
            store.heartbeat_lease("work-3", args.worker_id, epoch, ttl_seconds=2)
        elif args.mode == "recover-final":
            epoch = take_over_expired_lease(store, "work-3", args.worker_id)
            recovered = CodexActionRunner(store, adapter).reconcile_archive(
                "phase2-real-turn-3", "attempt-3", args.worker_id, epoch,
            )
            result["thread_id"] = args.thread_id
            result["archive"] = {
                "disposition": recovered.disposition,
                "lifecycle_state": store.thread_binding("attempt-3")["lifecycle_state"],
                "pending_archive": store.thread_binding("attempt-3")["pending_archive"],
            }
        else:
            raise ValueError("unsupported worker mode")
        result["status"] = "completed"
        result["domain_integrity"] = store.integrity_check()
        _write_once(args.output, result)
        if args.hold_after:
            while True:
                time.sleep(1)
        return result
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("bootstrap", "continue-drop", "recover-archive", "recover-final"), required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--domain", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--codex-version", default="0.128.0")
    parser.add_argument("--hold-after", action="store_true")
    result = run(parser.parse_args())
    print(json.dumps({"status": result["status"], "mode": result["mode"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
