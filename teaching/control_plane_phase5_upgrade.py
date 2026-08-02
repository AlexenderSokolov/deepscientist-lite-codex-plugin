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
HARNESS = CONTROLLER_ROOT / "phase1_fault_harness.py"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.store import ControlStore  # noqa: E402
from teaching.control_plane_phase5_evidence import file_hash, write_once  # noqa: E402


def evaluate_upgrade_observation(
    *, old_dbos_version: str, new_dbos_version: str, action_id: str,
    recovered_workflow_id: str, workflow_rows: int, terminal_status: str,
    external_kill: bool,
) -> dict[str, Any]:
    checks = {
        "old_runtime": old_dbos_version == "2.28.0",
        "new_runtime": new_dbos_version == "2.29.0",
        "single_workflow_identity": (
            recovered_workflow_id == action_id and workflow_rows == 1
        ),
        "terminal_recovery": terminal_status == "completed",
        "external_process_kill": external_kill,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "old_dbos_version": old_dbos_version,
        "new_dbos_version": new_dbos_version,
        "action_id_sha256": hashlib.sha256(action_id.encode()).hexdigest(),
        "workflow_id_sha256": hashlib.sha256(recovered_workflow_id.encode()).hexdigest(),
        "workflow_rows": workflow_rows,
        "terminal_status": terminal_status,
        "release_allowed": False,
    }


def _environment(*roots: Path) -> dict[str, str]:
    environment = os.environ.copy()
    paths = [str(root.resolve()) for root in roots]
    paths.extend((str(CONTROLLER_ROOT), str(ROOT)))
    if environment.get("PYTHONPATH"):
        paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _dbos_version(python_bin: Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        [str(python_bin.resolve()), "-c",
         "import importlib.metadata; print(importlib.metadata.version('dbos'))"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment, timeout=30, check=True,
    )
    return completed.stdout.strip()


def _wait(path: Path, process: subprocess.Popen[str], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        if path.is_file():
            return True
        time.sleep(0.01)
    return path.is_file()


def run_upgrade(
    *, python_bin: Path, old_dbos_root: Path, dependency_root: Path,
    workdir: Path, output: Path, timeout: float = 45.0,
) -> dict[str, Any]:
    workdir = workdir.resolve()
    output = output.resolve()
    if workdir.exists() or output.exists():
        raise FileExistsError("upgrade paths must be new")
    workdir.mkdir(parents=True, exist_ok=False)
    action_id = "phase5-upgrade-action-v1"
    store = ControlStore(workdir / "control.sqlite3")
    try:
        epoch = store.create_job_work_item("phase5-upgrade-job", "upgrade-gate", "owner-old")
        store.plan_attempt_action(
            job_id="phase5-upgrade-job", work_item_id="upgrade-gate",
            attempt_id="phase5-upgrade-attempt", action_id=action_id,
            kind="fake-turn", payload_hash=hashlib.sha256(action_id.encode()).hexdigest(),
            owner_id="owner-old", fence_epoch=epoch,
        )
        store.transition_outbox(action_id, "workflow_submitting", "owner-old", epoch)
    finally:
        store.close()
    old_env = _environment(old_dbos_root, dependency_root)
    new_env = _environment(dependency_root)
    old_version = _dbos_version(python_bin, old_env)
    new_version = _dbos_version(python_bin, new_env)
    accepted = workdir / "old-workflow-accepted.marker"
    started = workdir / "old-workflow-started.marker"
    old_command = [
        str(python_bin.resolve()), str(HARNESS), "--child-mode", "submit-cut",
        "--case-root", str(workdir), "--action-id", action_id,
        "--old-epoch", str(epoch), "--marker", str(accepted),
        "--workflow-marker", str(started), "--delay-seconds", "30",
    ]
    old_process = subprocess.Popen(
        old_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", env=old_env,
    )
    barrier_observed = _wait(started, old_process, timeout)
    if old_process.poll() is None:
        old_process.kill()
    old_stdout, old_stderr = old_process.communicate(timeout=15)
    external_kill = barrier_observed and old_process.returncode is not None
    recovery_marker = workdir / "recovery-unused.marker"
    recover_command = [
        str(python_bin.resolve()), str(HARNESS), "--child-mode", "recover",
        "--case-root", str(workdir), "--action-id", action_id,
        "--old-epoch", str(epoch), "--marker", str(recovery_marker),
        "--workflow-marker", str(started), "--delay-seconds", "30",
        "--attach-owner", "owner-old", "--attach-epoch", str(epoch),
    ]
    recovered = subprocess.run(
        recover_command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=new_env, timeout=timeout + 30,
    )
    recovery_payload: dict[str, Any] = {}
    if recovered.returncode == 0:
        for line in reversed(recovered.stdout.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if candidate.get("event") == "recovered":
                recovery_payload = candidate
                break
    with sqlite3.connect(workdir / "runtime.sqlite3") as connection:
        workflow_rows = int(connection.execute(
            "SELECT COUNT(*) FROM workflow_status WHERE workflow_uuid=?", (action_id,)
        ).fetchone()[0])
    observation = evaluate_upgrade_observation(
        old_dbos_version=old_version, new_dbos_version=new_version,
        action_id=action_id,
        recovered_workflow_id=str(recovery_payload.get("workflow_id") or "missing"),
        workflow_rows=workflow_rows,
        terminal_status=str(recovery_payload.get("result", {}).get("terminal_status") or "missing"),
        external_kill=external_kill,
    )
    result = {
        "schema_version": "ds-lite.phase5-dbos-upgrade.v1",
        **observation,
        "old_process_returncode": old_process.returncode,
        "recovery_returncode": recovered.returncode,
        "old_stdout_sha256": hashlib.sha256(old_stdout.encode()).hexdigest(),
        "old_stderr_sha256": hashlib.sha256(old_stderr.encode()).hexdigest(),
        "recovery_stdout_sha256": hashlib.sha256(recovered.stdout.encode()).hexdigest(),
        "recovery_stderr_sha256": hashlib.sha256(recovered.stderr.encode()).hexdigest(),
        "old_dbos_package_sha256": file_hash(
            next(old_dbos_root.parent.glob("dbos-2.28-wheel/*.whl"))
        ),
        "evidence_class": "real-dbos-sqlite-cross-version-external-process",
    }
    write_once(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-bin", required=True, type=Path)
    parser.add_argument("--old-dbos-root", required=True, type=Path)
    parser.add_argument("--dependency-root", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args(argv)
    result = run_upgrade(
        python_bin=args.python_bin, old_dbos_root=args.old_dbos_root,
        dependency_root=args.dependency_root, workdir=args.workdir,
        output=args.output, timeout=args.timeout,
    )
    print(json.dumps({"status": result["status"], "checks": result["checks"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
