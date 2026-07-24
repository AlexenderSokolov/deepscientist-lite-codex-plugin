#!/usr/bin/env python3
"""Lightweight, host-invoked hooks for DeepScientist Lite workspaces."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import ds_lite_protocol
import ds_lite_state


EVENT_NAMES = {
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}
STATE_MUTATIONS = {
    "add-node",
    "update-node",
    "add-edge",
    "link-path",
    "link-artifact",
    "set-active",
    "set-status",
}
HOST_EVENT_SCHEMA = "ds-lite.hook-host-event.v1"


def _workspace_root(payload: dict[str, Any]) -> Path | None:
    for key in ("cwd", "workspace_root", "project_root"):
        raw = payload.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            candidate = candidate.parent
        for current in (candidate, *candidate.parents):
            if (
                (current / "PROJECT.md").is_file()
                and (current / "research" / "state" / "graph.json").is_file()
                and (current / "research" / "work-unit.json").is_file()
            ):
                return current
    return None


def _base(event_name: str, root: Path | None) -> dict[str, Any]:
    return {
        "ok": True,
        "hook_event": EVENT_NAMES[event_name],
        "decision": "allow",
        "workspace_detected": root is not None,
    }


def _mission(root: Path) -> dict[str, Any]:
    return ds_lite_state.build_mission(root, ds_lite_state.load_graph(root))


def _suggested_skill(mission: dict[str, Any]) -> str:
    if mission.get("waiting_for_user"):
        return "ds-lite-iterate"
    return {
        "intake": "ds-lite-scout",
        "scout": "ds-lite-idea",
        "idea": "ds-lite-experiment",
        "experiment": "ds-lite-review",
        "review": "ds-lite-analysis-write",
        "analysis": "ds-lite-analysis-write",
        "write": "ds-lite-analysis-write",
    }.get(str(mission.get("stage", "")), "ds-lite-iterate")


def _mission_context(root: Path) -> str:
    try:
        mission = _mission(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_state.CliError):
        return (
            "DS Lite Mission Board: state check unavailable. Run the repository state "
            "validator before choosing an action."
        )
    lines = (
        "DS Lite Mission Board (read-only hook projection)",
        f"revision: {mission.get('revision', 'unknown')}",
        f"active_node: {mission.get('active_node_id') or 'none'}",
        f"stage: {mission.get('stage') or 'unknown'}",
        f"evidence_strength: {mission.get('evidence_strength') or 'unknown'}",
        f"claim_readiness: {mission.get('claim_readiness') or 'unknown'}",
        f"waiting_for_user: {str(bool(mission.get('waiting_for_user'))).lower()}",
        f"suggested_skill: ${_suggested_skill(mission)}",
        f"next_action: {mission.get('next_action') or 'inspect the Mission Board'}",
        "Boundary: choose one bounded action, verify it, reflect, report, then stop.",
    )
    return "\n".join(lines)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_strings(item))
        return result
    return []


def _command(payload: dict[str, Any]) -> str:
    direct = payload.get("command")
    if isinstance(direct, str):
        return direct
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("command", "cmd", "script"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    return ""


def _block(result: dict[str, Any], category: str, reason: str) -> dict[str, Any]:
    result.update(
        {
            "decision": "block",
            "failure_category": category,
            "reason": reason,
        }
    )
    return result


def _pre_tool_use(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = _base("pre-tool-use", root)
    tool_name = str(payload.get("tool_name", "")).lower()
    values = _strings(payload.get("tool_input", {}))
    normalized_values = [value.replace("\\", "/").lower() for value in values]
    direct_write_tool = any(token in tool_name for token in ("write", "edit", "apply_patch"))
    if direct_write_tool and any(
        "research/state/graph.json" in value for value in normalized_values
    ):
        return _block(
            result,
            "state/direct-authority-write",
            "Graph v2 is authoritative; mutate it only through ds_lite_state.py with revision checks.",
        )

    command = _command(payload)
    lowered = command.lower()
    if re.search(r"\bgit\b[^\r\n;&|]*\b(?:reset|clean)\b", lowered) or re.search(
        r"\bgit\b[^\r\n;&|]*\bcheckout\b[^\r\n;&|]*--", lowered
    ):
        return _block(
            result,
            "safety/destructive-command",
            "Destructive Git reset, clean, or checkout-overwrite operations are not permitted.",
        )
    if (
        re.search(r"\brm\s+(?:-[a-z]*r[a-z]*|--recursive)\b", lowered)
        or re.search(r"\bremove-item\b[^\r\n;&|]*-recurse\b", lowered)
        or re.search(r"\b(?:del|erase|rd|rmdir)\b[^\r\n;&|]*/s\b", lowered)
    ):
        return _block(
            result,
            "safety/recursive-delete",
            "Recursive deletion is outside the Lite action boundary and requires explicit handling.",
        )
    if re.search(
        r"\btmux\b[^\r\n;&|]*\b(?:new-session|new-window|split-window|resize-pane)\b",
        lowered,
    ):
        return _block(
            result,
            "runtime/tmux-capacity",
            "Codex may inspect authorized tmux capacity but must not create or expand it.",
        )

    if "ds_lite_state.py" in lowered:
        mutation = next(
            (name for name in STATE_MUTATIONS if re.search(rf"\b{re.escape(name)}\b", lowered)),
            "",
        )
        if mutation and "--expected-revision" not in lowered:
            return _block(
                result,
                "state/missing-revision",
                "State mutation requires an explicit --expected-revision guard.",
            )

    graph_named = any("research/state/graph.json" in value for value in normalized_values)
    graph_mutator = any(
        token in lowered
        for token in (">", "set-content", "add-content", "out-file", "copy-item", "move-item")
    )
    if graph_named and graph_mutator and "ds_lite_state.py" not in lowered:
        return _block(
            result,
            "state/direct-authority-write",
            "Graph v2 is authoritative; mutate it only through ds_lite_state.py with revision checks.",
        )
    return result


def _post_tool_context(root: Path) -> str:
    try:
        mission = _mission(root)
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_state.CliError):
        return (
            "DS Lite consistency: state could not be checked. Run ds_lite_state.py validate "
            "before the next mutation."
        )
    validation = mission.get("validation") or {}
    error_count = len(validation.get("errors") or [])
    warning_count = len(validation.get("warnings") or [])
    off_route_count = len(validation.get("off_route_warnings") or [])
    status = "pass" if error_count == 0 and warning_count == 0 else "attention"
    return (
        f"DS Lite consistency: {status}; errors={error_count}; active-route warnings="
        f"{warning_count}; off-route warnings={off_route_count}; revision={mission.get('revision', 'unknown')}."
    )


def _stop_gaps(root: Path) -> list[str]:
    work_unit_path = root / "research" / "work-unit.json"
    try:
        work_unit = json.loads(work_unit_path.read_text(encoding="utf-8"))
        ds_lite_protocol.validate_work_unit(work_unit)
        ref = work_unit.get("active_iteration_ref", "")
        if not ref:
            return []
        ds_lite_protocol.validate_ref(ref, "active_iteration_ref")
        if ref.startswith("external://"):
            return ["active iteration is not available as a project-relative receipt"]
        project_root = root.resolve()
        iteration_path = (root / ref).resolve()
        iteration_path.relative_to(project_root)
        iteration = json.loads(iteration_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ds_lite_protocol.ProtocolError):
        return ["active iteration receipt cannot be safely verified"]

    gaps: list[str] = []
    if iteration.get("status") == "running":
        gaps.append("running iteration must be finalized")
    reflection = iteration.get("reflection")
    if not isinstance(reflection, dict) or not any(
        reflection.get(field)
        for field in (
            "observed_outcomes",
            "hypothesis_updates",
            "expectation_gap",
            "negative_results",
            "learned_boundaries",
            "next_candidates",
            "minimal_discriminating_test",
        )
    ):
        gaps.append("iteration reflection is missing")
    user_report = iteration.get("user_report")
    if not isinstance(user_report, dict) or not str(user_report.get("summary", "")).strip():
        gaps.append("user report is missing")
    return gaps

def handle_event(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unsupported hook event: {event_name}")
    root = _workspace_root(payload)
    result = _base(event_name, root)
    if root is None:
        if event_name == "stop":
            result["continue_once"] = False
        return result
    if event_name == "user-prompt-submit":
        result["additional_context"] = _mission_context(root)
        return result
    if event_name == "pre-tool-use":
        return _pre_tool_use(root, payload)
    if event_name == "post-tool-use":
        result["additional_context"] = _post_tool_context(root)
        return result

    result["continue_once"] = False
    gaps = _stop_gaps(root)
    if not gaps:
        return result
    result["additional_context"] = (
        "DS Lite stop check: " + "; ".join(gaps) + ". Finalize once, report to the user, then stop."
    )
    if payload.get("stop_hook_active") is True:
        return result
    result["decision"] = "block"
    result["continue_once"] = True
    result["failure_category"] = "iteration/incomplete-handoff"
    return result


def _write_host_acceptance_event(event_name: str, decision: str) -> None:
    raw_directory = os.environ.get("DS_LITE_HOOK_ACCEPTANCE_DIR", "").strip()
    if not raw_directory:
        return
    directory = Path(raw_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": HOST_EVENT_SCHEMA,
        "event_type": event_name,
        "decision": decision,
    }
    path = directory / f"{uuid.uuid4().hex}-{event_name}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one DeepScientist Lite hook event.")
    parser.add_argument(
        "event",
        choices=("user-prompt-submit", "pre-tool-use", "post-tool-use", "stop"),
    )
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        result = handle_event(args.event, payload)
        _write_host_acceptance_event(args.event, str(result.get("decision", "unknown")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
