"""External-process Phase 3 fault driver for K10 and K11."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ds_lite_control.dbos_bridge import DBOSBridge
from ds_lite_control.errors import FenceRejected
from ds_lite_control.failure_policy import FailureClassifier
from ds_lite_control.scheduler import DagScheduler, GateClaim
from ds_lite_control.store import ControlStore


CASES = ("K10", "K11")


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _wait_for_marker(process: subprocess.Popen, marker: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not marker.is_file() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.005)
    return marker.is_file()


def _kill(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)


def _child_k10(root: Path, marker: Path, action_id: str) -> int:
    store = ControlStore(root / "control.sqlite3")
    try:
        epoch = store.create_job_work_item(
            "job-1", "gate-a", "owner-old", lease_ttl_seconds=0.05
        )
        store.plan_attempt_action(
            job_id="job-1", work_item_id="gate-a", attempt_id=f"attempt-{action_id}",
            action_id=action_id, kind="fake-turn",
            payload_hash=hashlib.sha256(action_id.encode()).hexdigest(),
            owner_id="owner-old", fence_epoch=epoch,
        )
    finally:
        store.close()
    _write_once(marker, {"event": "old-owner-active", "epoch": epoch})
    while True:
        time.sleep(1)


def _setup_k11(root: Path, identity: str) -> tuple[GateClaim, GateClaim]:
    gate_a_id = f"gate-a-{identity}"
    gate_b_id = f"gate-b-{identity}"
    store = ControlStore(root / "control.sqlite3")
    try:
        scheduler = DagScheduler(store, FailureClassifier(seed=20260731))
        scheduler.register_job(
            "job-1",
            [{"id": gate_a_id, "type": "analysis", "priority": 2},
             {"id": gate_b_id, "type": "analysis", "priority": 1}],
            [],
        )
        claims = scheduler.claim_ready("job-1", "owner-1")
        by_id = {claim.work_item_id: claim for claim in claims}
        scheduler.record_failure(
            by_id[gate_a_id], layer="provider", http_status=429,
            retry_after_seconds=0, evidence_hash="a" * 64,
        )
        return by_id[gate_a_id], by_id[gate_b_id]
    finally:
        store.close()


def _child_k11(
    root: Path, marker: Path, action_id: str, work_item_id: str, fence_epoch: int,
    *, recover: bool,
) -> int:
    bridge = DBOSBridge(root / "runtime.sqlite3")
    try:
        handle = bridge.start_cooldown(
            action_id, work_item_id, root / "control.sqlite3", "owner-1", fence_epoch,
            delay_seconds=0.5, barrier_path=marker,
        )
        if recover:
            result = handle.get_result()
            print(json.dumps({
                "event": "recovered", "workflow_id": handle.workflow_id, "result": result,
            }, ensure_ascii=True), flush=True)
            return 0
        while True:
            time.sleep(1)
    finally:
        bridge.close()


def _child(args: argparse.Namespace) -> int:
    if args.child_mode == "k10-owner":
        return _child_k10(args.case_root, args.marker, args.action_id)
    if args.child_mode in {"k11-sleep", "k11-recover"}:
        return _child_k11(
            args.case_root, args.marker, args.action_id, args.work_item_id,
            args.fence_epoch,
            recover=args.child_mode == "k11-recover",
        )
    raise ValueError(args.child_mode)


def _command(
    python_bin: Path, root: Path, mode: str, marker: Path, action_id: str,
    fence_epoch: int = 1, work_item_id: str = "gate-a",
) -> list[str]:
    return [
        str(python_bin.resolve()), str(Path(__file__).resolve()),
        "--child-mode", mode, "--case-root", str(root), "--marker", str(marker),
        "--action-id", action_id, "--fence-epoch", str(fence_epoch),
        "--work-item-id", work_item_id,
    ]


def _trial_k10(
    root: Path, action_id: str, python_bin: Path, env: dict[str, str], timeout: float
) -> bool:
    root.mkdir(parents=True, exist_ok=False)
    marker = root / "old-owner.marker.json"
    process = subprocess.Popen(
        _command(python_bin, root, "k10-owner", marker, action_id),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    observed = _wait_for_marker(process, marker, timeout)
    _kill(process)
    if not observed:
        return False
    time.sleep(0.08)
    store = ControlStore(root / "control.sqlite3")
    try:
        new_epoch = store.acquire_lease("gate-a", "owner-new", ttl_seconds=60)
        rejected = 0
        operations = (
            lambda: store.heartbeat_lease("gate-a", "owner-old", 1, ttl_seconds=60),
            lambda: store.transition_outbox(action_id, "workflow_submitting", "owner-old", 1),
            lambda: store.attach_workflow(action_id, "run_action_v1", "owner-old", 1),
            lambda: store.record_host_event(
                event_id=f"late-{action_id}", action_id=action_id, event_type="terminal",
                observed_at="2026-07-31T00:00:00Z", payload_hash="f" * 64,
                owner_id="owner-old", fence_epoch=1,
            ),
        )
        for operation in operations:
            try:
                operation()
            except FenceRejected:
                rejected += 1
        store.transition_outbox(action_id, "workflow_submitting", "owner-new", new_epoch)
        binding = store.attach_workflow(
            action_id, "run_action_v1", "owner-new", new_epoch, "attached"
        )
        lease = store.connection.execute(
            "SELECT owner_id,fence_epoch FROM leases WHERE resource_id='gate-a'"
        ).fetchone()
        return bool(
            rejected == len(operations) and new_epoch == 2
            and tuple(lease) == ("owner-new", 2)
            and binding["workflow_id"] == action_id
        )
    finally:
        store.close()


def _workflow_count(runtime: Path, action_id: str) -> int:
    connection = sqlite3.connect(runtime)
    try:
        return int(connection.execute(
            "SELECT COUNT(*) FROM workflow_status WHERE workflow_uuid=?", (action_id,)
        ).fetchone()[0])
    finally:
        connection.close()


def _trial_k11(
    root: Path, action_id: str, python_bin: Path, env: dict[str, str], timeout: float
) -> bool:
    root.mkdir(parents=True, exist_ok=False)
    gate_a, gate_b = _setup_k11(root, action_id)
    workflow_id = gate_a.action_id
    marker = root / "cooldown.marker"
    process = subprocess.Popen(
        _command(
            python_bin, root, "k11-sleep", marker, workflow_id,
            gate_a.fence_epoch, gate_a.work_item_id,
        ),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    observed = _wait_for_marker(process, marker, timeout)
    _kill(process)
    if not observed:
        return False
    store = ControlStore(root / "control.sqlite3")
    try:
        scheduler = DagScheduler(store, FailureClassifier(seed=20260731))
        scheduler.complete_gate(gate_b, outcome="completed", evidence_hash="b" * 64)
    finally:
        store.close()
    recovered = subprocess.run(
        _command(
            python_bin, root, "k11-recover", marker, workflow_id,
            gate_a.fence_epoch, gate_a.work_item_id,
        ),
        capture_output=True, text=True, env=env, timeout=timeout,
    )
    if recovered.returncode != 0:
        return False
    event = None
    for line in reversed(recovered.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if candidate.get("event") == "recovered":
            event = candidate
            break
    store = ControlStore(root / "control.sqlite3")
    try:
        return bool(
            event and event["workflow_id"] == workflow_id
            and event["result"]["terminal_status"] == "ready"
            and store.work_item(gate_a.work_item_id)["state"] == "pending"
            and store.work_item(gate_b.work_item_id)["state"] == "terminal"
            and _workflow_count(root / "runtime.sqlite3", workflow_id) == 1
        )
    finally:
        store.close()


def run_matrix(
    workdir: Path,
    output: Path,
    *,
    python_bin: Path,
    dependency_root: Path,
    seed: int,
    trials: int,
    timeout: float = 20,
) -> dict[str, Any]:
    if workdir.exists() or output.exists():
        raise FileExistsError("phase3 fault evidence paths must be new")
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not (dependency_root / "dbos-2.29.0.dist-info").is_dir():
        raise FileNotFoundError("locked DBOS 2.29.0 dependency root is required")
    workdir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    paths = [str(dependency_root.resolve()), str(Path(__file__).resolve().parent)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    randomizer = random.Random(seed)
    cases: dict[str, Any] = {}
    for case in CASES:
        passed = 0
        identities: list[str] = []
        for trial in range(trials):
            action_id = f"phase3-{case.lower()}-{randomizer.randrange(2**63):016x}"
            identities.append(
                action_id if case == "K10" else f"gate-a-{action_id}:action:1"
            )
            root = workdir / case.lower() / f"trial-{trial:03d}"
            ok = (
                _trial_k10(root, action_id, python_bin, env, timeout)
                if case == "K10"
                else _trial_k11(root, action_id, python_bin, env, timeout)
            )
            passed += int(ok)
        cases[case] = {
            "passed": passed,
            "failed": trials - passed,
            "all_passed": passed == trials,
            "identity_digest": hashlib.sha256("".join(identities).encode()).hexdigest(),
            "evidence_class": (
                "sqlite-fencing-external-process" if case == "K10"
                else "real-dbos-sqlite-external-process"
            ),
        }
    result = {
        "schema_version": "ds-lite.phase3-fault-matrix.v1",
        "seed": seed,
        "trials": trials,
        "cases": cases,
        "external_process_termination": True,
        "status": "passed" if all(value["all_passed"] for value in cases.values()) else "failed",
        "release_allowed": False,
    }
    _write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--python-bin", type=Path, default=Path(sys.executable))
    parser.add_argument("--dependency-root", type=Path)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--child-mode", choices=("k10-owner", "k11-sleep", "k11-recover"))
    parser.add_argument("--case-root", type=Path)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--action-id")
    parser.add_argument("--fence-epoch", type=int, default=1)
    parser.add_argument("--work-item-id", default="gate-a")
    args = parser.parse_args()
    if args.child_mode:
        return _child(args)
    if args.workdir is None or args.output is None or args.dependency_root is None:
        parser.error("--workdir, --output, and --dependency-root are required")
    result = run_matrix(
        args.workdir.resolve(), args.output.resolve(), python_bin=args.python_bin,
        dependency_root=args.dependency_root.resolve(), seed=args.seed,
        trials=args.trials, timeout=args.timeout,
    )
    print(json.dumps({"status": result["status"], "trials": args.trials}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
