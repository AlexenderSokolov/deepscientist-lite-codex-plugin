"""Cross-process DBOS SQLite recovery probe for the Phase 0.5 gate."""

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
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.domain import ControlStore, FenceRejected

WORKFLOW_NAME = "ds_lite_phase05_sqlite_recovery_v1"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _dbos_version(dependency_root: Path) -> str:
    matches = sorted(dependency_root.glob("dbos-*.dist-info"))
    if len(matches) != 1:
        return "unknown"
    return matches[0].name.removeprefix("dbos-").removesuffix(".dist-info")


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _recoverable_workflow(action_id: str, domain_path: str, marker_path: str,
                          old_epoch: int, old_owner: str, sleep_seconds: float) -> dict[str, Any]:
    from dbos import DBOS

    marker = Path(marker_path)
    try:
        with marker.open("x", encoding="utf-8") as handle:
            handle.write("started\n")
    except FileExistsError:
        pass
    DBOS.sleep(sleep_seconds)
    store = ControlStore(Path(domain_path))
    try:
        try:
            store.enqueue(action_id, old_epoch, old_owner)
            fence_result = "accepted"
        except FenceRejected:
            fence_result = "rejected"
    finally:
        store.close()
    return {
        "workflow_id": DBOS.workflow_id,
        "fence_result": fence_result,
    }


def _configure_dbos(runtime_path: Path):
    from dbos import DBOS

    workflow = DBOS.workflow(name=WORKFLOW_NAME)(_recoverable_workflow)
    DBOS(config={
        "name": "ds-lite-phase05-probe",
        "system_database_url": _sqlite_url(runtime_path),
        "application_version": "phase0.5-probe-v1",
        "enable_otlp": False,
        "console_log_level": "ERROR",
        "run_admin_server": False,
    })
    DBOS.launch()
    return DBOS, workflow


def _child_start(args: argparse.Namespace) -> int:
    from dbos import SetWorkflowID

    DBOS, workflow = _configure_dbos(args.runtime_path)
    with SetWorkflowID(args.action_id):
        handle = DBOS.start_workflow(
            workflow,
            args.action_id,
            str(args.domain_path.resolve()),
            str(args.marker_path.resolve()),
            args.old_epoch,
            args.old_owner,
            args.sleep_seconds,
        )
    print(json.dumps({"event": "submitted", "same_identity": handle.workflow_id == args.action_id}), flush=True)
    while True:
        time.sleep(1)


def _child_recover(args: argparse.Namespace) -> int:
    from dbos import SetWorkflowID

    DBOS, workflow = _configure_dbos(args.runtime_path)
    with SetWorkflowID(args.action_id):
        attached = DBOS.start_workflow(
            workflow,
            args.action_id,
            str(args.domain_path.resolve()),
            str(args.marker_path.resolve()),
            args.old_epoch,
            args.old_owner,
            args.sleep_seconds,
        )
    retrieved = DBOS.retrieve_workflow(args.action_id)
    result = retrieved.get_result(polling_interval_sec=0.05)
    payload = {
        "event": "recovered",
        "attached_same_identity": attached.workflow_id == args.action_id,
        "retrieved_same_identity": retrieved.workflow_id == args.action_id,
        "result_same_identity": isinstance(result, dict) and result.get("workflow_id") == args.action_id,
        "fence_result": result.get("fence_result") if isinstance(result, dict) else "missing",
    }
    print(json.dumps(payload), flush=True)
    DBOS.destroy()
    return 0


def _child_command(python_bin: Path, mode: str, args: argparse.Namespace) -> list[str]:
    return [
        str(python_bin.resolve()), str(Path(__file__).resolve()),
        "--child-mode", mode,
        "--runtime-path", str(args.runtime_path.resolve()),
        "--domain-path", str(args.domain_path.resolve()),
        "--marker-path", str(args.marker_path.resolve()),
        "--action-id", args.action_id,
        "--old-epoch", str(args.old_epoch),
        "--old-owner", args.old_owner,
        "--sleep-seconds", str(args.sleep_seconds),
    ]


def _parse_child_event(output: str, event: str) -> dict[str, Any] | None:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("event") == event:
            return value
    return None


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    if args.output.exists():
        raise FileExistsError(args.output)
    args.workdir.mkdir(parents=True, exist_ok=False)
    args.runtime_path = args.workdir / "runtime.sqlite3"
    args.domain_path = args.workdir / "control.sqlite3"
    args.marker_path = args.workdir / "workflow-started.marker"
    args.old_owner = "controller-old"
    args.old_epoch = 0
    receipt: dict[str, Any] = {
        "schema_version": "ds-lite.dbos-sqlite-recovery-probe.v2",
        "status": "blocked",
        "failure_layer": "runtime-init",
        "evidence_class": "real-dbos-sqlite",
        "dbos_version": _dbos_version(args.dependency_root),
        "python_version": None,
        "action_id_sha256": _sha256(args.action_id),
        "workflow_id_sha256": None,
        "same_action_workflow_identity": False,
        "workflow_row_count": None,
        "workflow_status": None,
        "start_process_terminated": False,
        "recovery_process_exit": None,
        "old_fence_mutation_rejected": False,
        "new_fence_mutation_accepted": False,
        "new_fence_mutation_persisted": False,
        "raw_output_persisted": False,
        "network_or_service_used": False,
        "release_allowed": False,
    }
    environment = os.environ.copy()
    python_path = [str(args.dependency_root.resolve()), str(ROOT)]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)
    try:
        version = subprocess.run(
            [str(args.python_bin.resolve()), "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True, text=True, check=True, timeout=10, env=environment,
        )
        receipt["python_version"] = version.stdout.strip()
        store = ControlStore(args.domain_path)
        try:
            binding = store.plan_action(args.action_id, "turn")
            args.old_epoch = store.acquire_lease("work-k3", args.old_owner)
            store.enqueue(args.action_id, args.old_epoch, args.old_owner)
        finally:
            store.close()
        if binding["workflow_id"] != args.action_id:
            raise RuntimeError("domain-workflow-identity")

        starter = subprocess.Popen(
            _child_command(args.python_bin, "start", args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=environment,
        )
        deadline = time.monotonic() + args.start_timeout
        while not args.marker_path.exists() and starter.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if not args.marker_path.exists():
            stdout, stderr = starter.communicate(timeout=5)
            receipt["failure_layer"] = "workflow-start"
            receipt["start_stdout_sha256"] = _sha256(stdout)
            receipt["start_stderr_sha256"] = _sha256(stderr)
            return receipt
        starter.kill()
        stdout, stderr = starter.communicate(timeout=10)
        receipt["start_process_terminated"] = True
        receipt["start_stdout_sha256"] = _sha256(stdout)
        receipt["start_stderr_sha256"] = _sha256(stderr)

        store = ControlStore(args.domain_path)
        try:
            current_epoch = store.acquire_lease("work-k3", "controller-new")
        finally:
            store.close()
        if current_epoch <= args.old_epoch:
            raise RuntimeError("fence-epoch-not-advanced")

        recovered = subprocess.run(
            _child_command(args.python_bin, "recover", args),
            capture_output=True, text=True, check=False, timeout=args.recovery_timeout, env=environment,
        )
        receipt["recovery_process_exit"] = recovered.returncode
        receipt["recovery_stdout_sha256"] = _sha256(recovered.stdout)
        receipt["recovery_stderr_sha256"] = _sha256(recovered.stderr)
        event = _parse_child_event(recovered.stdout, "recovered")
        if recovered.returncode != 0 or event is None:
            receipt["failure_layer"] = "workflow-recovery"
            return receipt

        connection = sqlite3.connect(args.runtime_path)
        try:
            rows = connection.execute(
                "SELECT status FROM workflow_status WHERE workflow_uuid = ?", (args.action_id,)
            ).fetchall()
        finally:
            connection.close()
        receipt["workflow_row_count"] = len(rows)
        receipt["workflow_status"] = rows[0][0] if len(rows) == 1 else None
        receipt["workflow_id_sha256"] = _sha256(args.action_id)
        receipt["same_action_workflow_identity"] = all((
            event.get("attached_same_identity") is True,
            event.get("retrieved_same_identity") is True,
            event.get("result_same_identity") is True,
        ))
        receipt["old_fence_mutation_rejected"] = event.get("fence_result") == "rejected"

        store = ControlStore(args.domain_path)
        try:
            store.enqueue(args.action_id, current_epoch, "controller-new")
            receipt["new_fence_mutation_accepted"] = True
            receipt["new_fence_mutation_persisted"] = (
                store.outbox_fence(args.action_id) == ("controller-new", current_epoch)
            )
        finally:
            store.close()
        passed = all((
            receipt["same_action_workflow_identity"],
            receipt["workflow_row_count"] == 1,
            receipt["workflow_status"] == "SUCCESS",
            receipt["old_fence_mutation_rejected"],
            receipt["new_fence_mutation_accepted"],
            receipt["new_fence_mutation_persisted"],
        ))
        receipt["status"] = "passed" if passed else "blocked"
        receipt["failure_layer"] = "none" if passed else "verification"
        return receipt
    except subprocess.TimeoutExpired as exc:
        receipt["failure_layer"] = "execution/timeout"
        receipt["exception_class"] = type(exc).__name__
        return receipt
    except Exception as exc:
        receipt["failure_layer"] = "execution/" + type(exc).__name__.lower()
        receipt["exception_class"] = type(exc).__name__
        return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-root", type=Path)
    parser.add_argument("--python-bin", type=Path)
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--action-id")
    parser.add_argument("--start-timeout", type=float, default=20.0)
    parser.add_argument("--recovery-timeout", type=float, default=60.0)
    parser.add_argument("--sleep-seconds", type=float, default=3.0)
    parser.add_argument("--child-mode", choices=("start", "recover"))
    parser.add_argument("--runtime-path", type=Path)
    parser.add_argument("--domain-path", type=Path)
    parser.add_argument("--marker-path", type=Path)
    parser.add_argument("--old-epoch", type=int)
    parser.add_argument("--old-owner")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.child_mode == "start":
        return _child_start(args)
    if args.child_mode == "recover":
        return _child_recover(args)
    required = (args.dependency_root, args.python_bin, args.workdir, args.output, args.action_id)
    if any(value is None for value in required):
        raise SystemExit("parent mode requires dependency root, python bin, workdir, output, and action id")
    receipt = run_probe(args)
    _write_once(args.output.resolve(), receipt)
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
