from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from html import escape
from pathlib import Path
from typing import Any, Sequence

from .store import ControlStore


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def request_supervisor_stop(runtime_root: Path, supervisor_id: str) -> Path:
    runtime_root = runtime_root.resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    stop_path = runtime_root / "stop-request.json"
    if stop_path.exists():
        return stop_path
    with stop_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump({
            "schema_version": "ds-lite.supervisor-stop.v1",
            "supervisor_id": supervisor_id,
        }, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")
    return stop_path


def read_supervisor_status(runtime_root: Path) -> dict[str, Any]:
    state_path = runtime_root.resolve() / "supervisor-state.json"
    if not state_path.is_file():
        return {
            "schema_version": "ds-lite.supervisor-status.v1",
            "state": "not-observed",
            "release_allowed": False,
        }
    return json.loads(state_path.read_text(encoding="utf-8"))


class RepoSupervisor:
    """Foreground repository-local child supervisor with durable witnesses."""

    def __init__(
        self,
        store: ControlStore,
        *,
        runtime_root: Path,
        supervisor_id: str,
        owner_id: str,
        worker_command: Sequence[str],
        heartbeat_ttl_seconds: int = 60,
    ) -> None:
        if not worker_command:
            raise ValueError("worker_command is required")
        self.store = store
        self.runtime_root = runtime_root.resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.supervisor_id = supervisor_id
        self.owner_id = owner_id
        self.worker_command = [str(item) for item in worker_command]
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds
        self.state_path = self.runtime_root / "supervisor-state.json"
        self.stop_path = self.runtime_root / "stop-request.json"
        self.process: subprocess.Popen | None = None
        self.generation = 0
        self.last_exit_code: int | None = None

    def request_stop(self) -> None:
        request_supervisor_stop(self.runtime_root, self.supervisor_id)

    def _snapshot(self, state: str) -> dict[str, Any]:
        return {
            "schema_version": "ds-lite.supervisor-status.v1",
            "supervisor_id": self.supervisor_id,
            "owner_id": self.owner_id,
            "state": state,
            "generation": self.generation,
            "controller_pid": self.process.pid if self.process is not None and self.process.poll() is None else None,
            "last_exit_code": self.last_exit_code,
            "release_allowed": False,
        }

    def tick(self) -> dict[str, Any]:
        if self.stop_path.is_file():
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
            if self.process is not None:
                self.last_exit_code = self.process.poll()
            try:
                self.store.stop_supervisor(self.supervisor_id, self.owner_id)
            except ValueError:
                pass
            snapshot = self._snapshot("stopped")
            _write_state(self.state_path, snapshot)
            return snapshot

        if self.process is None or self.process.poll() is not None:
            if self.process is not None:
                self.last_exit_code = self.process.poll()
            self.generation += 1
            self.process = subprocess.Popen(
                self.worker_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=self.runtime_root,
            )
        witness = hashlib.sha256(
            f"{self.supervisor_id}:{self.owner_id}:{self.generation}:{self.process.pid}".encode("ascii")
        ).hexdigest()
        self.store.record_supervisor_heartbeat(
            self.supervisor_id, self.owner_id, controller_pid=self.process.pid,
            witness_hash=witness, ttl_seconds=self.heartbeat_ttl_seconds,
        )
        snapshot = self._snapshot("active")
        _write_state(self.state_path, snapshot)
        return snapshot

    def run(self, *, poll_seconds: float = 1.0) -> int:
        while True:
            snapshot = self.tick()
            if snapshot["state"] == "stopped":
                return 0
            time.sleep(poll_seconds)


def render_service_template(
    platform_name: str,
    output: Path,
    *,
    project: Path,
    python_bin: Path,
) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        str(python_bin.resolve()), "-m", "ds_lite_control", "supervisor", "run",
        "--project", str(project.resolve()),
    ]
    if platform_name == "windows":
        command = subprocess.list2cmdline(argv)
        content = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<Task version=\"1.4\"><Actions Context=\"Author\"><Exec>"
            f"<Command>{escape(command)}</Command>"
            "</Exec></Actions></Task>\n"
        )
    elif platform_name == "systemd":
        content = (
            "[Unit]\nDescription=DS Lite repository-local controller\n"
            "[Service]\nType=simple\n"
            f"WorkingDirectory={project.resolve()}\n"
            f"ExecStart={shlex.join(argv)}\nRestart=on-failure\n"
            "[Install]\nWantedBy=default.target\n"
        )
    else:
        raise ValueError("platform_name must be windows or systemd")
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return output
