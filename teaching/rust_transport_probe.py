#!/usr/bin/env python3
"""Run one fresh Rust Codex transport probe without retaining raw output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from teaching.transport_diagnostics import TransportDiagnosticReducer
except ModuleNotFoundError:  # pragma: no cover
    from transport_diagnostics import TransportDiagnosticReducer


EVENT_TYPES = {
    "error", "response.completed", "response.failed", "thread.started",
    "turn.completed", "turn.failed", "turn.started",
}
PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


class RustTransportProbeError(RuntimeError):
    pass


def transport_signals(lines: list[str]) -> list[str]:
    """Return allow-listed transport observations and never retain diagnostic text."""
    text = "\n".join(lines).lower()
    signals: set[str] = set()
    if any(term in text for term in ("certificate", "rustls", "tls", "schannel")):
        signals.add("tls")
    if any(term in text for term in ("http/2", "http2", "alpn", " h2 ")):
        signals.add("http2-or-alpn")
    if "proxy" in text:
        signals.add("proxy")
    if any(term in text for term in ("dns", "resolve", "name resolution")):
        signals.add("dns")
    if any(term in text for term in ("connection reset", "premature eof", "connection aborted")):
        signals.add("connection-reset")
    if "stream" in text and any(term in text for term in ("disconnect", "disconnected", "closed")):
        signals.add("stream-disconnect")
    return sorted(signals)


def run_once(*, codex_bin: Path | str, codex_home: Path | str, workspace: Path | str,
             output_path: Path | str, timeout_seconds: float = 90.0,
             memory_transport_detail: bool = False) -> dict[str, Any]:
    output = Path(output_path).resolve()
    if output.exists():
        raise RustTransportProbeError("probe receipt already exists; refusing retry or overwrite")
    binary = Path(codex_bin).resolve()
    home = Path(codex_home).resolve()
    root = Path(workspace).resolve()
    if not binary.is_file() or not home.is_dir() or not root.is_dir():
        raise RustTransportProbeError("binary, home, and workspace must exist")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    proxy_env_cleared = any(key in env for key in PROXY_KEYS)
    for key in PROXY_KEYS:
        env.pop(key, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    if memory_transport_detail:
        # The child diagnostic text remains process-local and is reduced below.
        env["RUST_LOG"] = "warn,reqwest=debug,hyper_util=debug,rustls=debug"

    command = [str(binary), "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(root), "End now."]
    process_started = False
    timed_out = False
    returncode: int | None = None
    stdout_state = stderr_state = "not-opened"
    lines: list[str] = []
    try:
        process = subprocess.Popen(command, cwd=str(root), env=env, text=True, encoding="utf-8", errors="replace",
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_started = True
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        returncode = process.returncode
        stdout_state = stderr_state = "closed"
        lines = [line for line in (stdout.splitlines() + stderr.splitlines()) if line]
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
        returncode = process.returncode
        stdout_state = stderr_state = "closed"
        lines = [line for line in (stdout.splitlines() + stderr.splitlines()) if line]
    except OSError:
        lines = ["child process spawn failure"]

    reducer = TransportDiagnosticReducer()
    event_counts: Counter[str] = Counter()
    turn_completed = turn_failed = False
    for line in lines:
        reducer.consume(line)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            continue
        event_type = event["type"]
        if event_type in EVENT_TYPES:
            event_counts[event_type] += 1
        if event_type == "turn.completed":
            turn_completed = True
        elif event_type == "turn.failed":
            turn_failed = True
        if event_type in {"error", "response.failed", "turn.failed"}:
            message = event.get("message") if isinstance(event.get("message"), str) else ""
            reducer.consume_structured_error(message, event_type)

    diagnostic = reducer.finalize(
        exit_code=returncode,
        timed_out=timed_out,
        turn_completed=turn_completed,
        turn_failed=turn_failed,
        child_process_state="started" if process_started else "not-started",
        stdout_pipe_state=stdout_state,
        stderr_pipe_state=stderr_state,
    )
    # Codex can complete a turn before a best-effort curated-plugin sync exits
    # nonzero on Windows. The acceptance surface is the terminal turn, while
    # the post-terminal process exit remains explicit in the receipt.
    terminal_success = turn_completed and not turn_failed
    passed = process_started and terminal_success
    receipt = {
        "schema_version": "ds-lite.cli-acceptance.v1",
        "identity": output.parent.name,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "status": "passed" if passed else "blocked",
        "failure_layer": "none" if passed else "fresh-cli-host",
        "process_started": process_started,
        "returncode_observed": returncode is not None,
        "post_terminal_process_exit_nonzero": bool(terminal_success and returncode not in (0, None)),
        "terminal_event_observed": turn_completed or turn_failed,
        "event_type_counts": dict(sorted(event_counts.items())),
        "transport_signals": transport_signals(lines),
        "diagnostic": diagnostic,
        "direct_egress_requested": True,
        "proxy_env_cleared": proxy_env_cleared,
        "no_proxy_forced": True,
        "memory_transport_detail_requested": memory_transport_detail,
        "raw_output_persisted": False,
        "raw_error_text_persisted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one redacted Rust Codex transport probe.")
    parser.add_argument("--codex-bin", required=True)
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--memory-transport-detail", action="store_true")
    args = parser.parse_args()
    try:
        receipt = run_once(codex_bin=args.codex_bin, codex_home=args.codex_home, workspace=args.workspace,
                           output_path=args.output, timeout_seconds=args.timeout,
                           memory_transport_detail=args.memory_transport_detail)
    except RustTransportProbeError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
