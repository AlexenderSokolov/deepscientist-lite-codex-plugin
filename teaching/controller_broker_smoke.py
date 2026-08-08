"""External-process real Codex response-loss and restart acceptance driver."""

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
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-control-plane" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.broker import BrokerClientTransport, DurableWireJournal, SchemaRegistry


def version_matches(observed: str, expected: str) -> bool:
    return observed.strip() == f"codex-cli {expected}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _wait_file(path: Path, process: subprocess.Popen[Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"process-exited-before-barrier:{process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"barrier-timeout:{path.name}")


def _worker_command(args: argparse.Namespace, mode: str, output: Path, worker_id: str,
                    thread_id: str = "", hold: bool = False) -> list[str]:
    command = [
        sys.executable, str(ROOT / "teaching" / "controller_broker_worker.py"),
        "--mode", mode, "--ready-file", str(args.runtime / "broker-ready.json"),
        "--domain", str(args.runtime / "control.sqlite3"),
        "--schema-root", str(args.schema_root), "--workspace", str(args.workspace),
        "--output", str(output), "--worker-id", worker_id,
        "--codex-version", args.codex_version,
    ]
    if thread_id:
        command.extend(("--thread-id", thread_id))
    if hold:
        command.append("--hold-after")
    return command


def _launch_worker(args: argparse.Namespace, mode: str, worker_id: str, *,
                   thread_id: str = "", kill_at_barrier: bool) -> tuple[dict[str, Any], int, bool]:
    output = args.runtime / f"{worker_id}.json"
    process = subprocess.Popen(
        _worker_command(args, mode, output, worker_id, thread_id, kill_at_barrier),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    data = _wait_file(output, process, 300.0)
    killed = False
    if kill_at_barrier:
        process.terminate()
        process.wait(timeout=20)
        killed = True
    else:
        if process.wait(timeout=20) != 0:
            raise RuntimeError(f"worker-failed:{worker_id}")
    return data, process.pid, killed


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime.exists() or args.output.exists() or args.journal_summary.exists():
        raise FileExistsError("real broker smoke paths must be new")
    args.runtime.mkdir(parents=True, exist_ok=False)
    version = subprocess.run(
        [str(args.codex_bin.resolve()), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, check=False,
    ).stdout.strip()
    if not version_matches(version, args.codex_version):
        raise RuntimeError("pinned-codex-version-mismatch")
    ready_file = args.runtime / "broker-ready.json"
    journal_path = args.runtime / "protocol-journal.jsonl"
    broker_command = [
        sys.executable, "-m", "ds_lite_control", "broker", "serve",
        "--codex-bin", str(args.codex_bin), "--home", str(args.runtime / "codex-home"),
        "--schema-root", str(args.schema_root), "--journal", str(journal_path),
        "--ready-file", str(ready_file),
    ]
    if args.ambient_home:
        broker_command.append("--ambient-home")
    broker = subprocess.Popen(broker_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={
        **os.environ,
        "PYTHONPATH": str(CONTROLLER_ROOT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    })
    ready = _wait_file(ready_file, broker, 30.0)
    worker_records: list[dict[str, Any]] = []
    try:
        first, pid_a, killed_a = _launch_worker(
            args, "bootstrap", "worker-a", kill_at_barrier=True,
        )
        thread_id = str(first["thread_id"])
        second, pid_b, killed_b = _launch_worker(
            args, "continue-drop", "worker-b", thread_id=thread_id, kill_at_barrier=True,
        )
        third, pid_c, killed_c = _launch_worker(
            args, "recover-archive", "worker-c", thread_id=thread_id, kill_at_barrier=True,
        )
        fourth, pid_d, killed_d = _launch_worker(
            args, "recover-final", "worker-d", thread_id=thread_id, kill_at_barrier=False,
        )
        worker_records = [first, second, third, fourth]
        pids = [pid_a, pid_b, pid_c, pid_d]
        killed = [killed_a, killed_b, killed_c, killed_d]
    finally:
        try:
            client = BrokerClientTransport(
                (str(ready["host"]), int(ready["port"])), str(ready["token"]),
                SchemaRegistry(args.schema_root), response_timeout=10.0, connection_id="acceptance-driver",
            )
            client.shutdown()
        finally:
            try:
                broker.wait(timeout=20)
            except subprocess.TimeoutExpired:
                broker.terminate()
                broker.wait(timeout=20)

    journal = DurableWireJournal(journal_path)
    rows = journal.snapshot()
    outbound_methods = [row.get("method") for row in rows if row.get("direction") == "outbound"]
    turn_rows = [row for row in rows if row.get("direction") == "outbound" and row.get("method") == "turn/start"]
    thread_hashes = {_hash(str(row.get("thread_id"))) for row in worker_records if row.get("thread_id")}
    turn_ids = [
        first["turn"].get("turn_id"), second["turn_2"].get("turn_id"),
        third["recovered_turn"].get("turn_id"),
    ]
    journal_report = {
        "schema_version": "ds-lite.broker-journal-summary.v1",
        **journal.summary(),
        "broker_id_sha256": _hash(str(ready["broker_id"])),
        "app_server_pid": int(ready["app_server_pid"]),
        "method_counts": {method: outbound_methods.count(method) for method in sorted(set(outbound_methods)) if method},
        "turn_request_hashes": [row.get("payload_hash") for row in turn_rows],
        "summary_contains_raw_frames": False,
        "release_allowed": False,
    }
    _write_once(args.journal_summary, journal_report)

    checks = {
        "single_broker_app_server": len({row["app_server_pid"] for row in worker_records}) == 1,
        "distinct_controller_processes": len(set(pids)) == 4 and killed[:3] == [True, True, True],
        "single_canonical_thread": len(thread_hashes) == 1,
        "exactly_three_turn_starts": outbound_methods.count("turn/start") == 3,
        "response_loss_injected": second["turn_3"]["disposition"] == "ambiguous" and journal_report["dropped_response_count"] >= 2,
        "response_loss_reconciled": third["recovered_turn"]["disposition"] == "terminal",
        "archive_not_redispatched": outbound_methods.count("thread/archive") == 1,
        "archive_reconciled": fourth["archive"]["disposition"] == "terminal" and fourth["archive"]["lifecycle_state"] == "archived",
        "domain_integrity": all(row.get("domain_integrity") == "ok" for row in worker_records),
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": "ds-lite.real-fault-broker-smoke.v1",
        "status": "passed" if passed else "blocked",
        "failure_layer": "none" if passed else "real-broker-observation-gap",
        "evidence_class": "real-app-server-external-controller-processes",
        "checks": checks,
        "broker_id_sha256": _hash(str(ready["broker_id"])),
        "app_server_pid": int(ready["app_server_pid"]),
        "controller_pids": pids,
        "controller_killed_at_barrier": killed,
        "thread_id_sha256": next(iter(thread_hashes)) if len(thread_hashes) == 1 else None,
        "turn_id_sha256": [_hash(str(value)) if value else None for value in turn_ids],
        "turn_start_count": outbound_methods.count("turn/start"),
        "archive_request_count": outbound_methods.count("thread/archive"),
        "response_loss_injected": checks["response_loss_injected"],
        "controller_restart_observed": checks["distinct_controller_processes"],
        "pending_archive_recovered": checks["archive_reconciled"],
        "used_last": False,
        "implicit_thread_start_after_resume_failure": False,
        "journal_summary_sha256": hashlib.sha256(args.journal_summary.read_bytes()).hexdigest(),
        "codex_cli": args.codex_version,
        "codex_bin_sha256": _file_hash(args.codex_bin),
        "release_allowed": False,
        "sample_id": args.sample_id,
    }
    _write_once(args.output, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal-summary", type=Path, required=True)
    parser.add_argument("--codex-version", default="0.128.0")
    parser.add_argument("--ambient-home", action="store_true")
    parser.add_argument("--sample-id", default="controller-legacy")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, RuntimeError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": "ds-lite.real-fault-broker-smoke.v1",
            "status": "blocked",
            "failure_layer": type(exc).__name__,
            "evidence_class": "real-app-server-not-complete",
            "response_loss_injected": False,
            "controller_restart_observed": False,
            "pending_archive_recovered": False,
            "release_allowed": False,
        }
        if not args.output.exists():
            _write_once(args.output, result)
    print(json.dumps({"status": result["status"], "checks": result.get("checks", {})}, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
