from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.broker import BrokerAppServerAdapter
from ds_lite_control.codex_actions import CodexActionRunner
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler, GateClaim
from ds_lite_control.store import ControlStore, LeaseBusy
from teaching.controller_phase3_multigate_smoke import record_terminal_failure


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _claim(value: dict[str, Any]) -> GateClaim:
    return GateClaim(**value)


def _adapter(ready: dict[str, Any], schema_root: Path, worker_id: str) -> BrokerAppServerAdapter:
    return BrokerAppServerAdapter(
        (str(ready["host"]), int(ready["port"])), str(ready["token"]), schema_root,
        response_timeout=130.0, connection_id=worker_id,
    )


def side_effect_command(root: Path) -> str:
    return subprocess.list2cmdline([
        sys.executable,
        str((ROOT / "teaching" / "phase3_side_effect_tool.py").resolve()),
        "--root",
        str(root.resolve()),
    ])


def _take_over_expired_lease(
    store: ControlStore, work_item_id: str, owner_id: str, *, timeout: float = 15.0,
) -> int:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return store.acquire_lease(work_item_id, owner_id, ttl_seconds=600)
        except LeaseBusy:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def run(args: argparse.Namespace) -> dict[str, Any]:
    ready = json.loads(args.ready_file.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    model = str(manifest["model"])
    codex_version = str(manifest["codex_version"])
    claim = _claim(manifest["gate_a"] if args.mode != "gate-b" else manifest["gate_b"])
    store = ControlStore(args.domain)
    adapter = _adapter(ready, args.schema_root, args.worker_id)
    result: dict[str, Any] = {
        "schema_version": "ds-lite.phase3-real-worker.v1",
        "mode": args.mode,
        "controller_pid": os.getpid(),
        "app_server_pid": int(ready["app_server_pid"]),
        "action_id": claim.action_id,
        "attempt_id": claim.attempt_id,
    }
    try:
        if args.mode in {"gate-a-drop", "gate-b"}:
            started = adapter.start_thread(
                {"cwd": str(args.workspace.resolve()), "ephemeral": False, "model": model},
                request_id=f"{claim.action_id}:thread-start",
            )
            if not started.thread_id:
                raise RuntimeError("canonical thread missing")
            store.bind_canonical_thread(
                claim.attempt_id, "codex-app-server-broker", started.thread_id,
                codex_version, claim.owner_id, claim.fence_epoch,
            )
            if args.mode == "gate-a-drop":
                adapter.transport.drop_next_response("turn/start")
                prompt = (
                    "Run exactly this command once, then reply OK: "
                    f"{side_effect_command(args.side_effect_root)}"
                )
            else:
                prompt = "Return gate B OK without using tools."
            observation = CodexActionRunner(store, adapter).dispatch_turn(
                claim.action_id, claim.attempt_id,
                [{"type": "text", "text": prompt}], claim.owner_id, claim.fence_epoch,
                model=model,
            )
            terminal = observation
            if observation.turn_id:
                terminal = adapter.observe_turn(
                    started.thread_id, observation.turn_id, timeout=120.0
                )
            if args.mode == "gate-b" and terminal.disposition == "terminal":
                store.transition_rpc_request(
                    f"{claim.action_id}:turn-start", "terminal", claim.owner_id,
                    claim.fence_epoch, thread_id=started.thread_id,
                    turn_id=terminal.turn_id,
                )
                DagScheduler(store, FailureClassifier(seed=20260731)).complete_gate(
                    claim, outcome="completed",
                    evidence_hash=hashlib.sha256(str(terminal.turn_id).encode()).hexdigest(),
                )
            elif terminal.disposition == "failed":
                result["failure"] = record_terminal_failure(store, claim, terminal)
            result.update({
                "thread_id": started.thread_id,
                "turn_id": terminal.turn_id or observation.turn_id,
                "disposition": terminal.disposition,
                "owner_id": claim.owner_id,
                "fence_epoch": claim.fence_epoch,
            })
            if args.mode == "gate-a-drop":
                store.heartbeat_lease(
                    claim.work_item_id, claim.owner_id, claim.fence_epoch, ttl_seconds=2,
                )
        elif args.mode == "gate-a-recover":
            epoch = _take_over_expired_lease(store, claim.work_item_id, args.worker_id)
            claim = GateClaim(
                job_id=claim.job_id, work_item_id=claim.work_item_id,
                owner_id=args.worker_id, fence_epoch=epoch,
                attempt_number=claim.attempt_number, attempt_id=claim.attempt_id,
                action_id=claim.action_id,
            )
            binding = store.thread_binding(claim.attempt_id)
            observation = CodexActionRunner(store, adapter).reconcile_turn(
                claim.action_id, claim.owner_id, claim.fence_epoch, observe_timeout=120.0,
            )
            if observation.disposition == "terminal":
                DagScheduler(store, FailureClassifier(seed=20260731)).complete_gate(
                    claim, outcome="completed",
                    evidence_hash=hashlib.sha256(str(observation.turn_id).encode()).hexdigest(),
                )
            elif observation.disposition == "failed":
                result["failure"] = record_terminal_failure(store, claim, observation)
            result.update({
                "thread_id": binding["thread_id"], "turn_id": observation.turn_id,
                "disposition": observation.disposition,
                "owner_id": claim.owner_id,
                "fence_epoch": claim.fence_epoch,
            })
        else:
            raise ValueError("unsupported mode")
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
    parser.add_argument("--mode", choices=("gate-a-drop", "gate-b", "gate-a-recover"), required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--domain", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--side-effect-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--hold-after", action="store_true")
    result = run(parser.parse_args())
    print(json.dumps({"mode": result["mode"], "disposition": result["disposition"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
