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
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.errors import FenceRejected  # noqa: E402
from ds_lite_control.store import ControlStore  # noqa: E402
from teaching.control_plane_phase5_evidence import write_once  # noqa: E402


JOB_ID = "phase5-user-supervisor-job"
WORK_ITEM_ID = "phase5-user-supervisor-gate"
ACTION_ID = "phase5-user-supervisor-action"


def _append_witness(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def evaluate_supervisor_rows(
    rows: list[dict[str, Any]], *, supervisor_kind: str, cleanup_observed: bool,
) -> dict[str, Any]:
    first = rows[0] if rows else {}
    second = rows[1] if len(rows) > 1 else {}
    checks = {
        "two_generations": len(rows) >= 2,
        "cross_process_restart": (
            bool(first.get("pid")) and bool(second.get("pid"))
            and first.get("pid") != second.get("pid")
        ),
        "heartbeat_each_generation": (
            first.get("heartbeat_recorded") is True
            and second.get("heartbeat_recorded") is True
        ),
        "fence_epoch_advanced": (
            isinstance(first.get("fence_epoch"), int)
            and isinstance(second.get("fence_epoch"), int)
            and second["fence_epoch"] > first["fence_epoch"]
        ),
        "old_fence_rejected": second.get("old_fence_rejected") is True,
        "user_level_supervisor": supervisor_kind in {"windows-task", "systemd-user"},
        "cleanup_observed": cleanup_observed,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "supervisor_kind": supervisor_kind,
        "generation_count": len(rows),
        "pid_sha256": [
            hashlib.sha256(str(row.get("pid")).encode()).hexdigest()
            for row in rows[:2]
        ],
        "owner_sha256": [
            hashlib.sha256(str(row.get("owner_id")).encode()).hexdigest()
            for row in rows[:2]
        ],
        "fence_epochs": [row.get("fence_epoch") for row in rows[:2]],
        "release_allowed": False,
    }


def worker(state_root: Path, witness: Path, ready: Path, hold_seconds: float) -> int:
    state_root = state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    existing_rows = _read_rows(witness)
    generation = len(existing_rows) + 1
    owner_id = f"phase5-supervisor-{os.getpid()}"
    store = ControlStore(state_root / "control.sqlite3")
    try:
        exists = store.connection.execute(
            "SELECT 1 FROM work_items WHERE work_item_id=?", (WORK_ITEM_ID,)
        ).fetchone()
        if exists is None:
            epoch = store.create_job_work_item(JOB_ID, WORK_ITEM_ID, owner_id)
            store.plan_attempt_action(
                job_id=JOB_ID, work_item_id=WORK_ITEM_ID,
                attempt_id="phase5-supervisor-attempt", action_id=ACTION_ID,
                kind="fake-turn", payload_hash=hashlib.sha256(ACTION_ID.encode()).hexdigest(),
                owner_id=owner_id, fence_epoch=epoch,
            )
        else:
            epoch = store.acquire_lease(
                WORK_ITEM_ID, owner_id, allow_unexpired_takeover=True
            )
        old_fence_rejected = None
        if existing_rows:
            previous = existing_rows[0]
            try:
                store.transition_outbox(
                    ACTION_ID, "workflow_submitting", str(previous["owner_id"]),
                    int(previous["fence_epoch"]),
                )
                old_fence_rejected = False
            except FenceRejected:
                old_fence_rejected = True
        witness_hash = hashlib.sha256(
            f"{generation}:{owner_id}:{epoch}".encode()
        ).hexdigest()
        store.record_supervisor_heartbeat(
            "phase5-user-supervisor", "phase5-user-supervisor-owner",
            controller_pid=os.getpid(),
            witness_hash=witness_hash,
        )
        heartbeat = store.connection.execute(
            "SELECT controller_pid FROM supervisor_heartbeats WHERE supervisor_id=?",
            ("phase5-user-supervisor",),
        ).fetchone()
        row = {
            "generation": generation,
            "pid": os.getpid(),
            "owner_id": owner_id,
            "fence_epoch": epoch,
            "heartbeat_recorded": bool(heartbeat and int(heartbeat[0]) == os.getpid()),
            "old_fence_rejected": old_fence_rejected,
            "witness_hash": witness_hash,
        }
    finally:
        store.close()
    _append_witness(witness.resolve(), row)
    if generation == 1:
        return 17
    ready = ready.resolve()
    ready.parent.mkdir(parents=True, exist_ok=True)
    with ready.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump({"generation": generation, "pid": os.getpid()}, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    time.sleep(hold_seconds)
    return 0


def task_supervisor(
    state_root: Path, witness: Path, ready: Path, hold_seconds: float
) -> int:
    command = [
        sys.executable, "-m", "teaching.control_plane_phase5_supervisor", "worker",
        "--state-root", str(state_root.resolve()),
        "--witness", str(witness.resolve()),
        "--ready", str(ready.resolve()),
        "--hold-seconds", str(hold_seconds),
    ]
    first = subprocess.run(command, check=False, cwd=ROOT)
    if first.returncode != 17:
        return 31
    second = subprocess.Popen(command, cwd=ROOT)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if ready.is_file():
            return second.wait()
        if second.poll() is not None:
            break
        time.sleep(0.05)
    if second.poll() is None:
        second.terminate()
        second.wait(timeout=10)
    return 32


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("worker")
    run.add_argument("--state-root", required=True, type=Path)
    run.add_argument("--witness", required=True, type=Path)
    run.add_argument("--ready", required=True, type=Path)
    run.add_argument("--hold-seconds", type=float, default=120.0)
    supervise = sub.add_parser("task-supervisor")
    supervise.add_argument("--state-root", required=True, type=Path)
    supervise.add_argument("--witness", required=True, type=Path)
    supervise.add_argument("--ready", required=True, type=Path)
    supervise.add_argument("--hold-seconds", type=float, default=180.0)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--witness", required=True, type=Path)
    evaluate.add_argument("--supervisor-kind", required=True)
    evaluate.add_argument("--cleanup-observed", action="store_true")
    evaluate.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "worker":
        return worker(args.state_root, args.witness, args.ready, args.hold_seconds)
    if args.command == "task-supervisor":
        return task_supervisor(args.state_root, args.witness, args.ready, args.hold_seconds)
    result = evaluate_supervisor_rows(
        _read_rows(args.witness), supervisor_kind=args.supervisor_kind,
        cleanup_observed=args.cleanup_observed,
    )
    result = {
        "schema_version": "ds-lite.phase5-user-supervisor.v1",
        **result,
        "witness_sha256": hashlib.sha256(args.witness.read_bytes()).hexdigest(),
    }
    write_once(args.output, result)
    print(json.dumps({"status": result["status"], "checks": result["checks"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
