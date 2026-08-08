"""Real stable app-server kill and controller+app-server recovery harness."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-control-plane" / "controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerAdapter, ProtocolSpool  # noqa: E402


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _workspace_manifest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _process_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _spawn_app_server(args: argparse.Namespace, spool: Path) -> tuple[subprocess.Popen[str], AppServerAdapter]:
    env = os.environ.copy()
    if args.ambient_home:
        env.pop("CODEX_HOME", None)
    else:
        env["CODEX_HOME"] = str(args.codex_home.resolve())
    process = subprocess.Popen(
        [str(args.codex_bin.resolve()), "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return process, AppServerAdapter(
        process, args.schema_root, response_timeout=30.0, spool=ProtocolSpool(spool)
    )


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _turn_status(response: dict[str, Any] | None, turn_id: str) -> str | None:
    def walk(value: Any) -> str | None:
        if isinstance(value, dict):
            if value.get("id") == turn_id and isinstance(value.get("status"), str):
                return str(value["status"])
            for nested in value.values():
                found = walk(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = walk(nested)
                if found is not None:
                    return found
        return None

    return walk(response)


def _spool_methods(path: Path, direction: str = "outbound") -> list[str]:
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [str(row["method"]) for row in rows if row.get("direction") == direction and row.get("method")]


def evaluate_process_chaos(
    *, scenario: str, barrier: dict[str, Any], recovery: dict[str, Any],
    start_methods: list[str], recovery_methods: list[str], killed_app_server: bool,
    killed_controller: bool, workspace_unchanged: bool,
) -> dict[str, Any]:
    checks = {
        "fault_mode_observed": killed_app_server and (
            scenario == "app-server" or killed_controller
        ),
        "controller_mode_observed": (
            not killed_controller if scenario == "app-server" else killed_controller
        ),
        "distinct_app_server_process": barrier.get("app_server_pid") != recovery.get("app_server_pid"),
        "distinct_controller_process": barrier.get("controller_pid") != recovery.get("controller_pid"),
        "single_canonical_thread": barrier.get("thread_id") == recovery.get("thread_id"),
        "single_logical_turn": barrier.get("turn_id") == recovery.get("turn_id"),
        "host_started_before_fault": barrier.get("prekill_disposition") == "active",
        "exactly_one_turn_start": start_methods.count("turn/start") == 1,
        "no_recovery_redispatch": "turn/start" not in recovery_methods,
        "exact_resume": recovery_methods.count("thread/resume") == 1,
        "terminal_recovered": recovery.get("disposition") in {"terminal", "failed"},
        "workspace_unchanged": workspace_unchanged,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "release_allowed": False,
    }


def worker_start(args: argparse.Namespace) -> int:
    process, adapter = _spawn_app_server(args, args.runtime / "start-protocol.jsonl")
    try:
        adapter.initialize(request_id=f"{args.sample_id}-initialize")
        started = adapter.start_thread({
            "cwd": str(args.workspace.resolve()),
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "model": args.model,
            "developerInstructions": "Return only the requested token. Do not use tools.",
            "ephemeral": False,
        }, request_id=f"{args.sample_id}-thread-start")
        if not started.thread_id:
            raise RuntimeError("thread identity missing")
        turn = adapter.start_turn(
            started.thread_id,
            [{"type": "text", "text": "Return exactly PHASE5_CHAOS_OK."}],
            request_id=f"{args.sample_id}-turn-start",
            model=args.model,
        )
        if not turn.turn_id:
            raise RuntimeError("turn identity missing")
        prekill = adapter.observe_turn(started.thread_id, turn.turn_id, timeout=5.0)
        if prekill.disposition != "active":
            raise RuntimeError(f"turn was not active at fault barrier:{prekill.disposition}")
        _write_once(args.barrier, {
            "schema_version": "ds-lite.phase5-process-chaos-barrier.v1",
            "scenario": args.scenario,
            "sample_id": args.sample_id,
            "controller_pid": os.getpid(),
            "app_server_pid": process.pid,
            "thread_id": started.thread_id,
            "turn_id": turn.turn_id,
            "prekill_disposition": prekill.disposition,
            "workspace_digest_before": _workspace_manifest(args.workspace),
        })
        if args.scenario == "app-server":
            process.wait(timeout=300)
            _write_once(args.runtime / "app-server-exit.json", {
                "app_server_pid": process.pid, "controller_pid": os.getpid(),
                "app_server_exit_observed": True,
            })
        while True:
            time.sleep(1)
    finally:
        _stop_process(process)


def worker_recover(args: argparse.Namespace) -> int:
    barrier = json.loads(args.barrier.read_text(encoding="utf-8"))
    process, adapter = _spawn_app_server(args, args.runtime / "recovery-protocol.jsonl")
    disposition = "ambiguous"
    observed_status: str | None = None
    try:
        adapter.initialize(request_id=f"{args.sample_id}-recovery-initialize")
        adapter.resume_thread(
            str(barrier["thread_id"]),
            {
                "cwd": str(args.workspace.resolve()), "sandbox": "read-only",
                "approvalPolicy": "never", "model": args.model,
                "developerInstructions": "Return only the requested token. Do not use tools.",
            },
            request_id=f"{args.sample_id}-thread-resume",
        )
        read = adapter.read_thread(
            str(barrier["thread_id"]), include_turns=True,
            request_id=f"{args.sample_id}-thread-read-initial",
        )
        observed_status = _turn_status(read.response, str(barrier["turn_id"]))
        if observed_status == "completed":
            disposition = "terminal"
        elif observed_status in {"failed", "interrupted", "cancelled"}:
            disposition = "failed"
        elif observed_status in {"inProgress", "in_progress", "active"}:
            terminal = adapter.observe_turn(
                str(barrier["thread_id"]), str(barrier["turn_id"]), timeout=args.timeout
            )
            disposition = terminal.disposition
            if disposition not in {"terminal", "failed"}:
                final_read = adapter.read_thread(
                    str(barrier["thread_id"]), include_turns=True,
                    request_id=f"{args.sample_id}-thread-read-final",
                )
                observed_status = _turn_status(final_read.response, str(barrier["turn_id"]))
                if observed_status == "completed":
                    disposition = "terminal"
                elif observed_status in {"failed", "interrupted", "cancelled"}:
                    disposition = "failed"
        _write_once(args.recovery, {
            "schema_version": "ds-lite.phase5-process-chaos-recovery.v1",
            "sample_id": args.sample_id,
            "controller_pid": os.getpid(),
            "app_server_pid": process.pid,
            "thread_id": barrier["thread_id"],
            "turn_id": barrier["turn_id"],
            "disposition": disposition,
            "observed_status": observed_status,
            "workspace_digest_after": _workspace_manifest(args.workspace),
        })
        return 0 if disposition in {"terminal", "failed"} else 2
    finally:
        _stop_process(process)


def _wait_file(path: Path, process: subprocess.Popen[Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if process.poll() is not None:
            raise RuntimeError(f"worker exited before {path.name}")
        time.sleep(0.05)
    raise TimeoutError(path.name)


def _worker_command(args: argparse.Namespace, mode: str) -> list[str]:
    command = [
        sys.executable, "-m", "teaching.control_plane_phase5_process_chaos", mode,
        "--scenario", args.scenario, "--sample-id", args.sample_id,
        "--codex-bin", str(args.codex_bin), "--schema-root", str(args.schema_root),
        "--codex-home", str(args.codex_home), "--workspace", str(args.workspace),
        "--runtime", str(args.runtime), "--barrier", str(args.runtime / "barrier.json"),
        "--recovery", str(args.runtime / "recovery.json"), "--model", args.model,
        "--timeout", str(args.timeout),
    ]
    if args.ambient_home:
        command.append("--ambient-home")
    return command


def run_driver(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime.exists() or args.output.exists():
        raise FileExistsError("process chaos paths must be new")
    args.runtime.mkdir(parents=True, exist_ok=False)
    barrier_path = args.runtime / "barrier.json"
    start = subprocess.Popen(
        _worker_command(args, "worker-start"), cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    barrier = _wait_file(barrier_path, start, 60.0)
    killed_controller = False
    if args.scenario == "app-server":
        os.kill(int(barrier["app_server_pid"]), signal.SIGTERM)
        _wait_file(args.runtime / "app-server-exit.json", start, 30.0)
        start.terminate()
        start.wait(timeout=20)
    else:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(start.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        else:
            os.killpg(os.getpgid(start.pid), signal.SIGKILL)
        start.wait(timeout=20)
        killed_controller = True
    deadline = time.monotonic() + 20
    while _process_alive(int(barrier["app_server_pid"])) and time.monotonic() < deadline:
        time.sleep(0.05)
    killed_app_server = not _process_alive(int(barrier["app_server_pid"]))

    recovery_process = subprocess.Popen(
        _worker_command(args, "worker-recover"), cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    recovery = _wait_file(args.runtime / "recovery.json", recovery_process, args.timeout + 60)
    recovery_process.wait(timeout=30)
    start_methods = _spool_methods(args.runtime / "start-protocol.jsonl")
    recovery_methods = _spool_methods(args.runtime / "recovery-protocol.jsonl")
    result = evaluate_process_chaos(
        scenario=args.scenario,
        barrier=barrier,
        recovery=recovery,
        start_methods=start_methods,
        recovery_methods=recovery_methods,
        killed_app_server=killed_app_server,
        killed_controller=killed_controller,
        workspace_unchanged=(
            barrier["workspace_digest_before"] == recovery["workspace_digest_after"]
        ),
    )
    receipt = {
        "schema_version": "ds-lite.phase5-process-chaos.v1",
        "status": result["status"],
        "scenario": args.scenario,
        "sample_id": args.sample_id,
        "checks": result["checks"],
        "controller_pid_sha256": [_hash(str(barrier["controller_pid"])), _hash(str(recovery["controller_pid"]))],
        "app_server_pid_sha256": [_hash(str(barrier["app_server_pid"])), _hash(str(recovery["app_server_pid"]))],
        "thread_id_sha256": _hash(str(barrier["thread_id"])),
        "turn_id_sha256": _hash(str(barrier["turn_id"])),
        "method_counts": dict(sorted(Counter(start_methods + recovery_methods).items())),
        "evidence_class": "real-codex-ambient-provider",
        "raw_model_output_persisted": False,
        "release_allowed": False,
    }
    _write_once(args.output, receipt)
    return receipt


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scenario", choices=("app-server", "controller-and-app-server"), required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--barrier", type=Path)
    parser.add_argument("--recovery", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--ambient-home", action="store_true")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "worker-start", "worker-recover"):
        _add_common(subparsers.add_parser(name))
    args = parser.parse_args()
    if args.command == "worker-start":
        return worker_start(args)
    if args.command == "worker-recover":
        return worker_recover(args)
    try:
        result = run_driver(args)
    except Exception as exc:
        result = {
            "schema_version": "ds-lite.phase5-process-chaos.v1",
            "status": "failed", "failure_layer": type(exc).__name__,
            "scenario": args.scenario, "sample_id": args.sample_id,
            "release_allowed": False,
        }
        if args.output is not None and not args.output.exists():
            _write_once(args.output, result)
    print(json.dumps({"status": result["status"], "scenario": result["scenario"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
