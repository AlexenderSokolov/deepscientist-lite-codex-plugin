"""External-process Phase 1 kill-point driver for K1-K3 and K8-K9."""

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
from ds_lite_control.receipts import ReceiptStore
from ds_lite_control.store import ControlStore


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    files = [Path(__file__).resolve(), *sorted((Path(__file__).parent / "ds_lite_control").glob("*.py"))]
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_marker(path: Path, value: str) -> None:
    with path.open("x", encoding="ascii") as handle:
        handle.write(value + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _setup(root: Path, action_id: str) -> int:
    store = ControlStore(root / "control.sqlite3")
    try:
        epoch = store.create_job_work_item("job-1", "work-1", "owner-old")
        store.plan_attempt_action(
            job_id="job-1", work_item_id="work-1", attempt_id=f"attempt-{action_id}",
            action_id=action_id, kind="fake-turn", payload_hash=_hash(action_id),
            owner_id="owner-old", fence_epoch=epoch,
        )
        return epoch
    finally:
        store.close()


def _wait_forever() -> None:
    while True:
        time.sleep(1)


def _child(args: argparse.Namespace) -> int:
    root = args.case_root.resolve()
    if args.child_mode == "k1-cut":
        _setup(root, args.action_id)
        _write_marker(args.marker, "domain-committed")
        _wait_forever()
    if args.child_mode == "submit-cut":
        bridge = DBOSBridge(root / "runtime.sqlite3")
        bridge.start_action(
            args.action_id, root / "control.sqlite3", "owner-old", args.old_epoch,
            args.workflow_marker, args.delay_seconds,
        )
        _write_marker(args.marker, "workflow-accepted")
        _wait_forever()
    if args.child_mode == "recover":
        bridge = DBOSBridge(root / "runtime.sqlite3")
        try:
            handle = bridge.start_action(
                args.action_id, root / "control.sqlite3", "owner-old", args.old_epoch,
                args.workflow_marker, args.delay_seconds,
            )
            result = handle.get_result()
            store = ControlStore(root / "control.sqlite3")
            try:
                store.attach_workflow(
                    args.action_id, "run_action_v1", args.attach_owner,
                    args.attach_epoch, "SUCCESS" if result.get("terminal_status") == "completed" else "fenced",
                )
            finally:
                store.close()
            print(json.dumps({"event": "recovered", "workflow_id": handle.workflow_id, "result": result}), flush=True)
            return 0
        finally:
            bridge.close()
    if args.child_mode == "k8-cut":
        store = ControlStore(root / "control.sqlite3")
        try:
            store.record_host_event(
                event_id=f"terminal-{args.action_id}", action_id=args.action_id,
                event_type="terminal", observed_at="2026-07-31T00:00:00Z",
                payload_hash=_hash(f"terminal:{args.action_id}"), owner_id="owner-old",
                fence_epoch=args.old_epoch,
            )
        finally:
            store.close()
        _write_marker(args.marker, "terminal-event-committed")
        _wait_forever()
    if args.child_mode == "k9-cut":
        store = ControlStore(root / "control.sqlite3")
        try:
            receipts = ReceiptStore(root / "receipts", store)
            payload = receipts.terminal_payload(args.action_id, "owner-old", args.old_epoch)
            receipts.write_file(f"terminal-{args.action_id}", payload)
        finally:
            store.close()
        _write_marker(args.marker, "receipt-file-fsynced")
        _wait_forever()
    raise ValueError(args.child_mode)


def _command(args: argparse.Namespace, mode: str, root: Path, action_id: str, epoch: int,
             marker: Path, *, attach_owner: str = "owner-old", attach_epoch: int | None = None,
             workflow_marker: Path | None = None, delay_seconds: float = 0.0) -> list[str]:
    return [
        str(args.python_bin.resolve()), str(Path(__file__).resolve()), "--child-mode", mode,
        "--case-root", str(root), "--action-id", action_id, "--old-epoch", str(epoch),
        "--marker", str(marker), "--attach-owner", attach_owner,
        "--attach-epoch", str(attach_epoch if attach_epoch is not None else epoch),
        "--delay-seconds", str(delay_seconds),
        *( ["--workflow-marker", str(workflow_marker)] if workflow_marker is not None else [] ),
    ]


def _kill_at_barrier(command: list[str], marker: Path, env: dict[str, str], timeout: float) -> bool:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    deadline = time.monotonic() + timeout
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    observed = marker.exists()
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)
    return observed and process.returncode is not None


def _recover(command: list[str], env: dict[str, str], timeout: float) -> dict[str, Any] | None:
    process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)
    if process.returncode != 0:
        return None
    for line in reversed(process.stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "recovered":
            return event
    return None


def _workflow_rows(runtime: Path, action_id: str) -> int:
    connection = sqlite3.connect(runtime)
    try:
        return len(connection.execute(
            "SELECT 1 FROM workflow_status WHERE workflow_uuid=?", (action_id,)
        ).fetchall())
    finally:
        connection.close()


def _prepare_attached(root: Path, action_id: str) -> int:
    epoch = _setup(root, action_id)
    store = ControlStore(root / "control.sqlite3")
    try:
        store.transition_outbox(action_id, "workflow_submitting", "owner-old", epoch)
        store.attach_workflow(action_id, "run_action_v1", "owner-old", epoch)
    finally:
        store.close()
    return epoch


def _run_case(name: str, root: Path, action_id: str, args: argparse.Namespace,
              env: dict[str, str]) -> bool:
    root.mkdir(parents=True, exist_ok=False)
    marker = root / "driver-barrier.marker"
    if name == "K1":
        killed = _kill_at_barrier(_command(args, "k1-cut", root, action_id, 1, marker), marker, env, args.timeout)
        if not killed:
            return False
        recovery = _recover(_command(args, "recover", root, action_id, 1, root / "unused.marker"), env, args.timeout)
        return bool(killed and recovery and recovery["workflow_id"] == action_id and
                    _workflow_rows(root / "runtime.sqlite3", action_id) == 1)
    if name in {"K2", "K3"}:
        epoch = _setup(root, action_id)
        store = ControlStore(root / "control.sqlite3")
        store.transition_outbox(action_id, "workflow_submitting", "owner-old", epoch)
        store.close()
        workflow_marker = root / "workflow-started.marker" if name == "K3" else None
        wait_marker = workflow_marker if workflow_marker is not None else marker
        killed = _kill_at_barrier(
            _command(args, "submit-cut", root, action_id, epoch, marker,
                     workflow_marker=workflow_marker, delay_seconds=0.5 if name == "K3" else 0.0),
            wait_marker, env, args.timeout,
        )
        if not killed:
            return False
        attach_owner, attach_epoch = "owner-old", epoch
        if name == "K3":
            store = ControlStore(root / "control.sqlite3")
            attach_owner = "owner-new"
            attach_epoch = store.acquire_lease(
                "work-1", attach_owner, allow_unexpired_takeover=True
            )
            store.close()
        recovery = _recover(
            _command(args, "recover", root, action_id, epoch, root / "recover.marker",
                     attach_owner=attach_owner, attach_epoch=attach_epoch,
                     workflow_marker=workflow_marker, delay_seconds=0.5 if name == "K3" else 0.0),
            env, args.timeout,
        )
        expected = "fenced" if name == "K3" else "completed"
        domain_verified = True
        if name == "K3":
            store = ControlStore(root / "control.sqlite3")
            try:
                try:
                    store.terminal_event(action_id)
                    no_terminal_mutation = False
                except ValueError:
                    no_terminal_mutation = True
                domain_verified = all((
                    no_terminal_mutation,
                    store.action_state(action_id) != "terminal",
                    store.outbox_fence(action_id) == (attach_owner, attach_epoch),
                    store.workflow_binding_count(action_id) == 1,
                ))
            finally:
                store.close()
        return bool(killed and recovery and recovery["workflow_id"] == action_id and
                    recovery["result"]["terminal_status"] == expected and domain_verified and
                    _workflow_rows(root / "runtime.sqlite3", action_id) == 1)
    epoch = _prepare_attached(root, action_id)
    if name == "K8":
        killed = _kill_at_barrier(_command(args, "k8-cut", root, action_id, epoch, marker), marker, env, args.timeout)
    else:
        store = ControlStore(root / "control.sqlite3")
        store.record_host_event(
            event_id=f"terminal-{action_id}", action_id=action_id, event_type="terminal",
            observed_at="2026-07-31T00:00:00Z", payload_hash=_hash(f"terminal:{action_id}"),
            owner_id="owner-old", fence_epoch=epoch,
        )
        store.close()
        killed = _kill_at_barrier(_command(args, "k9-cut", root, action_id, epoch, marker), marker, env, args.timeout)
    if not killed:
        return False
    store = ControlStore(root / "control.sqlite3")
    try:
        receipts = ReceiptStore(root / "receipts", store)
        payload = receipts.terminal_payload(action_id, "owner-old", epoch)
        written = receipts.write_and_index(f"terminal-{action_id}", payload, "owner-old", epoch)
        indexed = store.receipt_index(f"terminal-{action_id}")
        return bool(killed and indexed and indexed["content_hash"] == written["content_hash"])
    finally:
        store.close()


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    if args.trials <= 0:
        raise ValueError("trials must be positive")
    source_before = _source_digest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.workdir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    paths = [str(args.dependency_root.resolve()), str(Path(__file__).resolve().parent)]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    randomizer = random.Random(args.seed)
    cases: dict[str, Any] = {}
    for name in ("K1", "K2", "K3", "K8", "K9"):
        passed = 0
        identities = []
        for trial in range(args.trials):
            action_id = f"phase1-{name.lower()}-{randomizer.randrange(2**63):016x}"
            identities.append(_hash(action_id))
            if _run_case(name, args.workdir / name.lower() / f"trial-{trial:03d}", action_id, args, env):
                passed += 1
        cases[name] = {
            "passed": passed, "failed": args.trials - passed,
            "all_passed": passed == args.trials,
            "identity_digest": _hash("".join(identities)),
            "evidence_class": "real-dbos-sqlite" if name in {"K1", "K2", "K3"} else "fake-host-filesystem",
        }
    source_after = _source_digest()
    source_stable = source_before == source_after
    result = {
        "schema_version": "ds-lite.phase1-fault-matrix.v1",
        "seed": args.seed, "trials": args.trials, "cases": cases,
        "external_process_termination": True,
        "source_digest": source_after,
        "source_stable": source_stable,
        "release_allowed": False,
        "status": "passed" if source_stable and all(case["all_passed"] for case in cases.values()) else "blocked",
    }
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-root", type=Path)
    parser.add_argument("--python-bin", type=Path)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--child-mode", choices=("k1-cut", "submit-cut", "recover", "k8-cut", "k9-cut"))
    parser.add_argument("--case-root", type=Path)
    parser.add_argument("--action-id")
    parser.add_argument("--old-epoch", type=int, default=1)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--attach-owner", default="owner-old")
    parser.add_argument("--attach-epoch", type=int, default=1)
    parser.add_argument("--workflow-marker", type=Path)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.child_mode:
        return _child(args)
    if args.workdir is None or args.output is None or args.dependency_root is None or args.python_bin is None:
        raise SystemExit("--dependency-root, --python-bin, --workdir and --output are required")
    result = run_matrix(args)
    print(json.dumps({"status": result["status"], "trials": result["trials"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
