"""Controller-owned real Codex lifecycle smoke for Phase 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_ROOT = ROOT / "plugins" / "deepscientist-lite-core" / "controller"
sys.path.insert(0, str(CONTROLLER_ROOT))

from ds_lite_control.app_server import AppServerAdapter, AppServerClosed, AppServerResponseTimeout
from ds_lite_control.codex_actions import CodexActionRunner
from ds_lite_control.store import ControlStore


def _command(codex_bin: Path) -> list[str]:
    if os.name == "nt" and codex_bin.suffix.casefold() == ".cmd":
        return ["cmd.exe", "/d", "/s", "/c", f'"{codex_bin}" app-server']
    return [str(codex_bin), "app-server"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run(codex_bin: Path, home: Path, workspace: Path, schema_root: Path, output: Path) -> dict[str, Any]:
    if output.exists() or home.exists():
        raise FileExistsError("controller smoke paths must be new")
    home.mkdir(parents=True, exist_ok=False)
    process = subprocess.Popen(
        _command(codex_bin.resolve()), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env={**os.environ, "CODEX_HOME": str(home)},
    )
    domain = output.parent / "controller-domain.sqlite3"
    store = ControlStore(domain)
    thread_id = ""
    turns: list[dict[str, Any]] = []
    observed: dict[str, str] = {}
    failure = "none"
    adapter = AppServerAdapter(process, schema_root, response_timeout=30.0)
    try:
        initialized = adapter.initialize()
        observed["initialize"] = "observed" if initialized.response and "result" in initialized.response else "response-gap"
        started = adapter.start_thread({"cwd": str(workspace.resolve()), "ephemeral": False}, request_id="thread-start")
        thread_id = started.thread_id or ""
        observed["thread/start"] = "observed" if thread_id else "identity-gap"
        if not thread_id:
            raise RuntimeError("thread-id-missing")
        for ordinal in range(1, 4):
            attempt = f"attempt-{ordinal}"
            action = f"phase2-turn-{ordinal}"
            epoch = store.create_job_work_item("phase2-job", f"work-{ordinal}", "phase2-smoke")
            store.plan_attempt_action(
                job_id="phase2-job", work_item_id=f"work-{ordinal}", attempt_id=attempt,
                action_id=action, kind="codex-turn", payload_hash=_hash(f"turn-{ordinal}"),
                owner_id="phase2-smoke", fence_epoch=epoch,
            )
            store.bind_canonical_thread(attempt, "codex-app-server", thread_id, "0.128.0", "phase2-smoke", epoch)
            runner = CodexActionRunner(store, adapter)
            observation = runner.dispatch_turn(
                action, attempt, [{"type": "text", "text": "Return OK without tools."}],
                "phase2-smoke", epoch,
            )
            terminal = adapter.observe_turn(thread_id, str(observation.turn_id), timeout=120) if observation.turn_id else None
            status = terminal.disposition if terminal is not None else observation.disposition
            turns.append({"ordinal": ordinal, "action_id_sha256": _hash(action), "turn_id_sha256": _hash(observation.turn_id) if observation.turn_id else None, "status": status})
            if status != "terminal":
                break
        observed["three-turns"] = "observed" if len(turns) == 3 and all(row["status"] == "terminal" for row in turns) else "response-gap"
        for method, params in (
            ("thread/list", {"limit": 20}),
            ("thread/read", {"threadId": thread_id, "includeTurns": True}),
            ("thread/archive", {"threadId": thread_id}),
            ("thread/unarchive", {"threadId": thread_id}),
            ("thread/resume", {"threadId": thread_id, "cwd": str(workspace.resolve()), "excludeTurns": True}),
        ):
            call = {
                "thread/list": adapter.list_threads,
                "thread/read": adapter.read_thread,
                "thread/archive": adapter.archive_thread,
                "thread/unarchive": adapter.unarchive_thread,
                "thread/resume": adapter.resume_thread,
            }[method]
            if method == "thread/list":
                result = call(params, request_id=f"{method}-probe")
            elif method == "thread/read":
                result = call(thread_id, include_turns=True, request_id=f"{method}-probe")
            elif method == "thread/resume":
                result = call(thread_id, params, request_id=f"{method}-probe")
            else:
                result = call(thread_id, request_id=f"{method}-probe")
            returned_thread = result.thread_id or thread_id
            observed[method] = "observed" if returned_thread == thread_id or method == "thread/list" else "identity-gap"
        status = "passed" if all(value == "observed" for value in observed.values()) else "blocked"
    except (AppServerClosed, AppServerResponseTimeout, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        status = "blocked"
        failure = str(exc).split(":", 1)[0]
    finally:
        store.close()
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    receipt = {
        "schema_version": "ds-lite.controller-canonical-thread-smoke.v1",
        "status": status, "failure_layer": failure,
        "evidence_class": "real-app-server" if thread_id else "app-server-not-observed",
        "codex_bin_sha256": _hash(str(codex_bin.resolve())),
        "thread_id_sha256": _hash(thread_id) if thread_id else None,
        "methods": observed, "turns": turns,
        "controller_turn_start_count": len(turns),
        "used_last": False, "implicit_thread_start_after_resume_failure": False,
        "response_loss_injected": False, "controller_restart_observed": False,
        "release_allowed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.codex_bin, args.home, args.workspace, args.schema_root, args.output)
    print(json.dumps({"status": result["status"], "failure_layer": result["failure_layer"]}))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
