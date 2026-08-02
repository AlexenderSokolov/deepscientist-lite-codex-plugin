#!/usr/bin/env python3
"""Run one fresh-host CLI probe and persist only a redacted terminal receipt."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from teaching import cli_compatibility
except ModuleNotFoundError:  # pragma: no cover
    import cli_compatibility


SCHEMA_VERSION = "ds-lite.fresh-host-probe.v1"
PINNED_CLI_VERSION = "0.144.5"
SUPPORTED_CLI_VERSIONS = {PINNED_CLI_VERSION, "0.146.0"}
CLI_EVENT_TYPES = {
    "error",
    "item.completed",
    "item.started",
    "response.completed",
    "response.failed",
    "response.output_item.done",
    "thread.started",
    "turn.completed",
    "turn.failed",
    "turn.started",
}
HOOK_EVENT_ALIASES = {
    "PostToolUse": "post-tool-use",
    "PreToolUse": "pre-tool-use",
    "Stop": "stop",
    "UserPromptSubmit": "user-prompt-submit",
    "post-tool-use": "post-tool-use",
    "pre-tool-use": "pre-tool-use",
    "stop": "stop",
    "user-prompt-submit": "user-prompt-submit",
}
HOOK_DECISIONS = {"allow", "block"}


class FreshHostProbeError(RuntimeError):
    pass


def _host_error_summary(lines: list[str]) -> dict[str, Any]:
    classes: Counter[str] = Counter()
    digests: list[str] = []
    field_names: set[str] = set()
    patterns = (
        ("auth", ("401", "403", "unauthorized", "authentication", "api key")),
        ("rate-limit", ("429", "rate limit", "retry-after")),
        ("provider-transport", ("error sending request", "connection refused", "dns error")),
        ("hook", ("hook",)),
        ("model", ("model", "unsupported_model")),
        ("provider", ("provider", "upstream", "service unavailable", "502", "503", "504")),
        ("schema-config", ("schema", "config", "toml", "invalid parameter")),
        ("sandbox", ("sandbox", "permission denied", "read-only")),
        ("protocol", ("protocol", "stream", "decode", "json")),
    )

    def strings(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            field_names.update(str(key) for key in value)
            return [item for nested in value.values() for item in strings(nested)]
        if isinstance(value, list):
            return [item for nested in value for item in strings(nested)]
        return []

    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or value.get("type") not in {"error", "turn.failed"}:
            continue
        text = " ".join(strings(value)).lower()
        error_class = next(
            (label for label, markers in patterns if any(marker in text for marker in markers)),
            "unknown",
        )
        classes[error_class] += 1
        digests.append(hashlib.sha256(line.encode("utf-8")).hexdigest())
    return {
        "count": sum(classes.values()),
        "classes": dict(sorted(classes.items())),
        "event_sha256": sorted(digests),
        "field_names": sorted(field_names),
        "raw_error_persisted": False,
    }


def _cli_identity(
    binary: Path,
    *,
    expected_cli_version: str | None,
    expected_cli_sha256: str | None,
) -> dict[str, Any]:
    if (expected_cli_version is None) != (expected_cli_sha256 is None):
        raise FreshHostProbeError("expected CLI version and SHA-256 must be supplied together")
    if expected_cli_version is None:
        return {"enforced": False, "expected_version": "not-required", "sha256_match": "not-checked"}
    if expected_cli_version not in SUPPORTED_CLI_VERSIONS:
        raise FreshHostProbeError("expected CLI version is not in the verified host matrix")
    if not isinstance(expected_cli_sha256, str) or re.fullmatch(r"[0-9a-fA-F]{64}", expected_cli_sha256) is None:
        raise FreshHostProbeError("expected CLI SHA-256 must contain 64 hexadecimal characters")
    try:
        actual_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
    except OSError as exc:
        raise FreshHostProbeError("Codex binary could not be read for identity verification") from exc
    if actual_sha256.lower() != expected_cli_sha256.lower():
        raise FreshHostProbeError("Codex binary SHA-256 mismatch")
    return {"enforced": True, "expected_version": expected_cli_version, "sha256_match": True}


def _version_observed(lines: list[str], expected_cli_version: str = PINNED_CLI_VERSION) -> str | None:
    for line in lines:
        match = re.search(r"\bcodex-cli\s+([0-9A-Za-z._-]+)", line, re.IGNORECASE)
        if match:
            return expected_cli_version if match.group(1) == expected_cli_version else "unexpected"
    return None


def _run_command(*, command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: float,
                 expected_cli_version: str = PINNED_CLI_VERSION) -> dict[str, Any]:
    """Run one model-free command; retain only structural output metadata."""
    started = False
    stdout_state = stderr_state = "not-opened"
    lines: list[str] = []
    returncode: int | None = None
    timed_out = False
    try:
        process = subprocess.Popen(command, cwd=str(cwd), env=env, text=True, encoding="utf-8", errors="replace",
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        started = True
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
        returncode = None
        lines = ["child process spawn failure"]
    diagnostic = cli_compatibility.classify_lines(lines, shell="windows-powershell", returncode=returncode,
                                                   stdout_pipe=stdout_state, stderr_pipe=stderr_state, timed_out=timed_out)
    return {"process_started": started, "returncode_observed": returncode is not None,
            "returncode": returncode, "output_line_count": len(lines),
            "output_sha256": diagnostic["diagnostic_sha256"], "diagnostic": diagnostic,
            "version_observed": _version_observed(lines, expected_cli_version),
            "raw_output_persisted": False, "terminal": returncode == 0 and not timed_out}


def run_model_free_checks(*, codex_bin: Path | str, codex_home: Path | str, workspace: Path | str,
                          output_path: Path | str, timeout_seconds: float = 30.0,
                          expected_cli_version: str | None = None,
                          expected_cli_sha256: str | None = None) -> dict[str, Any]:
    """Run fresh CLI-start checks without a prompt or model request."""
    output = Path(output_path)
    if output.exists():
        raise FreshHostProbeError("probe receipt already exists; refusing retry or overwrite")
    binary = Path(codex_bin)
    cli_identity = _cli_identity(
        binary,
        expected_cli_version=expected_cli_version,
        expected_cli_sha256=expected_cli_sha256,
    )
    prefix = [sys.executable, str(binary)] if binary.suffix.lower() == ".py" else [str(binary)]
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    labels = [("version", ["--version"]), ("features", ["features", "list"]), ("plugins", ["plugin", "list", "--json"])]
    checks = []
    for label, args in labels:
        result = _run_command(
            command=prefix + args,
            cwd=Path(workspace),
            env=env,
            timeout_seconds=timeout_seconds,
            expected_cli_version=expected_cli_version or PINNED_CLI_VERSION,
        )
        checks.append({"label": label, **{key: value for key, value in result.items() if key != "returncode"}})
    passed = all(item["process_started"] and item["returncode_observed"] and item["diagnostic"]["failure_class"] == "none" for item in checks)
    if cli_identity["enforced"]:
        passed = passed and checks[0]["version_observed"] == expected_cli_version
    receipt = {"schema_version": "ds-lite.fresh-host-model-free.v1", "status": "passed" if passed else "blocked",
               "checks": checks, "no_external_model_request": True, "raw_output_persisted": False,
               "cli_identity": cli_identity,
               "unverified": ["Hook host loading", "fresh Desktop task", "delegation", "matched effect", "release gate"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def _exec_command_prefix(binary: Path, *, bypass_hook_trust: bool) -> list[str]:
    command = [sys.executable, str(binary)] if binary.suffix.lower() == ".py" else [str(binary)]
    if bypass_hook_trust:
        command.append("--dangerously-bypass-hook-trust")
    command.extend(["exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check"])
    return command


def run_once(*, codex_bin: Path | str, codex_home: Path | str, workspace: Path | str,
            prompt: str, output_path: Path | str, shell_surface: str = "windows-powershell",
            timeout_seconds: float = 120.0, hook_events_path: Path | str | None = None,
            bypass_hook_trust: bool = False, expected_cli_version: str | None = None,
            expected_cli_sha256: str | None = None) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists():
        raise FreshHostProbeError("probe receipt already exists; refusing retry or overwrite")
    binary = Path(codex_bin)
    cli_identity = _cli_identity(
        binary,
        expected_cli_version=expected_cli_version,
        expected_cli_sha256=expected_cli_sha256,
    )
    command = _exec_command_prefix(binary, bypass_hook_trust=bypass_hook_trust)
    command += ["-C", str(workspace), prompt]
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    process_started = False
    lines: list[str] = []
    returncode: int | None = None
    timed_out = False
    stdout_state = "not-opened"
    stderr_state = "not-opened"
    try:
        process = subprocess.Popen(command, cwd=str(workspace), env=env, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process_started = True
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        returncode = process.returncode
        stdout_state = "closed"
        stderr_state = "closed"
        lines = [line for line in (stdout.splitlines() + stderr.splitlines()) if line]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
        returncode = process.returncode
        stdout_state = "closed"
        stderr_state = "closed"
        lines = [line for line in (stdout.splitlines() + stderr.splitlines()) if line]
    except OSError:
        returncode = None
        lines = ["child process spawn failure"]

    event_type_counts: Counter[str] = Counter()
    unrecognized_event_count = 0
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("type"), str):
            event_type = value["type"]
            if event_type in CLI_EVENT_TYPES:
                event_type_counts[event_type] += 1
            else:
                unrecognized_event_count += 1
    event_types = sorted(event_type_counts)
    terminal = any(item in {"turn.completed", "turn.failed", "error"} for item in event_types)
    diagnostic = cli_compatibility.classify_lines(lines, shell=shell_surface, returncode=returncode, stdout_pipe=stdout_state, stderr_pipe=stderr_state, timed_out=timed_out)
    host_errors = _host_error_summary(lines)
    cli_task_status = "passed" if process_started and returncode == 0 and terminal else ("timeout" if timed_out else "blocked")
    status = (
        "passed"
        if cli_task_status == "passed" and cli_identity["enforced"]
        else "test-only-passed"
        if cli_task_status == "passed"
        else cli_task_status
    )
    hook_event_counts: Counter[str] = Counter()
    hook_event_sequence: list[dict[str, Any]] = []
    unrecognized_hook_event_count = 0
    if hook_events_path:
        directory = Path(hook_events_path)
        paths = sorted(
            directory.glob("*.json"),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
        ) if directory.is_dir() else []
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and isinstance(value.get("event_type"), str) and isinstance(value.get("decision"), str):
                event_type = HOOK_EVENT_ALIASES.get(value["event_type"])
                decision = value["decision"].lower()
                if event_type is not None and decision in HOOK_DECISIONS:
                    hook_event_counts[f"{event_type}:{decision}"] += 1
                    hook_event_sequence.append({
                        "event_type": event_type,
                        "decision": decision,
                        "reason_present": value.get("reason_present") is True,
                        "stop_hook_active": value.get("stop_hook_active") is True,
                    })
                else:
                    unrecognized_hook_event_count += 1
    hook_events = [
        {"event_type": key.rsplit(":", 1)[0], "decision": key.rsplit(":", 1)[1]}
        for key in sorted(hook_event_counts)
    ]
    # A host that reports Stop:block and nevertheless emits turn.completed has
    # loaded the hook but has not demonstrated continuation. Treating that as a
    # pass would let a plugin claim conversation control it does not have.
    stop_block_terminal = (
        terminal
        and hook_event_counts.get("stop:block", 0) > 0
        and hook_event_counts.get("stop:allow", 0) == 0
    )
    if stop_block_terminal:
        status = "blocked"
    collaboration_tools: Counter[str] = Counter()
    collaboration_statuses: Counter[str] = Counter()
    collaboration_receivers: set[str] = set()
    for line in lines:
        try:
            value = json.loads(line)
            item = value.get("item") if isinstance(value, dict) else None
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or item.get("type") != "collab_tool_call":
            continue
        tool = item.get("tool") if isinstance(item.get("tool"), str) else "unknown"
        status_value = item.get("status") if isinstance(item.get("status"), str) else "unknown"
        collaboration_tools[tool] += 1
        collaboration_statuses[status_value] += 1
        receivers = item.get("receiver_thread_ids")
        if isinstance(receivers, list):
            for receiver in receivers:
                if isinstance(receiver, str) and receiver:
                    collaboration_receivers.add(hashlib.sha256(receiver.encode("utf-8")).hexdigest())
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "cli_task_status": cli_task_status,
        "process_started": process_started,
        "returncode_observed": returncode is not None,
        "event_count": sum(event_type_counts.values()),
        "event_types": event_types,
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "unrecognized_event_count": unrecognized_event_count,
        "terminal_event_observed": terminal,
        "hook_events": hook_events,
        "hook_event_sequence": hook_event_sequence,
        "hook_event_counts": dict(sorted(hook_event_counts.items())),
        "unrecognized_hook_event_count": unrecognized_hook_event_count,
        "collaboration": {
            "spawn_count": collaboration_tools.get("spawn_agent", 0),
            "receiver_count": len(collaboration_receivers),
            "receiver_id_sha256": sorted(collaboration_receivers),
            "tool_counts": dict(sorted(collaboration_tools.items())),
            "status_counts": dict(sorted(collaboration_statuses.items())),
        },
        "cli_identity": cli_identity,
        "automatic_retry_observed": False,
        "diagnostic": diagnostic,
        "host_errors": host_errors,
        "raw_output_persisted": False,
        "failure_layer": (
            "hook-continuation-not-observed"
            if stop_block_terminal
            else "none"
            if cli_task_status == "passed"
            else "timeout"
            if timed_out
            else "fresh-cli-host"
        ),
        "unverified": [
            "Hook host loading",
            "Hook UserPromptSubmit",
            "Hook PreToolUse",
            "Hook PostToolUse",
            "Hook Stop",
            "fresh Desktop task",
            "delegation",
            "matched effect",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt
