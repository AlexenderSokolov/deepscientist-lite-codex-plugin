#!/usr/bin/env python3
"""Run the authorized matched-control pilot without retaining raw event streams."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable

try:
    from .toml_compat import tomllib
except ImportError:
    from toml_compat import tomllib

try:
    import acceptance_gate
    import transport_diagnostics
except ModuleNotFoundError:  # Package import from repository tests and tools.
    from teaching import acceptance_gate, transport_diagnostics

try:
    from teaching.runtime_identity import default_codex_version
except ModuleNotFoundError:  # pragma: no cover
    from runtime_identity import default_codex_version


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "low"
CODEX_VERSION = default_codex_version()
LEGACY_CODEX_VERSIONS = {"0.144.5"}
FROZEN_PILOT_IDS = {"matched-pilot-20260717-01"}
EXPECTED_SKILLS = (
    "ds-lite",
    "ds-lite-analysis-write",
    "ds-lite-coordinate",
    "ds-lite-experiment",
    "ds-lite-idea",
    "ds-lite-intake",
    "ds-lite-iterate",
    "ds-lite-review",
    "ds-lite-scout",
)
LEGACY_SKILL_COUNTS = {9}
CANARY_PROMPT = """上下文重启了。请接手这个科研工程目录，从项目文件恢复当前路线、证据门和下一步。

只做一次只读状态检查，明确说明采用的 skill、插件介入理由和下一检查点，然后停止。不要修改任何文件，不要委派子智能体，不要读取工作区外内容。
"""

EXECUTION_FIELDS = {
    "schema_version",
    "execution_id",
    "pilot_id",
    "call_id",
    "case",
    "arm",
    "round",
    "status",
    "source",
    "cli",
    "input",
    "usage",
    "elapsed_seconds",
    "exit_code",
    "session_id",
    "final_message",
    "wsl",
    "stop_reason",
    "result_refs",
    "started_at",
    "completed_at",
    "extensions",
}
SOURCE_FIELDS = {"git_commit", "tree_digest", "plugin_version", "skill_count", "extensions"}
EXPECTED_SKILL_COUNT = len(EXPECTED_SKILLS)
CLI_FIELDS = {"name", "version", "model", "reasoning_effort", "extensions"}
INPUT_FIELDS = {"workspace_surface", "workspace_ref", "prompt_ref", "input_digest", "extensions"}
USAGE_FIELDS = {"input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "extensions"}
WSL_FIELDS = {"status", "distribution", "proof_ref", "extensions"}
STATUSES = {"pending", "running", "completed", "failed", "timeout", "ambiguous", "blocked"}
STOP_REASONS = {
    "not-started",
    "completed",
    "process-failed",
    "timeout",
    "ambiguous-transport",
    "duplicate-risk",
    "operator-stop",
    "precondition",
}
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "password",
    "passwd",
    "secret",
    "access_token",
    "refresh_token",
    "credential",
    "credentials",
    "chain_of_thought",
    "hidden_reasoning",
    "reasoning_content",
    "environment_variables",
    "full_environment",
    "raw_jsonl",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HEX_PATTERN = re.compile(r"^[0-9a-f]+$")

class PilotError(RuntimeError):
    pass


def _print_progress(snapshot: dict[str, Any]) -> None:
    print(
        "[pilot] "
        f"call={snapshot['call']} case={snapshot['case']} arm={snapshot['arm']} "
        f"round={snapshot['round']} status={snapshot['status']} "
        f"thread={'yes' if snapshot['thread_established'] else 'no'} "
        f"event={snapshot['event_category']} tools={snapshot['tool_count']} "
        f"last_event_age={snapshot['last_event_age_seconds']:.1f}s "
        f"elapsed={snapshot['elapsed_seconds']:.1f}s "
        f"remaining={snapshot['remaining_seconds']:.1f}s "
        f"failure={snapshot['failure_category']} receipt={snapshot['receipt_ref']}",
        flush=True,
    )


class PilotProgress:
    """Reduced, user-visible progress for one Codex call."""

    def __init__(
        self,
        *,
        call_number: int,
        total_calls: int,
        case: str,
        arm: str,
        round_number: int,
        receipt_ref: str,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sink: Callable[[dict[str, Any]], None] | None = None,
        heartbeat_seconds: float = 60.0,
    ) -> None:
        if call_number < 1 or total_calls < call_number:
            raise PilotError("progress call number must be within the declared total")
        if timeout_seconds <= 0 or heartbeat_seconds <= 0:
            raise PilotError("progress timing values must be positive")
        _validate_relative_ref(receipt_ref, "progress.receipt_ref")
        self.call_number = call_number
        self.total_calls = total_calls
        self.case = case
        self.arm = arm
        self.round_number = round_number
        self.receipt_ref = receipt_ref
        self.timeout_seconds = float(timeout_seconds)
        self.clock = clock
        self.sink = sink or _print_progress
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.started_at = self.clock()
        self.last_event_at = self.started_at
        self.last_emit_at = self.started_at
        self.event_category = "process-started"
        self.thread_established = False
        self.tool_count = 0
        self.status = "running"
        self.failure_category = "none"

    def _snapshot(self, now: float) -> dict[str, Any]:
        elapsed = max(0.0, now - self.started_at)
        return {
            "call": f"{self.call_number}/{self.total_calls}",
            "case": self.case,
            "arm": self.arm,
            "round": self.round_number,
            "status": self.status,
            "thread_established": self.thread_established,
            "event_category": self.event_category,
            "tool_count": self.tool_count,
            "last_event_age_seconds": round(max(0.0, now - self.last_event_at), 1),
            "elapsed_seconds": round(elapsed, 1),
            "remaining_seconds": round(max(0.0, self.timeout_seconds - elapsed), 1),
            "failure_category": self.failure_category,
            "receipt_ref": self.receipt_ref,
        }

    def _emit(self, now: float) -> None:
        self.sink(self._snapshot(now))
        self.last_emit_at = now

    def start(self) -> None:
        self._emit(self.clock())

    def observe(self, event_category: str, *, thread_established: bool, tool_count: int) -> None:
        now = self.clock()
        changed = (
            event_category != self.event_category
            or (thread_established and not self.thread_established)
            or tool_count > self.tool_count
        )
        self.event_category = event_category
        self.thread_established = self.thread_established or thread_established
        self.tool_count = max(self.tool_count, tool_count)
        self.last_event_at = now
        if changed:
            self._emit(now)

    def heartbeat(self) -> bool:
        now = self.clock()
        if now - self.last_emit_at < self.heartbeat_seconds:
            return False
        self._emit(now)
        return True

    def finish(self, status: str, failure_category: str) -> None:
        self.status = status
        self.failure_category = failure_category
        self._emit(self.clock())


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PilotError(f"{label} must be an object")
    return value


def _validate_fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    missing = sorted(allowed - set(value))
    if missing:
        raise PilotError(f"{label} missing fields: {', '.join(missing)}")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise PilotError(f"{label} unsupported fields: {', '.join(unknown)}")


def _scan_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS:
                raise PilotError(f"sensitive or hidden-reasoning field is forbidden: {key}")
            _scan_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _scan_sensitive(child)


def _validate_extensions(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise PilotError(f"{label}.extensions must be an object")


def _validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise PilotError(f"{label} must be a stable ID")
    return value


def _validate_digest(value: Any, label: str, lengths: tuple[int, ...] = (64,)) -> str:
    if not isinstance(value, str) or len(value) not in lengths or not HEX_PATTERN.fullmatch(value):
        raise PilotError(f"{label} must be a lowercase hex digest")
    return value


def _validate_relative_ref(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise PilotError(f"{label} must be a project-relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PilotError(f"{label} must not escape its declared surface")
    return value


def _validate_nonnegative_int(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PilotError(f"{label} must be a non-negative integer")


def validate_execution(payload: dict) -> dict:
    value = _require_object(payload, "execution")
    _validate_fields(value, EXECUTION_FIELDS, "execution")
    _scan_sensitive(value)
    if value["schema_version"] != "ds-lite.matched-pilot-execution.v1":
        raise PilotError("schema_version must be ds-lite.matched-pilot-execution.v1")
    execution_id = _validate_id(value["execution_id"], "execution_id")
    pilot_id = _validate_id(value["pilot_id"], "pilot_id")
    call_id = _validate_id(value["call_id"], "call_id")
    if len({execution_id, pilot_id, call_id}) != 3:
        raise PilotError("execution_id, pilot_id, and call_id must differ")
    if value["case"] not in {
        "engineering-continuity",
        "math-counterexample",
        "numerical-seeds",
        "idea-evaluation",
    }:
        raise PilotError("case is invalid")
    if value["arm"] not in {"plain", "scratchpad", "ds-lite"}:
        raise PilotError("arm is invalid")
    if not isinstance(value["round"], int) or value["round"] not in {1, 2, 3}:
        raise PilotError("round is invalid")
    if value["status"] not in STATUSES:
        raise PilotError("status is invalid")
    if value["stop_reason"] not in STOP_REASONS:
        raise PilotError("stop_reason is invalid")

    source = _require_object(value["source"], "source")
    _validate_fields(source, SOURCE_FIELDS, "source")
    _validate_digest(source["git_commit"], "source.git_commit", tuple(range(7, 41)))
    _validate_digest(source["tree_digest"], "source.tree_digest")
    if not isinstance(source["plugin_version"], str) or not source["plugin_version"]:
        raise PilotError("source.plugin_version is required")
    legacy_receipt = str(source["plugin_version"]).startswith(("0.4.", "0.5."))
    if source["skill_count"] != EXPECTED_SKILL_COUNT and not (legacy_receipt and source["skill_count"] in LEGACY_SKILL_COUNTS):
        raise PilotError(f"source.skill_count must be {EXPECTED_SKILL_COUNT}")
    _validate_extensions(source["extensions"], "source")

    cli = _require_object(value["cli"], "cli")
    _validate_fields(cli, CLI_FIELDS, "cli")
    version_valid = cli["version"] == CODEX_VERSION or (
        legacy_receipt and cli["version"] in LEGACY_CODEX_VERSIONS
    )
    if cli["name"] != "codex" or not version_valid:
        raise PilotError("cli identity is invalid")
    if cli["model"] != MODEL or cli["reasoning_effort"] != REASONING_EFFORT:
        raise PilotError("cli model configuration is invalid")
    _validate_extensions(cli["extensions"], "cli")

    input_value = _require_object(value["input"], "input")
    _validate_fields(input_value, INPUT_FIELDS, "input")
    if input_value["workspace_surface"] not in {"windows", "wsl"}:
        raise PilotError("input.workspace_surface is invalid")
    _validate_relative_ref(input_value["workspace_ref"], "workspace_ref")
    _validate_relative_ref(input_value["prompt_ref"], "prompt_ref")
    _validate_digest(input_value["input_digest"], "input.input_digest")
    _validate_extensions(input_value["extensions"], "input")

    usage = _require_object(value["usage"], "usage")
    _validate_fields(usage, USAGE_FIELDS, "usage")
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
        _validate_nonnegative_int(usage[key], f"usage.{key}")
    _validate_extensions(usage["extensions"], "usage")
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise PilotError("usage.total_tokens must equal input_tokens + output_tokens")

    if not isinstance(value["elapsed_seconds"], (int, float)) or value["elapsed_seconds"] < 0:
        raise PilotError("elapsed_seconds must be non-negative")
    if value["exit_code"] is not None and (not isinstance(value["exit_code"], int) or isinstance(value["exit_code"], bool)):
        raise PilotError("exit_code must be an integer or null")
    for key in ("session_id", "final_message", "started_at", "completed_at"):
        if not isinstance(value[key], str):
            raise PilotError(f"{key} must be a string")

    wsl = _require_object(value["wsl"], "wsl")
    _validate_fields(wsl, WSL_FIELDS, "wsl")
    if wsl["status"] not in {"not-required", "verified", "missing"}:
        raise PilotError("wsl.status is invalid")
    if not isinstance(wsl["distribution"], str):
        raise PilotError("wsl.distribution must be a string")
    _validate_relative_ref(wsl["proof_ref"], "wsl.proof_ref", allow_empty=True)
    _validate_extensions(wsl["extensions"], "wsl")

    if not isinstance(value["result_refs"], list) or not value["result_refs"]:
        raise PilotError("result_refs must be a non-empty list")
    for index, ref in enumerate(value["result_refs"]):
        _validate_relative_ref(ref, f"result_refs[{index}]")
    if len(set(value["result_refs"])) != len(value["result_refs"]):
        raise PilotError("result_refs must be unique")
    _validate_extensions(value["extensions"], "execution")

    if value["status"] == "completed":
        if value["exit_code"] != 0 or value["stop_reason"] != "completed" or not value["completed_at"]:
            raise PilotError("completed execution requires exit_code=0, completed stop, and completed_at")
    if value["status"] == "failed" and value["stop_reason"] != "process-failed":
        raise PilotError("failed execution requires process-failed stop_reason")
    if value["case"] == "numerical-seeds" and input_value["workspace_surface"] != "wsl":
        raise PilotError("numerical-seeds must use the wsl workspace surface")
    return payload


def _usage_payload(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    input_tokens = source.get("input_tokens", source.get("prompt_tokens", 0))
    cached_tokens = source.get("cached_input_tokens", source.get("cached_tokens", 0))
    output_tokens = source.get("output_tokens", source.get("completion_tokens", 0))
    values = []
    for item in (input_tokens, cached_tokens, output_tokens):
        values.append(item if isinstance(item, int) and item >= 0 else 0)
    return {
        "input_tokens": values[0],
        "cached_input_tokens": values[1],
        "output_tokens": values[2],
        "total_tokens": values[0] + values[2],
        "extensions": {},
    }


def _message_text(item: dict[str, Any]) -> str:
    direct = item.get("text") or item.get("output_text")
    if isinstance(direct, str):
        return direct
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


class _EventReducer:
    def __init__(self, diagnostic_reducer: transport_diagnostics.TransportDiagnosticReducer | None = None) -> None:
        self.thread_id = ""
        self.final_message = ""
        self.usage = _usage_payload({})
        self.turn_completed = False
        self.turn_failed = False
        self.invalid_line_count = 0
        self.event_category = "none"
        self.tool_count = 0
        self.diagnostic_reducer = diagnostic_reducer
        self.structured_error_count = 0
        self.structured_error_sources: set[str] = set()
        self.collaboration_tool_counts: dict[str, int] = {}
        self.collaboration_status_counts: dict[str, int] = {}
        self.collaboration_receiver_hashes: set[str] = set()

    def _consume_structured_error(self, event_type: str, event: dict[str, Any]) -> None:
        error = event.get("error")
        message = error.get("message") if isinstance(error, dict) else error if isinstance(error, str) else None
        if event_type == "error" and not message:
            message = event.get("message")
        if not isinstance(message, str) or not message:
            return
        source = event_type if event_type in {"error", "response.failed", "turn.failed"} else "unknown"
        self.structured_error_count += 1
        self.structured_error_sources.add(source)
        if self.diagnostic_reducer is not None:
            details = error if isinstance(error, dict) else event
            status = event.get("status")
            if not isinstance(status, int):
                status = details.get("status") if isinstance(details, dict) else None
            self.diagnostic_reducer.consume_structured_error(
                message,
                source,
                provider_code=details.get("code") if isinstance(details, dict) else None,
                provider_type=details.get("type") if isinstance(details, dict) else None,
                http_status=status if isinstance(status, int) else None,
            )

    def _consume_collaboration(self, item: dict[str, Any]) -> None:
        tool = item.get("tool") if isinstance(item.get("tool"), str) else "unknown"
        status = item.get("status") if isinstance(item.get("status"), str) else "unknown"
        self.collaboration_tool_counts[tool] = self.collaboration_tool_counts.get(tool, 0) + 1
        self.collaboration_status_counts[status] = self.collaboration_status_counts.get(status, 0) + 1
        receivers = item.get("receiver_thread_ids")
        if isinstance(receivers, list):
            for receiver in receivers:
                if isinstance(receiver, str) and receiver:
                    self.collaboration_receiver_hashes.add(hashlib.sha256(receiver.encode("utf-8")).hexdigest())

    def consume(self, line: str) -> None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            self.invalid_line_count += 1
            self.event_category = "invalid"
            return
        if not isinstance(event, dict):
            self.invalid_line_count += 1
            self.event_category = "invalid"
            return
        event_type = event.get("type")
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            self.thread_id = event["thread_id"]
            self.event_category = "thread"
        elif event_type in {"item.completed", "response.output_item.done"}:
            item = event.get("item", event.get("output_item"))
            item_type = item.get("type") if isinstance(item, dict) else ""
            if item_type in {"agent_message", "message"}:
                text = _message_text(item)
                if text:
                    self.final_message = text
                self.event_category = "message"
            elif item_type in {
                "command_execution",
                "collab_tool_call",
                "file_change",
                "function_call",
                "mcp_tool_call",
                "tool_call",
                "web_search",
            }:
                self.tool_count += 1
                if item_type == "collab_tool_call" and isinstance(item, dict):
                    self._consume_collaboration(item)
                self.event_category = "tool"
            elif item_type == "reasoning":
                self.event_category = "internal"
            else:
                self.event_category = "item"
        elif event_type in {"turn.completed", "response.completed"}:
            self.turn_completed = True
            self.event_category = "turn-completed"
            raw_usage = event.get("usage")
            if raw_usage is None and isinstance(event.get("response"), dict):
                raw_usage = event["response"].get("usage")
            self.usage = _usage_payload(raw_usage)
        elif event_type in {"turn.failed", "response.failed"}:
            self.turn_failed = True
            self.event_category = "turn-failed"
            self.usage = _usage_payload(event.get("usage"))
            self._consume_structured_error(str(event_type), event)
        elif event_type == "error":
            self.turn_failed = True
            self.event_category = "error"
            self._consume_structured_error("error", event)
        else:
            self.event_category = "event"

    def result(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "final_message": self.final_message,
            "usage": self.usage,
            "turn_completed": self.turn_completed,
            "turn_failed": self.turn_failed,
            "invalid_line_count": self.invalid_line_count,
            "event_category": self.event_category,
            "tool_count": self.tool_count,
            "structured_error_summary": {
                "count": self.structured_error_count,
                "sources": sorted(self.structured_error_sources),
            },
            "collaboration_summary": {
                "spawn_count": self.collaboration_tool_counts.get("spawn_agent", 0),
                "receiver_count": len(self.collaboration_receiver_hashes),
                "receiver_id_sha256": sorted(self.collaboration_receiver_hashes),
                "tool_counts": dict(sorted(self.collaboration_tool_counts.items())),
                "status_counts": dict(sorted(self.collaboration_status_counts.items())),
            },
        }


def reduce_event_lines(lines: Iterable[str]) -> dict:
    reducer = _EventReducer()
    for line in lines:
        reducer.consume(line)
    return reducer.result()


def build_execution_plan() -> list[dict]:
    plan: list[dict[str, Any]] = []

    def add(case: str, arm: str, round_id: int, session_mode: str) -> None:
        call_id = f"{case}--{arm}--r{round_id}"
        prompt_ref = f"arms/{case}/{arm}/TASK.md"
        if case == "engineering-continuity" and round_id > 1:
            prompt_ref = f"prompts/{case}/round-{round_id}.md"
        plan.append(
            {
                "call_id": call_id,
                "case": case,
                "arm": arm,
                "round": round_id,
                "codex_home": "ds-lite" if arm == "ds-lite" else "control",
                "workspace_surface": "wsl" if case == "numerical-seeds" else "windows",
                "workspace_ref": f"arms/{case}/{arm}",
                "prompt_ref": prompt_ref,
                "result_ref": f"results/executions/{call_id}.json",
                "session_mode": session_mode,
                "delete_session_after": case == "engineering-continuity" and round_id == 2,
            }
        )

    for arm in ("plain", "scratchpad", "ds-lite"):
        add("engineering-continuity", arm, 1, "temporary-new")
        add("engineering-continuity", arm, 2, "temporary-resume")
        add("engineering-continuity", arm, 3, "ephemeral")
    for arm in ("scratchpad", "ds-lite", "plain"):
        add("math-counterexample", arm, 1, "ephemeral")
    for arm in ("ds-lite", "plain", "scratchpad"):
        add("numerical-seeds", arm, 1, "ephemeral")
    for arm in ("plain", "ds-lite", "scratchpad"):
        add("idea-evaluation", arm, 1, "ephemeral")
    return plan


def build_progress_context(
    item: dict[str, Any], *, call_number: int, total_calls: int
) -> dict[str, Any]:
    if call_number < 1 or total_calls < call_number:
        raise PilotError("progress call number must be within the execution plan")
    receipt_ref = _validate_relative_ref(item.get("result_ref"), "progress.receipt_ref")
    return {
        "call_number": call_number,
        "total_calls": total_calls,
        "receipt_ref": receipt_ref,
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_fresh_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _inventory_digest(inventory: dict[str, str]) -> str:
    return hashlib.sha256(_canonical_json_bytes(inventory)).hexdigest()


def reconcile_attempt_retry(
    result: dict[str, Any],
    *,
    before_inventory: dict[str, str],
    after_inventory: dict[str, str],
    attempt_number: int,
    max_attempts: int,
) -> dict[str, Any]:
    """Decide whether a fresh call attempt is safe after a terminal failure."""
    if attempt_number < 1 or max_attempts < 1:
        raise PilotError("attempt numbers and budget must be positive")
    effect_absent = before_inventory == after_inventory
    base = {
        "schema_version": "ds-lite.matched-pilot-attempt-reconciliation.v1",
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "before_inventory_sha256": _inventory_digest(before_inventory),
        "after_inventory_sha256": _inventory_digest(after_inventory),
        "effect_absent": effect_absent,
        "delay_seconds": 0,
    }
    status = result.get("status")
    diagnostic = result.get("extensions", {}).get("process_diagnostic", {})
    failure_class = diagnostic.get("failure_class", "unknown")
    http_category = diagnostic.get("http_status_category", "none")
    if status == "ambiguous" or failure_class == "ambiguous":
        return {**base, "disposition": "blocked", "reason": "ambiguous-effect"}
    if status == "completed":
        return {**base, "disposition": "terminal", "reason": "completed"}
    if not effect_absent:
        return {**base, "disposition": "blocked", "reason": "workspace-effect-observed"}
    if attempt_number >= max_attempts:
        return {**base, "disposition": "blocked", "reason": "attempt-budget-exhausted"}
    transient = failure_class in {"network", "rate-limit", "timeout"} or (
        failure_class == "protocol" and http_category == "5xx"
    )
    if not transient:
        return {**base, "disposition": "blocked", "reason": "non-retryable-failure"}
    if failure_class == "rate-limit":
        delay = 30 * attempt_number
    elif http_category == "5xx":
        delay = 15 * attempt_number
    else:
        delay = 5 * (2 ** (attempt_number - 1))
    return {**base, "disposition": "retry", "reason": "transient-effect-absent", "delay_seconds": delay}


def _attempt_ref(item: dict[str, Any], attempt_number: int) -> str:
    return f"results/execution-attempts/{item['call_id']}/attempt-{attempt_number:03d}.json"


def _attempt_index_ref(item: dict[str, Any]) -> str:
    return f"results/execution-index/{item['call_id']}.json"


def _attempt_receipts(windows: Path, item: dict[str, Any]) -> list[tuple[int, Path, dict[str, Any]]]:
    directory = windows / "results" / "execution-attempts" / item["call_id"]
    receipts: list[tuple[int, Path, dict[str, Any]]] = []
    if not directory.is_dir():
        return receipts
    for path in sorted(directory.glob("attempt-*.json")):
        match = re.fullmatch(r"attempt-([0-9]{3})\.json", path.name)
        if match:
            receipts.append((int(match.group(1)), path, _read_json(path)))
    return receipts


def _ensure_success_index(windows: Path, item: dict[str, Any], attempt_number: int, attempt_path: Path) -> dict[str, Any]:
    content = attempt_path.read_bytes()
    canonical_path = windows / item["result_ref"]
    if canonical_path.exists():
        if canonical_path.read_bytes() != content:
            raise PilotError(f"canonical execution conflicts with successful attempt: {item['call_id']}")
    else:
        _write_fresh_bytes(canonical_path, content)
    attempts = _attempt_receipts(windows, item)
    index = {
        "schema_version": "ds-lite.matched-pilot-call-index.v1",
        "call_id": item["call_id"],
        "canonical_attempt_number": attempt_number,
        "canonical_ref": item["result_ref"],
        "canonical_sha256": hashlib.sha256(content).hexdigest(),
        "attempts": [
            {
                "attempt_number": number,
                "attempt_ref": path.relative_to(windows).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "status": payload.get("status"),
            }
            for number, path, payload in attempts
        ],
        "completed_at": _read_json(attempt_path).get("completed_at", ""),
        "extensions": {},
    }
    index_path = windows / _attempt_index_ref(item)
    index_bytes = _canonical_json_bytes(index)
    if index_path.exists():
        if index_path.read_bytes() != index_bytes:
            raise PilotError(f"canonical execution index conflicts: {item['call_id']}")
    else:
        _write_fresh_bytes(index_path, index_bytes)
    return index


def persist_terminal_attempt(
    windows_root: Path | str,
    item: dict[str, Any],
    result: dict[str, Any],
    *,
    attempt_number: int,
) -> dict[str, Any]:
    """Freeze one terminal attempt and, on success, its canonical call result."""
    windows = Path(windows_root)
    if result.get("status") in {"pending", "running"}:
        raise PilotError("only terminal attempts can be persisted")
    if result.get("call_id") != item.get("call_id"):
        raise PilotError("attempt call identity does not match the execution plan")
    validate_execution(result)
    attempt_ref = _attempt_ref(item, attempt_number)
    attempt_path = windows / attempt_ref
    content = _canonical_json_bytes(result)
    _write_fresh_bytes(attempt_path, content)
    response = {
        "attempt_ref": attempt_ref,
        "attempt_sha256": hashlib.sha256(content).hexdigest(),
        "index_ref": "",
    }
    if result.get("status") == "completed":
        _ensure_success_index(windows, item, attempt_number, attempt_path)
        response["index_ref"] = _attempt_index_ref(item)
    return response


def run_call_attempt_sequence(
    windows_root: Path | str,
    *,
    workspace: Path | str,
    item: dict[str, Any],
    base_execution: dict[str, Any],
    invoke: Callable[[int, dict[str, Any], Path], dict[str, Any]],
    max_attempts: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
    finalize_result: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    authorized_retry: bool = False,
    authorization_ref: str = "",
) -> dict[str, Any]:
    """Run or recover one logical call without overwriting terminal attempts."""
    windows = Path(windows_root)
    workdir = Path(workspace)
    attempts = _attempt_receipts(windows, item)
    successful = [(number, path, value) for number, path, value in attempts if value.get("status") == "completed"]
    if len(successful) > 1:
        raise PilotError(f"multiple successful attempts observed: {item['call_id']}")
    if successful:
        number, path, value = successful[0]
        _ensure_success_index(windows, item, number, path)
        return value

    next_attempt = 1
    operator_authorization: dict[str, Any] | None = None
    if attempts:
        number, prior_path, prior = attempts[-1]
        reconciliation = prior.get("extensions", {}).get("attempt_reconciliation", {})
        if reconciliation.get("disposition") != "retry":
            diagnostic = prior.get("extensions", {}).get("process_diagnostic", {})
            event_summary = prior.get("extensions", {}).get("event_summary", {})
            operator_already_used = any(
                bool(value.get("extensions", {}).get("operator_retry_authorization"))
                for _attempt, _receipt, value in attempts
            )
            exact_terminal_auth = (
                prior.get("status") == "failed"
                and prior.get("stop_reason") == "process-failed"
                and diagnostic.get("failure_class") == "auth"
                and event_summary.get("turn_failed") is True
                and reconciliation.get("effect_absent") is True
                and reconciliation.get("reason") == "non-retryable-failure"
            )
            exact_wsl_precondition = (
                prior.get("status") == "blocked"
                and prior.get("stop_reason") == "precondition"
                and prior.get("case") == "numerical-seeds"
                and prior.get("wsl", {}).get("status") == "missing"
                and event_summary.get("turn_completed") is True
                and reconciliation.get("effect_absent") is True
            )
            if not (
                authorized_retry
                and (exact_terminal_auth or exact_wsl_precondition)
                and not operator_already_used
                and number < max_attempts
            ):
                return prior
            _validate_id(authorization_ref, "authorization_ref")
            operator_authorization = {
                "schema_version": "ds-lite.matched-pilot-operator-retry.v1",
                "authorization_ref": authorization_ref,
                "prior_attempt_number": number,
                "prior_attempt_ref": prior_path.relative_to(windows).as_posix(),
                "prior_attempt_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
                "prior_terminal_turn_failed": event_summary.get("turn_failed") is True,
                "prior_terminal_turn_completed": event_summary.get("turn_completed") is True,
                "prior_effect_absent": True,
            }
        if number >= max_attempts:
            return prior
        next_attempt = number + 1

    runtime_dir = windows / "results" / "runtime" / item["call_id"]
    if runtime_dir.is_dir():
        known = {number for number, _path, _value in attempts}
        unfinished = []
        for path in runtime_dir.glob("attempt-*.json"):
            match = re.fullmatch(r"attempt-([0-9]{3})\.json", path.name)
            if match and int(match.group(1)) not in known:
                unfinished.append(path)
        if unfinished:
            raise PilotError(f"unfinished call attempt is ambiguous: {item['call_id']}")

    for attempt_number in range(next_attempt, max_attempts + 1):
        execution = dict(base_execution)
        execution["execution_id"] = f"execution:{item['call_id']}:attempt:{attempt_number}"
        if operator_authorization is not None and attempt_number == next_attempt:
            execution["extensions"] = {
                **execution.get("extensions", {}),
                "operator_retry_authorization": operator_authorization,
            }
        before = _inventory(workdir)
        runtime_path = runtime_dir / f"attempt-{attempt_number:03d}.json"
        result = invoke(attempt_number, execution, runtime_path)
        if finalize_result is not None:
            result = finalize_result(result)
        after = _inventory(workdir)
        reconciliation = reconcile_attempt_retry(
            result,
            before_inventory=before,
            after_inventory=after,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
        )
        result = dict(result)
        result["extensions"] = {
            **result.get("extensions", {}),
            "attempt_reconciliation": reconciliation,
        }
        if operator_authorization is not None and attempt_number == next_attempt:
            result["extensions"]["operator_retry_authorization"] = operator_authorization
        validate_execution(result)
        persist_terminal_attempt(windows, item, result, attempt_number=attempt_number)
        if result.get("status") == "completed":
            return result
        if reconciliation["disposition"] != "retry":
            return result
        sleep_fn(float(reconciliation["delay_seconds"]))
    raise PilotError(f"attempt sequence exhausted without a terminal disposition: {item['call_id']}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}


def _git_commit(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PilotError("cannot resolve source git commit")
    return completed.stdout.strip()


def _inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
        if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }


def prepare_pilot(
    windows_root: Path | str,
    wsl_root: Path | str,
    *,
    repo_root: Path | str = REPO_ROOT,
    pilot_id: str,
    authorization_ref: str,
) -> dict[str, Any]:
    from lab_runner import MatchedPilotBuilder

    windows = Path(windows_root)
    wsl = Path(wsl_root)
    repository = Path(repo_root).resolve()
    _validate_id(pilot_id, "pilot_id")
    _validate_id(authorization_ref, "authorization_ref")
    if pilot_id in FROZEN_PILOT_IDS:
        raise PilotError("frozen pilot id cannot be prepared, resumed, or overwritten")
    for label, path in (("windows_root", windows), ("wsl_root", wsl)):
        if path.exists():
            raise PilotError(f"{label} already exists; refusing to overwrite: {path}")

    MatchedPilotBuilder(windows).build()
    wsl_numerical = wsl / "arms" / "numerical-seeds"
    wsl_numerical.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(windows / "arms" / "numerical-seeds", wsl_numerical, ignore=_copy_ignore)

    canary_root = windows / "canary"
    shutil.copytree(
        windows / "arms" / "engineering-continuity" / "ds-lite",
        canary_root / "workspace",
        ignore=_copy_ignore,
    )
    (canary_root / "PROMPT.md").write_text(CANARY_PROMPT, encoding="utf-8")

    plugin_source = repository / "plugins" / "deepscientist-lite-core"
    snapshot_plugin = windows / "source-snapshot" / "plugins" / "deepscientist-lite-core"
    shutil.copytree(plugin_source, snapshot_plugin, ignore=_copy_ignore)
    plugin_manifest = _read_json(snapshot_plugin / ".codex-plugin" / "plugin.json")
    source = {
        "git_commit": _git_commit(repository),
        "tree_digest": _tree_digest(snapshot_plugin),
        "plugin_version": plugin_manifest["version"],
        "skill_count": len([
            path
            for path in (snapshot_plugin / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ]),
        "extensions": {"working_tree_snapshot": True},
    }
    if source["skill_count"] != EXPECTED_SKILL_COUNT:
        raise PilotError(f"frozen source snapshot must contain exactly {EXPECTED_SKILL_COUNT} skills")
    _write_json(windows / "source-snapshot" / "SOURCE_IDENTITY.json", source)

    manifest_path = windows / "pilot-manifest.json"
    manifest = _read_json(manifest_path)
    manifest["pilot_id"] = pilot_id
    manifest["control_policy"] = {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "codex_cli_version": CODEX_VERSION,
        "per_call_timeout_seconds": 900,
        "prompt_budget": "one bounded task prompt per call",
        "tool_policy": "same host tools; arm-specific continuity treatment only",
        "material_digest_algorithm": "sha256",
        "actual_execution_authorization": authorization_ref,
    }
    _write_json(manifest_path, manifest)
    plan = {
        "schema_version": "ds-lite.matched-pilot-plan.v1",
        "pilot_id": pilot_id,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "codex_cli_version": CODEX_VERSION,
        "call_timeout_seconds": 900,
        "calls": build_execution_plan(),
        "extensions": {},
    }
    _write_json(windows / "execution-plan.json", plan)
    _write_json(
        windows / "layout.json",
        {
            "schema_version": "ds-lite.matched-pilot-layout.v1",
            "pilot_id": pilot_id,
            "surfaces": {
                "windows": {"root_ref": ".", "case_refs": [f"arms/{case}" for case in ("engineering-continuity", "math-counterexample", "idea-evaluation")]},
                "wsl": {"root_ref": ".", "case_refs": ["arms/numerical-seeds"], "distribution": "DS-Lite-Ubuntu-24.04"},
            },
            "extensions": {},
        },
    )
    inventories = {}
    for item in build_execution_plan():
        surface_root = wsl if item["workspace_surface"] == "wsl" else windows
        key = f"{item['case']}--{item['arm']}"
        inventories.setdefault(key, _inventory(surface_root / item["workspace_ref"]))
    _write_json(windows / "results" / "baseline-files.json", inventories)
    _write_json(
        windows / "runtime-state.json",
        {
            "schema_version": "ds-lite.matched-pilot-runtime.v1",
            "pilot_id": pilot_id,
            "status": "prepared",
            "completed_calls": [],
            "blocking_calls": [],
            "extensions": {},
        },
    )
    return {"pilot_id": pilot_id, "source": source, "call_count": len(plan["calls"])}


_NONSECRET_PROVIDER_KEYS = {
    "name",
    "base_url",
    "wire_api",
    "query_params",
    "requires_openai_auth",
    "stream_idle_timeout_ms",
    "env_key",
}
_AUTH_ENV_KEY = "OPENAI_API_KEY"
_REQUIRED_PROVIDER_ROUTE_FIELDS = {"base_url", "name", "requires_openai_auth", "wire_api"}
_SENSITIVE_CONFIG_PARTS = {
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "header",
    "environment",
    "env",
}


def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    raise PilotError("provider config contains an unsupported value")


def _clone_nonsecret_provider_config(source_codex_home: Path, target_home: Path) -> tuple[list[str], dict[str, Any]]:
    """Clone only the provider route needed for a canary, never credentials or global config."""
    lines = [
        f'model = {json.dumps(MODEL)}',
        f'model_reasoning_effort = {json.dumps(REASONING_EFFORT)}',
    ]
    status: dict[str, Any] = {
        "status": "not-found",
        "catalog_copied": False,
        "catalog_configured": False,
        "provider_route_copied": False,
        "route_fidelity": {
            "source_fields_present": [],
            "copied_fields_present": [],
            "required_fields_match": False,
            "request_max_retries": 0,
            "stream_max_retries": 0,
        },
    }
    config_path = source_codex_home / "config.toml"
    if not config_path.is_file():
        return lines, status
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        status["status"] = "invalid"
        return lines, status

    provider_name = config.get("model_provider")
    catalog_ref = config.get("model_catalog_json")
    provider_table = config.get("model_providers", {}).get(provider_name, {}) if isinstance(provider_name, str) else {}
    if provider_name == "custom" and isinstance(provider_table, dict):
        lines.insert(0, 'model_provider = "custom"')
        safe_items: list[tuple[str, Any]] = []
        for key, value in provider_table.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized not in _NONSECRET_PROVIDER_KEYS:
                continue
            if any(part in normalized for part in _SENSITIVE_CONFIG_PARTS):
                continue
            if isinstance(value, (dict, tuple)):
                continue
            safe_items.append((str(key), value))
        if provider_table.get("requires_openai_auth") is True and not any(
            str(key).lower().replace("-", "_") == "env_key" for key, _ in safe_items
        ):
            safe_items.append(("env_key", _AUTH_ENV_KEY))
        if safe_items:
            lines.extend(["", "[model_providers.custom]"])
            lines.extend(f"{key} = {_toml_literal(value)}" for key, value in safe_items)
            lines.append("request_max_retries = 0")
            lines.append("stream_max_retries = 0")
            source_by_key = {
                str(key).lower().replace("-", "_"): value
                for key, value in safe_items
            }
            try:
                copied_config = tomllib.loads("\n".join(lines))
                copied_provider = copied_config.get("model_providers", {}).get("custom", {})
            except (ValueError, tomllib.TOMLDecodeError):
                copied_provider = {}
            source_present = sorted(_REQUIRED_PROVIDER_ROUTE_FIELDS & set(source_by_key))
            copied_present = sorted(_REQUIRED_PROVIDER_ROUTE_FIELDS & set(copied_provider)) if isinstance(copied_provider, dict) else []
            required_match = (
                source_present == sorted(_REQUIRED_PROVIDER_ROUTE_FIELDS)
                and copied_present == source_present
                and all(copied_provider.get(key) == source_by_key.get(key) for key in _REQUIRED_PROVIDER_ROUTE_FIELDS)
            )
            status["route_fidelity"] = {
                "source_fields_present": source_present,
                "copied_fields_present": copied_present,
                "required_fields_match": required_match,
                "request_max_retries": copied_provider.get("request_max_retries") if isinstance(copied_provider, dict) else None,
                "stream_max_retries": copied_provider.get("stream_max_retries") if isinstance(copied_provider, dict) else None,
                "auth_env_key_configured": (
                    copied_provider.get("env_key") == _AUTH_ENV_KEY
                    if isinstance(copied_provider, dict) and copied_provider.get("requires_openai_auth") is True
                    else True
                ),
            }
            status["provider_route_copied"] = required_match and status["route_fidelity"]["auth_env_key_configured"]
            if not required_match:
                status["status"] = "invalid"

    if isinstance(catalog_ref, str) and catalog_ref and "\\" not in catalog_ref:
        status["catalog_configured"] = True
        catalog_path = PurePosixPath(catalog_ref)
        if not catalog_path.is_absolute() and all(part not in {"", ".", ".."} for part in catalog_path.parts):
            source_catalog = source_codex_home.joinpath(*catalog_path.parts)
            target_catalog = target_home.joinpath(*catalog_path.parts)
            if source_catalog.is_file():
                target_catalog.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_catalog, target_catalog)
                lines.insert(1, f"model_catalog_json = {json.dumps(catalog_ref)}")
                status["catalog_copied"] = True
            else:
                status["status"] = "invalid"
        else:
            status["status"] = "invalid"
    status["status"] = "copied" if status["status"] == "not-found" and (status["provider_route_copied"] or status["catalog_copied"]) else status["status"]
    return lines, status


def clone_nonsecret_provider_config(
    source_codex_home: Path | str,
    target_home: Path | str,
) -> tuple[list[str], dict[str, Any]]:
    """Expose the redacted provider clone for staged acceptance preflight."""
    return _clone_nonsecret_provider_config(Path(source_codex_home), Path(target_home))


def install_homes(windows_root: Path | str, **_kwargs: Any) -> dict[str, Any]:
    windows = Path(windows_root)
    snapshot_plugin = windows / "source-snapshot" / "plugins" / "deepscientist-lite-core"
    source = _read_json(windows / "source-snapshot" / "SOURCE_IDENTITY.json")
    homes_root = windows / "homes"
    if homes_root.exists():
        raise PilotError("isolated homes already exist; refusing to overwrite")
    control = homes_root / "control"
    ds_lite = homes_root / "ds-lite"
    (control / "skills").mkdir(parents=True)
    (ds_lite / "skills").mkdir(parents=True)
    source_codex_home = Path(_kwargs.get("source_codex_home") or os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    control_config, control_status = clone_nonsecret_provider_config(source_codex_home, control)
    ds_lite_config, ds_lite_status = clone_nonsecret_provider_config(source_codex_home, ds_lite)
    (control / "config.toml").write_text("\n".join(control_config) + "\n", encoding="utf-8")
    (ds_lite / "config.toml").write_text("\n".join(ds_lite_config) + "\n", encoding="utf-8")
    skill_names = []
    for source_skill in sorted((snapshot_plugin / "skills").iterdir()):
        if source_skill.is_dir():
            shutil.copytree(source_skill, ds_lite / "skills" / source_skill.name, ignore=_copy_ignore)
            if (source_skill / "SKILL.md").is_file():
                skill_names.append(source_skill.name)
    for support_name in ("assets", "references", "scripts"):
        shutil.copytree(snapshot_plugin / support_name, ds_lite / support_name, ignore=_copy_ignore)
    if len(skill_names) != EXPECTED_SKILL_COUNT:
        raise PilotError(f"DS Lite isolated home must install exactly {EXPECTED_SKILL_COUNT} skills")
    result = {
        "schema_version": "ds-lite.matched-pilot-homes.v1",
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "control": {"home_ref": "homes/control", "skills": [], "credential_files_copied": False},
        "ds_lite": {
            "home_ref": "homes/ds-lite",
            "skills": skill_names,
            "source_tree_digest": source["tree_digest"],
            "credential_files_copied": False,
        },
        "extensions": {
            "installation_kind": "isolated-skill-home",
            "cache_installation_verified": False,
            "provider_config": {
                "source": "local-nonsecret-config",
                "control": control_status,
                "ds_lite": ds_lite_status,
            },
        },
    }
    _write_json(windows / "home-manifest.json", result)
    return result


def resume_decision(records: list[dict]) -> dict:
    skip_completed = []
    blocking = []
    for record in records:
        call_id = str(record.get("call_id", "unknown-call"))
        status = record.get("status")
        stop_reason = record.get("stop_reason")
        if status == "completed" and stop_reason == "completed":
            skip_completed.append(call_id)
        elif status == "pending" and stop_reason == "not-started":
            continue
        else:
            blocking.append(call_id)
    if blocking:
        return {"action": "stop", "skip_completed": skip_completed, "blocking_calls": blocking}
    return {"action": "continue", "skip_completed": skip_completed, "blocking_calls": []}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reader(stream, label: str, events: queue.Queue[tuple[str, str | None]]) -> None:
    try:
        for line in iter(stream.readline, ""):
            events.put((label, line))
    finally:
        events.put((label, None))


def _command_prefix(codex_bin: Path) -> list[str]:
    if codex_bin.suffix.lower() == ".py":
        return [sys.executable, str(codex_bin)]
    if codex_bin.suffix.lower() == ".ps1":
        # subprocess cannot reliably invoke a PowerShell script through its
        # file association. Use the host explicitly so the isolated runner
        # has the same launch semantics as an interactive PowerShell call.
        return ["powershell.exe", "-NoProfile", "-File", str(codex_bin)]
    return [str(codex_bin)]


_TREE_KILLERS: set[subprocess.Popen[str]] = set()


def _reap_tree_killer(killer: subprocess.Popen[str]) -> None:
    try:
        killer.wait()
    finally:
        _TREE_KILLERS.discard(killer)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        # Do not synchronously wait for taskkill: a .cmd launcher can hold
        # inherited handles until its descendant's sleep exits. The terminal
        # receipt records any still-open pipes below instead of delaying.
        try:
            killer = subprocess.Popen(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _TREE_KILLERS.add(killer)
            threading.Thread(target=_reap_tree_killer, args=(killer,), daemon=True).start()
        except OSError:
            pass
        if process.poll() is None:
            process.kill()
    else:
        if process.poll() is None:
            process.terminate()
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()


def run_codex_call(
    *,
    codex_bin: Path | str,
    cwd: Path | str,
    codex_home: Path | str,
    prompt: str,
    record_path: Path | str,
    execution: dict,
    timeout_seconds: float,
    extra_env: dict[str, str] | None = None,
    codex_args: list[str] | None = None,
    progress_context: dict[str, Any] | None = None,
    progress_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    codex_path = Path(codex_bin)
    # The Codex CLI resolves -C and CODEX_HOME relative to its process cwd.
    # A pilot supplies paths from its root, so normalize them before spawning
    # to avoid interpreting an already-relative workspace a second time.
    workdir = Path(cwd).resolve()
    home = Path(codex_home).resolve()
    record = Path(record_path).resolve()
    home.mkdir(parents=True, exist_ok=True)
    running = dict(execution)
    running.update(
        {
            "status": "running",
            "elapsed_seconds": 0,
            "exit_code": None,
            "session_id": "",
            "final_message": "",
            "usage": _usage_payload({}),
            "stop_reason": "operator-stop",
            "started_at": _utc_now(),
            "completed_at": "",
        }
    )
    validate_execution(running)
    _write_json(record, running)

    progress_values = progress_context or {}
    progress = PilotProgress(
        call_number=int(progress_values.get("call_number", 1)),
        total_calls=int(progress_values.get("total_calls", 1)),
        case=str(execution.get("case", "unknown")),
        arm=str(execution.get("arm", "unknown")),
        round_number=int(execution.get("round", 0)),
        receipt_ref=str(progress_values.get("receipt_ref", record.name)),
        timeout_seconds=timeout_seconds,
        sink=progress_sink,
    )
    progress.start()

    argv = _command_prefix(codex_path)
    argv.extend(codex_args or ["exec", "--json", "--ephemeral", "--model", MODEL, "-c", f'model_reasoning_effort="{REASONING_EFFORT}"'])
    argv.append(prompt)
    env = os.environ.copy()
    env.update({"CODEX_HOME": str(home), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    if extra_env:
        env.update(extra_env)
    started = time.monotonic()
    stderr_reducer = transport_diagnostics.TransportDiagnosticReducer()
    reducer = _EventReducer(stderr_reducer)
    try:
        process = subprocess.Popen(
            argv,
            cwd=workdir,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        diagnostic = stderr_reducer.finalize(
            exit_code=None,
            timed_out=False,
            turn_completed=False,
            turn_failed=False,
            child_process_state="not-started",
            stdout_pipe_state="not-opened",
            stderr_pipe_state="not-opened",
        )
        failed = dict(running)
        extensions = dict(failed.get("extensions", {}))
        extensions["process_diagnostic"] = diagnostic
        failed.update(
            {
                "status": "failed",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "exit_code": None,
                "stop_reason": "process-failed",
                "completed_at": _utc_now(),
                "extensions": extensions,
            }
        )
        validate_execution(failed)
        _write_json(record, failed)
        progress.finish("failed", "process")
        return failed
    assert process.stdout is not None and process.stderr is not None
    events: queue.Queue[tuple[str, str | None]] = queue.Queue()
    stdout_thread = threading.Thread(target=_reader, args=(process.stdout, "stdout", events), daemon=True)
    stderr_thread = threading.Thread(target=_reader, args=(process.stderr, "stderr", events), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    closed = set()
    timed_out = False
    while len(closed) < 2 or process.poll() is None:
        # A Windows descendant can retain inherited stdout/stderr handles after
        # the Codex parent exits. A recorded successful terminal turn is enough
        # to close this invocation once its parent has exited; waiting for those
        # unrelated handles would convert a completed call into a timeout.
        if (
            process.poll() is not None
            and reducer.turn_completed
            and not reducer.turn_failed
        ):
            break
        if time.monotonic() - started > timeout_seconds:
            timed_out = True
            _terminate_process_tree(process)
            break
        try:
            label, line = events.get(timeout=0.05)
        except queue.Empty:
            progress.heartbeat()
            continue
        if line is None:
            closed.add(label)
        elif label == "stdout":
            reducer.consume(line)
            progress.observe(
                reducer.event_category,
                thread_established=bool(reducer.thread_id),
                tool_count=reducer.tool_count,
            )
        else:
            stderr_reducer.consume(line)
            progress.observe(
                "diagnostic",
                thread_established=bool(reducer.thread_id),
                tool_count=reducer.tool_count,
            )
    # A killed Windows .cmd tree can retain inherited pipe handles briefly. The
    # receipt must still become terminal promptly; record an open pipe instead
    # of serially waiting two seconds for reader threads that cannot close yet.
    stdout_thread.join(timeout=0.2)
    stderr_thread.join(timeout=0.2)
    stdout_pipe_state = "open-after-join" if stdout_thread.is_alive() else "closed"
    stderr_pipe_state = "open-after-join" if stderr_thread.is_alive() else "closed"
    while not events.empty():
        label, line = events.get_nowait()
        if line is not None:
            if label == "stdout":
                reducer.consume(line)
                progress.observe(
                    reducer.event_category,
                    thread_established=bool(reducer.thread_id),
                    tool_count=reducer.tool_count,
                )
            else:
                stderr_reducer.consume(line)
                progress.observe(
                    "diagnostic",
                    thread_established=bool(reducer.thread_id),
                    tool_count=reducer.tool_count,
                )
    # Closing a stream while its reader still owns an inherited Windows handle
    # can block until the descendant exits. Daemon readers release it once the
    # asynchronous tree termination completes; the receipt records that state.
    if not stdout_thread.is_alive():
        process.stdout.close()
    if not stderr_thread.is_alive():
        process.stderr.close()
    exit_code = process.poll()
    reduced = reducer.result()
    child_process_state = "terminated" if timed_out else "exited" if exit_code is not None else "running"
    diagnostic = stderr_reducer.finalize(
        exit_code=exit_code,
        timed_out=timed_out,
        turn_completed=reduced["turn_completed"],
        turn_failed=reduced["turn_failed"],
        child_process_state=child_process_state,
        stdout_pipe_state=stdout_pipe_state,
        stderr_pipe_state=stderr_pipe_state,
    )
    if timed_out:
        status, stop_reason = "timeout", "timeout"
        failure_category = "timeout"
    elif exit_code != 0:
        status, stop_reason = "failed", "process-failed"
        failure_category = diagnostic["category"]
    elif reduced["turn_completed"]:
        status, stop_reason = "completed", "completed"
        failure_category = "none"
    else:
        status, stop_reason = "ambiguous", "ambiguous-transport"
        failure_category = "transport-ambiguous"
    finished = dict(running)
    final_message = reduced["final_message"]
    for path, replacement in ((workdir, "<WORKSPACE>"), (home, "<CODEX_HOME>")):
        rendered = str(path.resolve())
        final_message = final_message.replace(rendered, replacement).replace(rendered.replace("\\", "/"), replacement)
    full_message = final_message
    if len(final_message) > 1000:
        final_message = final_message[:997].rstrip() + "..."
    extensions = dict(finished.get("extensions", {}))
    extensions["event_summary"] = {
        "turn_completed": reduced["turn_completed"],
        "turn_failed": reduced["turn_failed"],
        "invalid_line_count": reduced["invalid_line_count"],
        "tool_count": reduced["tool_count"],
        "final_message_chars": len(full_message),
        "final_message_sha256": hashlib.sha256(full_message.encode("utf-8")).hexdigest(),
        "final_message_truncated": len(full_message) > len(final_message),
        "structured_errors": reduced["structured_error_summary"],
        "collaboration": reduced["collaboration_summary"],
    }
    extensions["process_diagnostic"] = diagnostic
    finished.update(
        {
            "status": status,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "exit_code": exit_code,
            "session_id": reduced["thread_id"],
            "final_message": final_message,
            "usage": reduced["usage"],
            "stop_reason": stop_reason,
            "completed_at": _utc_now(),
            "extensions": extensions,
        }
    )
    validate_execution(finished)
    _write_json(record, finished)
    progress.finish(status, failure_category)
    return finished


def _codex_version(codex_bin: Path) -> str:
    completed = subprocess.run(
        [*_command_prefix(codex_bin), "--version"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0 or CODEX_VERSION not in output:
        raise PilotError(f"Codex CLI {CODEX_VERSION} is required")
    return CODEX_VERSION


def _run_probe(
    executable: Path | str,
    arguments: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    command = [*_command_prefix(Path(executable)), *arguments]
    try:
        completed = subprocess.run(
            command,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": None, "stdout": "", "stderr": ""}
    except OSError:
        return {"status": "unavailable", "returncode": None, "stdout": "", "stderr": ""}
    return {
        "status": "supported" if completed.returncode == 0 else "unsupported",
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def _mentioned_skill_names(text: str) -> list[str]:
    return [
        name
        for name in EXPECTED_SKILLS
        if re.search(rf"(?<![A-Za-z0-9-]){re.escape(name)}(?![A-Za-z0-9-])", text)
    ]


def _feature_summary(text: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in {"hooks", "plugins", "multi_agent", "plugin_hooks"}:
            result[parts[0]] = {"stage": parts[1], "enabled": parts[2].lower() == "true"}
    return result


def _update_runtime_probe(windows: Path, name: str, status: str, result_ref: str) -> None:
    state_path = windows / "runtime-state.json"
    state = _read_json(state_path)
    extensions = dict(state.get("extensions", {}))
    extensions[name] = {"status": status, "result_ref": result_ref}
    state["extensions"] = extensions
    _write_json(state_path, state)


def _windows_canary_preflight_ready(preflight: dict[str, Any]) -> bool:
    """Allow the Windows-only canary to progress past an isolated WSL outage."""
    blocking = preflight.get("blocking_reasons", [])
    return preflight.get("status") == "passed" or blocking == ["wsl-precondition"]


def _validated_wsl_host_probe(path: Path) -> bool:
    try:
        probe = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        probe.get("schema_version") == "ds-lite.wsl-host-probe.v1"
        and probe.get("status") == "passed"
        and probe.get("host") == "windows-powershell"
        and probe.get("distribution") == "DS-Lite-Ubuntu-24.04"
        and probe.get("assertion") == "uname-s-is-linux"
        and probe.get("exit_code") == 0
        and probe.get("raw_output_persisted") is False
    )


def preflight_pilot(
    windows_root: Path | str,
    wsl_root: Path | str,
    *,
    codex_bin: Path | str,
    wsl_bin: Path | str = Path("wsl.exe"),
    wsl_host_probe: Path | str | None = None,
) -> dict[str, Any]:
    windows = Path(windows_root)
    wsl = Path(wsl_root)
    source = _read_json(windows / "source-snapshot" / "SOURCE_IDENTITY.json")
    homes = _read_json(windows / "home-manifest.json")
    state = _read_json(windows / "runtime-state.json")
    snapshot = windows / "source-snapshot" / "plugins" / "deepscientist-lite-core"
    blocking: list[str] = []

    try:
        cli_version = _codex_version(Path(codex_bin))
    except PilotError:
        cli_version = "unavailable"
        blocking.append("cli-version")

    probe_env = os.environ.copy()
    probe_env.update(
        {
            "CODEX_HOME": str(windows / homes["ds_lite"]["home_ref"]),
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    auth_probe = _run_probe(codex_bin, ["login", "status"], env=probe_env)
    auth_text = f"{auth_probe['stdout']}\n{auth_probe['stderr']}".lower()
    host_authenticated = auth_probe["status"] == "supported" and (
        "logged in" in auth_text or "authenticated" in auth_text
    )
    environment_api_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    authenticated = host_authenticated or environment_api_key
    authentication_source = (
        "host-login"
        if host_authenticated
        else "environment-api-key"
        if environment_api_key
        else "unavailable"
    )
    if not authenticated:
        blocking.append("authentication")

    feature_probe = _run_probe(codex_bin, ["features", "list"], env=probe_env)
    features = _feature_summary(f"{feature_probe['stdout']}\n{feature_probe['stderr']}")
    if feature_probe["status"] != "supported" or "plugins" not in features:
        blocking.append("feature-enumeration")

    home_results: dict[str, Any] = {}
    provider_config = homes.get("extensions", {}).get("provider_config", {})
    if not all(
        isinstance(provider_config.get(name), dict)
        and provider_config[name].get("route_fidelity", {}).get("auth_env_key_configured", False)
        for name in ("control", "ds_lite")
    ):
        blocking.append("provider-auth-env-route")
    for name in ("control", "ds_lite"):
        home = windows / homes[name]["home_ref"]
        local_env = dict(probe_env)
        local_env["CODEX_HOME"] = str(home)
        prompt_probe = _run_probe(
            codex_bin,
            ["debug", "prompt-input", "DS Lite isolated preflight"],
            env=local_env,
        )
        prompt_text = prompt_probe["stdout"]
        prompt_skills = _mentioned_skill_names(prompt_text)
        installed_skills = list(homes[name]["skills"])
        home_results[name] = {
            "home_ref": homes[name]["home_ref"],
            "installation_kind": "isolated-skill-home",
            "installed_skill_names": installed_skills,
            "prompt_skill_names": prompt_skills,
            "prompt_digest": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "prompt_bytes": len(prompt_text.encode("utf-8")),
            "probe_status": prompt_probe["status"],
        }
    if home_results["control"]["prompt_skill_names"]:
        blocking.append("control-home-contaminated")
    if home_results["ds_lite"]["prompt_skill_names"] != list(EXPECTED_SKILLS):
        blocking.append("ds-lite-skill-discovery")

    wsl_host_probe_path = Path(wsl_host_probe) if wsl_host_probe is not None else None
    wsl_probe = _run_probe(wsl_bin, ["-d", "DS-Lite-Ubuntu-24.04", "--", "uname", "-s"])
    # WSL may emit a non-fatal environment translation warning alongside the
    # requested output.  The distribution probe remains strict about a zero
    # exit status, but accepts the expected standalone uname result in that
    # mixed output.
    wsl_available = (
        wsl_probe["status"] == "supported"
        and any(line.strip() == "Linux" for line in wsl_probe["stdout"].splitlines())
    )
    if wsl_host_probe_path is not None:
        wsl_available = _validated_wsl_host_probe(wsl_host_probe_path)
    if not wsl.exists() or not wsl_available:
        blocking.append("wsl-precondition")
    if _tree_digest(snapshot) != source["tree_digest"]:
        blocking.append("source-snapshot-drift")

    result = {
        "record_type": "matched-pilot-preflight",
        "pilot_id": state["pilot_id"],
        "status": "passed" if not blocking else "blocked",
        "source": {
            "tree_digest": source["tree_digest"],
            "plugin_version": source["plugin_version"],
            "skill_count": source["skill_count"],
        },
        "cli": {
            "version": cli_version,
            "authenticated": authenticated,
            "authentication_source": authentication_source,
            "features": features,
        },
        "homes": home_results,
        "wsl": {
            "distribution": "DS-Lite-Ubuntu-24.04",
            "available": wsl_available,
            "root_present": wsl.exists(),
        },
        "blocking_reasons": blocking,
        "extensions": {
            "cache_installation_verified": False,
            "raw_host_output_persisted": False,
            "provider_auth_env_route_configured": "provider-auth-env-route" not in blocking,
        },
    }
    _write_json(windows / "results" / "preflight.json", result)
    _update_runtime_probe(windows, "preflight", result["status"], "results/preflight.json")
    return result


def _prompt_text(windows: Path, surface_root: Path, item: dict[str, Any]) -> str:
    workspace = surface_root / item["workspace_ref"]
    instructions = (workspace / "ARM_INSTRUCTIONS.md").read_text(encoding="utf-8")
    prompt_path = surface_root / item["prompt_ref"]
    if not prompt_path.is_file():
        prompt_path = windows / item["prompt_ref"]
    task = prompt_path.read_text(encoding="utf-8")
    boundary = """

# Runtime boundary

Complete exactly this one bounded call, write the requested public artifacts, and stop. Do not delegate subagents. Do not read sibling arms, instructor materials, repository sources, credentials, or global Codex state. Do not save a full conversation, hidden reasoning, environment dump, or absolute workstation root.
"""
    if item["case"] == "numerical-seeds":
        boundary += """

All numerical computation must run through `wsl.exe -d DS-Lite-Ubuntu-24.04 -- bash materials/run_simulation_wsl.sh ...` from this arm workspace. Retain `early-wsl-proof.json` and `wsl-proof.json`. This is WSL computation evidence, not Linux Codex installation evidence.
"""
    return f"{instructions.rstrip()}\n\n{task.rstrip()}\n{boundary.rstrip()}\n"


def _base_execution(
    *,
    pilot_id: str,
    source: dict[str, Any],
    item: dict[str, Any],
    input_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": "ds-lite.matched-pilot-execution.v1",
        "execution_id": f"execution:{item['call_id']}",
        "pilot_id": pilot_id,
        "call_id": item["call_id"],
        "case": item["case"],
        "arm": item["arm"],
        "round": item["round"],
        "status": "pending",
        "source": source,
        "cli": {
            "name": "codex",
            "version": CODEX_VERSION,
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "extensions": {},
        },
        "input": {
            "workspace_surface": item["workspace_surface"],
            "workspace_ref": item["workspace_ref"],
            "prompt_ref": item["prompt_ref"],
            "input_digest": input_digest,
            "extensions": {},
        },
        "usage": _usage_payload({}),
        "elapsed_seconds": 0,
        "exit_code": None,
        "session_id": "",
        "final_message": "",
        "wsl": {
            "status": "missing" if item["case"] == "numerical-seeds" else "not-required",
            "distribution": "DS-Lite-Ubuntu-24.04" if item["case"] == "numerical-seeds" else "",
            "proof_ref": "",
            "extensions": {},
        },
        "stop_reason": "not-started",
        "result_refs": [item["result_ref"]],
        "started_at": "",
        "completed_at": "",
        "extensions": {},
    }


def _codex_args(item: dict[str, Any], workspace: Path, prior_session_id: str) -> list[str]:
    common = [
        "--json",
        "--model",
        MODEL,
        "-c",
        f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--skip-git-repo-check",
        "--ignore-rules",
    ]
    if item["session_mode"] == "temporary-resume":
        if not prior_session_id:
            raise PilotError(f"missing prior session for {item['call_id']}")
        # Stable 0.146.0 resume inherits cwd and sandbox from the exact session;
        # its command surface rejects the start-only -C and -s options.
        return ["exec", "resume", *common, "--ephemeral", prior_session_id]
    sandbox = "danger-full-access" if item.get("case") == "numerical-seeds" else "workspace-write"
    result = ["exec", *common, "-s", sandbox, "-C", str(workspace.resolve())]
    if item["session_mode"] == "ephemeral":
        result.append("--ephemeral")
    return result


def run_canary(
    windows_root: Path | str,
    *,
    codex_bin: Path | str,
    timeout_seconds: float = 180,
) -> dict[str, Any]:
    windows = Path(windows_root)
    preflight_path = windows / "results" / "preflight.json"
    if not preflight_path.is_file():
        raise PilotError("a preflight receipt is required before the real canary")
    preflight = _read_json(preflight_path)
    if not _windows_canary_preflight_ready(preflight):
        raise PilotError("Windows canary preflight is not ready")
    record_path = windows / "results" / "canary.json"
    if record_path.exists():
        raise PilotError("canary receipt already exists; refusing duplicate or retry")
    _codex_version(Path(codex_bin))

    state = _read_json(windows / "runtime-state.json")
    source = _read_json(windows / "source-snapshot" / "SOURCE_IDENTITY.json")
    workspace = windows / "canary" / "workspace"
    prompt_path = windows / "canary" / "PROMPT.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    if "$ds-lite" in prompt:
        raise PilotError("implicit canary prompt must not name a DS Lite skill explicitly")
    before = _inventory(workspace)
    item = {
        "call_id": "implicit-gateway-canary",
        "case": "engineering-continuity",
        "arm": "ds-lite",
        "round": 1,
        "workspace_surface": "windows",
        "workspace_ref": "canary/workspace",
        "prompt_ref": "canary/PROMPT.md",
        "result_ref": "results/canary.json",
    }
    execution = _base_execution(
        pilot_id=state["pilot_id"],
        source=source,
        item=item,
        input_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )
    execution["extensions"] = {
        "probe": {
            "kind": "implicit-gateway-canary",
            "explicit_skill_name_in_prompt": False,
        },
        "preflight_scope": "full" if preflight.get("status") == "passed" else "windows-only",
    }
    home = windows / "homes" / "ds-lite"
    args = [
        "exec",
        "--json",
        "--ephemeral",
        "--model",
        MODEL,
        "-c",
        f'model_reasoning_effort="{REASONING_EFFORT}"',
        "--skip-git-repo-check",
        "--ignore-rules",
        "-s",
        "read-only",
        "-C",
        str(workspace.resolve()),
    ]
    result = run_codex_call(
        codex_bin=codex_bin,
        cwd=workspace,
        codex_home=home,
        prompt=prompt,
        record_path=record_path,
        execution=execution,
        timeout_seconds=timeout_seconds,
        codex_args=args,
        progress_context={
            "call_number": 1,
            "total_calls": 1,
            "receipt_ref": "results/canary.json",
        },
    )
    after = _inventory(workspace)
    message = result["final_message"]
    observed = next(
        (name for name in sorted(EXPECTED_SKILLS, key=len, reverse=True) if name.lower() in message.lower()),
        "ds-lite" if "ds lite" in message.lower() else "",
    )
    event_summary = result.get("extensions", {}).get("event_summary", {})
    blocking: list[str] = []
    if result["status"] != "completed":
        blocking.append(f"execution-{result['status']}")
    if not message.strip():
        blocking.append("final-feedback")
    if result["usage"]["total_tokens"] <= 0:
        blocking.append("nonzero-usage")
    if event_summary.get("tool_count", 0) <= 0:
        blocking.append("tool-observation")
    if not observed:
        blocking.append("implicit-skill-evidence")
    if before != after:
        blocking.append("workspace-mutated")

    gate = acceptance_gate.start_gate(
        gate_id="canary-01",
        input_refs=["canary/PROMPT.md"],
        authorization_ref=str(_read_json(windows / "pilot-manifest.json")["control_policy"]["actual_execution_authorization"]),
        expected_observations=["thread.started", "turn.completed", "final.feedback", "tool.observed"],
    )
    for observation, present in (
        ("thread.started", bool(result.get("session_id"))),
        ("turn.completed", bool(event_summary.get("turn_completed"))),
        ("final.feedback", bool(message.strip())),
        ("tool.observed", event_summary.get("tool_count", 0) > 0),
    ):
        if present:
            acceptance_gate.record_observation(gate, observation)
    gate["usage"] = {"total_tokens": int(result["usage"].get("total_tokens", 0))}
    gate_status = "passed" if not blocking else ("ambiguous" if result["status"] == "ambiguous" else "blocked")
    gate_failure = "none" if gate_status == "passed" else ("transport" if result["status"] in {"timeout", "ambiguous", "failed"} else "observation")
    acceptance_gate.cross_check_artifacts(gate, evidence_refs=["results/canary.json"])
    acceptance_gate.finalize_gate(
        gate,
        status=gate_status,
        failure_category=gate_failure,
        next_action="continue to the next authorized gate" if gate_status == "passed" else "freeze this pilot and create a fresh authorized pilot before retrying",
    )

    canary = {
        "passed": not blocking,
        "observed_skill": observed,
        "workspace_unchanged": before == after,
        "blocking_reasons": blocking,
        "cache_installation_verified": False,
    }
    result["extensions"] = {**result.get("extensions", {}), "canary": canary, "acceptance_gate": gate}
    if result["status"] == "completed" and blocking:
        result["status"] = "blocked"
        result["stop_reason"] = "precondition"
    validate_execution(result)
    _write_json(record_path, result)
    _update_runtime_probe(windows, "canary", result["status"], "results/canary.json")
    return result


def _delete_session(codex_bin: Path, codex_home: Path, workspace: Path, session_id: str) -> bool:
    if not session_id:
        return False
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home.resolve())
    completed = subprocess.run(
        [*_command_prefix(codex_bin), "delete", session_id, "--force"],
        cwd=workspace.resolve(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _verify_wsl_artifacts(workspace: Path) -> tuple[bool, list[str]]:
    refs = []
    for name, minimum in (("early-wsl-proof.json", 2), ("wsl-proof.json", 20)):
        path = workspace / name
        if not path.is_file():
            return False, refs
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            return False, refs
        if (
            payload.get("schema_version") != "ds-lite.wsl-computation-proof.v1"
            or payload.get("distribution") != "DS-Lite-Ubuntu-24.04"
            or payload.get("kernel") != "Linux"
            or not isinstance(payload.get("seed_count"), int)
            or payload["seed_count"] < minimum
        ):
            return False, refs
        refs.append(name)
    return True, refs


def _execution_records(windows: Path, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for call_number, item in enumerate(plan, start=1):
        path = windows / item["result_ref"]
        if path.is_file():
            records.append(_read_json(path))
    return records


def _update_runtime_state(windows: Path, status: str, completed: list[str], blocking: list[str]) -> None:
    state = _read_json(windows / "runtime-state.json")
    state.update({"status": status, "completed_calls": completed, "blocking_calls": blocking})
    _write_json(windows / "runtime-state.json", state)


def execute_pilot(
    windows_root: Path | str,
    wsl_root: Path | str,
    *,
    codex_bin: Path | str,
    timeout_seconds: float = 900,
    resume: bool = False,
    max_attempts: int = 3,
    authorized_retry_calls: set[str] | None = None,
    authorization_ref: str = "",
) -> dict[str, Any]:
    windows = Path(windows_root)
    wsl = Path(wsl_root)
    codex_path = Path(codex_bin)
    authorized_calls = set(authorized_retry_calls or set())
    if authorized_calls:
        _validate_id(authorization_ref, "authorization_ref")
    _codex_version(codex_path)
    plan_payload = _read_json(windows / "execution-plan.json")
    plan = plan_payload["calls"]
    source = _read_json(windows / "source-snapshot" / "SOURCE_IDENTITY.json")
    if _tree_digest(windows / "source-snapshot" / "plugins" / "deepscientist-lite-core") != source["tree_digest"]:
        raise PilotError("frozen source snapshot changed after prepare")
    if not (windows / "home-manifest.json").is_file():
        raise PilotError("isolated homes are not installed")
    existing = _execution_records(windows, plan)
    if existing and not resume:
        raise PilotError("execution records already exist; use resume")
    decision = resume_decision(existing)
    if decision["action"] == "stop":
        _update_runtime_state(windows, "blocked", decision["skip_completed"], decision["blocking_calls"])
        raise PilotError(f"resume blocked by unsafe calls: {', '.join(decision['blocking_calls'])}")
    completed_ids = list(decision["skip_completed"])
    sessions: dict[str, str] = {}
    for record in existing:
        if record["case"] == "engineering-continuity" and record["round"] == 1 and record["status"] == "completed":
            sessions[record["arm"]] = record["session_id"]

    for call_number, item in enumerate(plan, start=1):
        if item["call_id"] in completed_ids:
            continue
        surface_root = wsl if item["workspace_surface"] == "wsl" else windows
        workspace = surface_root / item["workspace_ref"]
        prompt = _prompt_text(windows, surface_root, item)
        input_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        execution = _base_execution(
            pilot_id=plan_payload["pilot_id"],
            source=source,
            item=item,
            input_digest=input_digest,
        )
        home = windows / "homes" / item["codex_home"]
        args = _codex_args(item, workspace, sessions.get(item["arm"], ""))

        def invoke(_attempt_number: int, attempt_execution: dict[str, Any], runtime_path: Path) -> dict[str, Any]:
            return run_codex_call(
                codex_bin=codex_path,
                cwd=workspace,
                codex_home=home,
                prompt=prompt,
                record_path=runtime_path,
                execution=attempt_execution,
                timeout_seconds=timeout_seconds,
                codex_args=args,
                progress_context=build_progress_context(
                    item, call_number=call_number, total_calls=len(plan)
                ),
            )

        def finalize_result(result: dict[str, Any]) -> dict[str, Any]:
            if item["case"] == "numerical-seeds" and result["status"] == "completed":
                verified, proof_names = _verify_wsl_artifacts(workspace)
                result["wsl"] = {
                    "status": "verified" if verified else "missing",
                    "distribution": "DS-Lite-Ubuntu-24.04",
                    "proof_ref": f"{item['workspace_ref']}/wsl-proof.json" if verified else "",
                    "extensions": {},
                }
                if verified:
                    for proof_name in proof_names:
                        result["result_refs"].append(f"{item['workspace_ref']}/{proof_name}")
                else:
                    result["status"] = "blocked"
                    result["stop_reason"] = "precondition"
            if item["delete_session_after"] and result["status"] == "completed":
                original_session = sessions.get(item["arm"], "")
                deleted = _delete_session(codex_path, home, workspace, original_session)
                result["extensions"] = {**result["extensions"], "temporary_session_deleted": deleted}
                if deleted:
                    sessions.pop(item["arm"], None)
                else:
                    result["status"] = "blocked"
                    result["stop_reason"] = "precondition"
            validate_execution(result)
            return result

        result = run_call_attempt_sequence(
            windows,
            workspace=workspace,
            item=item,
            base_execution=execution,
            invoke=invoke,
            max_attempts=max_attempts,
            finalize_result=finalize_result,
            authorized_retry=item["call_id"] in authorized_calls,
            authorization_ref=authorization_ref,
        )
        if item["case"] == "engineering-continuity" and item["round"] == 1 and result["status"] == "completed":
            sessions[item["arm"]] = result["session_id"]
        if result["status"] != "completed":
            _update_runtime_state(windows, "blocked", completed_ids, [item["call_id"]])
            raise PilotError(f"execution stopped at {item['call_id']}: {result['stop_reason']}")
        completed_ids.append(item["call_id"])
        _update_runtime_state(windows, "running", completed_ids, [])
    _update_runtime_state(windows, "completed", completed_ids, [])
    return {"status": "completed", "completed_calls": completed_ids, "call_count": len(completed_ids)}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare and run the authorized DeepScientist Lite matched pilot.")
    subcommands = result.add_subparsers(dest="command", required=True)

    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--windows-root", type=Path, required=True)
    prepare.add_argument("--wsl-root", type=Path, required=True)
    prepare.add_argument("--pilot-id", required=True)
    prepare.add_argument("--authorization-ref", required=True)

    install = subcommands.add_parser("install", help="Install isolated skill homes; this is not cache installation.")
    install.add_argument("--windows-root", type=Path, required=True)

    preflight = subcommands.add_parser("preflight")
    preflight.add_argument("--windows-root", type=Path, required=True)
    preflight.add_argument("--wsl-root", type=Path, required=True)
    preflight.add_argument("--codex-bin", type=Path, required=True)
    preflight.add_argument("--wsl-bin", type=Path, default=Path("wsl.exe"))
    preflight.add_argument("--wsl-host-probe", type=Path)

    canary = subcommands.add_parser("canary")
    canary.add_argument("--windows-root", type=Path, required=True)
    canary.add_argument("--codex-bin", type=Path, required=True)
    canary.add_argument("--timeout-seconds", type=float, default=180)

    for name in ("run", "resume"):
        command = subcommands.add_parser(name)
        command.add_argument("--windows-root", type=Path, required=True)
        command.add_argument("--wsl-root", type=Path, required=True)
        command.add_argument("--codex-bin", type=Path, required=True)
        command.add_argument("--timeout-seconds", type=float, default=900)
        command.add_argument("--max-attempts", type=int, default=3)
        command.add_argument("--authorized-retry-call", action="append", default=[])
        command.add_argument("--authorization-ref", default="")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_pilot(
                args.windows_root,
                args.wsl_root,
                pilot_id=args.pilot_id,
                authorization_ref=args.authorization_ref,
            )
        elif args.command == "install":
            result = install_homes(args.windows_root)
        elif args.command == "preflight":
            result = preflight_pilot(
                args.windows_root,
                args.wsl_root,
                codex_bin=args.codex_bin,
                wsl_bin=args.wsl_bin,
                wsl_host_probe=args.wsl_host_probe,
            )
        elif args.command == "canary":
            result = run_canary(
                args.windows_root,
                codex_bin=args.codex_bin,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = execute_pilot(
                args.windows_root,
                args.wsl_root,
                codex_bin=args.codex_bin,
                timeout_seconds=args.timeout_seconds,
                resume=args.command == "resume",
                max_attempts=args.max_attempts,
                authorized_retry_calls=set(args.authorized_retry_call),
                authorization_ref=args.authorization_ref,
            )
    except (PilotError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"pilot runtime failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.command == "preflight" and result.get("status") != "passed":
        return 2
    if args.command == "canary" and result.get("status") != "completed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
