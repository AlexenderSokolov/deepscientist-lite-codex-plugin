#!/usr/bin/env python3
"""Audit redacted real-host Hook and bounded delegation evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = REPO_ROOT / "plugins" / "deepscientist-lite" / "scripts"
if str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))

import ds_lite_protocol  # noqa: E402


HOOK_SCHEMA = "ds-lite.hook-host-event.v1"
HOOK_FIELDS = {"schema_version", "event_type", "decision"}
HOOK_EVENTS = {"user-prompt-submit", "pre-tool-use", "post-tool-use", "stop"}
HOOK_DECISIONS = {"allow", "block"}
INTEGRATION_SCHEMA = "ds-lite.parent-integration.v1"
INTEGRATION_FIELDS = {
    "schema_version",
    "integration_owner",
    "integration_ref",
    "result_refs",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HostAcceptanceError(RuntimeError):
    pass


def _relative_ref(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise HostAcceptanceError("evidence must stay inside the acceptance root") from exc
    ref = relative.as_posix()
    if not ref or any(part in {"", ".", ".."} for part in PurePosixPath(ref).parts):
        raise HostAcceptanceError("evidence ref is invalid")
    return ref


def _resolve_ref(root: Path, ref: str) -> Path:
    if not isinstance(ref, str) or not ref or "\\" in ref or ":" in ref:
        raise HostAcceptanceError("artifact refs must be relative POSIX paths")
    path = PurePosixPath(ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HostAcceptanceError("artifact ref escapes the acceptance root")
    resolved = (root / Path(*path.parts)).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise HostAcceptanceError("artifact ref escapes the acceptance root") from exc
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HostAcceptanceError("host evidence is not readable JSON") from exc
    if not isinstance(value, dict):
        raise HostAcceptanceError("host evidence must be a JSON object")
    return value


def summarize_hook_receipts(root: Path | str, event_directory: Path | str) -> dict[str, Any]:
    acceptance_root = Path(root)
    directory = Path(event_directory)
    _relative_ref(acceptance_root, directory)
    if not directory.is_dir():
        raise HostAcceptanceError("Hook event directory is missing")
    events = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if set(payload) != HOOK_FIELDS or payload.get("schema_version") != HOOK_SCHEMA:
            raise HostAcceptanceError("Hook receipt fields or schema are invalid")
        event_type = payload.get("event_type")
        decision = payload.get("decision")
        if event_type not in HOOK_EVENTS or decision not in HOOK_DECISIONS:
            raise HostAcceptanceError("Hook receipt event or decision is invalid")
        events.append(
            {
                "event_type": event_type,
                "decision": decision,
                "evidence_ref": _relative_ref(acceptance_root, path),
            }
        )
    user_events = [item["decision"] for item in events if item["event_type"] == "user-prompt-submit"]
    pre_events = [item["decision"] for item in events if item["event_type"] == "pre-tool-use"]
    post_events = [item["decision"] for item in events if item["event_type"] == "post-tool-use"]
    stop_events = [item["decision"] for item in events if item["event_type"] == "stop"]
    passed = (
        "allow" in user_events
        and "block" in pre_events
        and "allow" in post_events
        and stop_events == ["block", "allow"]
    )
    if not passed:
        raise HostAcceptanceError("Hook receipts do not prove the required real-host sequence")
    return {
        "status": "passed",
        "host_loading": "verified",
        "events": events,
        "stop_continuation_count": 1,
        "raw_hook_input_persisted": False,
    }


def audit_delegation(
    root: Path | str,
    *,
    execution: dict[str, Any],
    delegation: dict[str, Any],
    integration_receipt_path: Path | str,
) -> dict[str, Any]:
    acceptance_root = Path(root)
    if execution.get("status") != "completed":
        raise HostAcceptanceError("parent execution is not completed")
    collaboration = (
        execution.get("extensions", {})
        .get("event_summary", {})
        .get("collaboration", {})
    )
    receiver_hashes = collaboration.get("receiver_id_sha256")
    tool_counts = collaboration.get("tool_counts")
    status_counts = collaboration.get("status_counts")
    collab_passed = (
        collaboration.get("spawn_count") == 2
        and collaboration.get("receiver_count") == 2
        and isinstance(receiver_hashes, list)
        and len(set(receiver_hashes)) == 2
        and all(isinstance(item, str) and SHA256.fullmatch(item) for item in receiver_hashes)
        and isinstance(tool_counts, dict)
        and tool_counts.get("spawn_agent") == 2
        and isinstance(status_counts, dict)
        and status_counts.get("completed", 0) >= 2
    )
    if not collab_passed:
        raise HostAcceptanceError("JSONL collaboration summary does not prove two successful spawns")
    try:
        validated = ds_lite_protocol.validate_delegation(delegation)
    except ds_lite_protocol.ProtocolError as exc:
        raise HostAcceptanceError("delegation protocol validation failed") from exc
    tasks = validated.get("tasks", [])
    if (
        validated.get("status") != "completed"
        or validated.get("integration_owner") != "parent-worker"
        or validated.get("nested_delegation") is not False
        or len(tasks) != 2
        or any(task.get("status") != "completed" for task in tasks)
    ):
        raise HostAcceptanceError("delegation terminal state is invalid")
    result_refs = [task.get("result_ref") for task in tasks]
    if len(set(result_refs)) != 2 or any(not isinstance(ref, str) for ref in result_refs):
        raise HostAcceptanceError("child result refs must be independent")
    for ref in result_refs:
        if not _resolve_ref(acceptance_root, ref).is_file():
            raise HostAcceptanceError("child result artifact is missing")
    integration_path = Path(integration_receipt_path)
    _relative_ref(acceptance_root, integration_path)
    integration = _read_json(integration_path)
    if (
        set(integration) != INTEGRATION_FIELDS
        or integration.get("schema_version") != INTEGRATION_SCHEMA
        or integration.get("integration_owner") != "parent-worker"
        or integration.get("result_refs") != result_refs
    ):
        raise HostAcceptanceError("parent integration receipt is invalid")
    integration_ref = integration.get("integration_ref")
    if not isinstance(integration_ref, str) or not _resolve_ref(acceptance_root, integration_ref).is_file():
        raise HostAcceptanceError("parent integration artifact is missing")
    return {
        "status": "passed",
        "spawn_agent_count": 2,
        "receiver_count": 2,
        "independent_result_ref_count": 2,
        "parent_integration_count": 1,
        "nested_delegation_protocol": False,
        "protocol_paths_mutually_exclusive": True,
        "os_path_isolation_claimed": False,
        "integration_evidence_ref": _relative_ref(acceptance_root, integration_path),
    }
