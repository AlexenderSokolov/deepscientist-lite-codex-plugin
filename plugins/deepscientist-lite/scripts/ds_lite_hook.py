#!/usr/bin/env python3
"""Optional, deterministic host hook adapter for DeepScientist Lite.

The adapter reports observable project state. It does not infer intent, prove a
scientific result, or silently register itself with an unknown host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import ds_lite_communication_audit as communication_audit
import ds_lite_protocol
import ds_lite_state


EVENT_NAMES = {
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}
STATE_MUTATIONS = {"add-node", "update-node", "add-edge", "link-path", "link-artifact", "set-active", "set-status"}
PROFILE_NAMES = {"research-peer", "teaching-explainer", "compact-operator", "reflective-researcher", "custom"}
ELEVATION_RE = re.compile(
    r"(?i)(?:^|[\s;&|])(?:sudo|su|doas|pkexec|runas)\b"
    r"|\bstart-process\b[^\r\n;&|]*\b-verb\s+runas\b"
)


def _workspace_root(payload: dict[str, Any]) -> Path | None:
    for key in ("cwd", "workspace_root", "project_root"):
        raw = payload.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            candidate = candidate.parent
        for current in (candidate, *candidate.parents):
            if ((current / "PROJECT.md").is_file()
                    and (current / "research" / "state" / "graph.json").is_file()
                    and (current / "research" / "work-unit.json").is_file()):
                return current.resolve()
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
        "intake": "ds-lite-scout", "scout": "ds-lite-idea", "idea": "ds-lite-experiment",
        "experiment": "ds-lite-review", "review": "ds-lite-analysis-write",
        "analysis": "ds-lite-analysis-write", "write": "ds-lite-analysis-write",
    }.get(str(mission.get("stage", "")), "ds-lite-iterate")


def _style(root: Path, payload: dict[str, Any]) -> tuple[str, str, str]:
    profile = str(payload.get("profile", "")).strip() or "research-peer"
    detail = str(payload.get("detail_mode", "")).strip() or "adaptive"
    language = str(payload.get("language", "")).strip() or "auto"
    style_path = root / "STYLE.md"
    if style_path.is_file():
        try:
            text = style_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""
        for key, fallback in (("profile", profile), ("detail", detail), ("language", language)):
            match = re.search(rf"^\s*{re.escape(key)}:\s*([^#\r\n]+)", text, re.MULTILINE)
            value = match.group(1).strip() if match else fallback
            if key == "profile":
                profile = value if value in PROFILE_NAMES else "research-peer"
            elif key == "detail":
                detail = value if value in {"adaptive", "concise", "deep"} else "adaptive"
            else:
                language = value if value in {"auto", "zh", "en"} else "auto"
    return profile, detail, language


def _audit_candidates(root: Path) -> list[Path]:
    directory = root / communication_audit.AUDIT_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("communication-audit-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)


def _audit(root: Path) -> tuple[Path | None, dict[str, Any] | None, list[str]]:
    candidates = _audit_candidates(root)
    if not candidates:
        return None, None, ["communication audit is missing; initialize communication-audit-<id>.json"]
    path = candidates[0]
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        _, payload = communication_audit.load(root, relative)
        errors = communication_audit.validate_payload(root, payload)
        return path, payload, errors
    except (OSError, UnicodeError, communication_audit.AuditError, json.JSONDecodeError) as exc:
        return path, None, [f"communication audit cannot be read: {exc}"]


def _audit_gate(root: Path) -> tuple[bool, str, str]:
    path, payload, errors = _audit(root)
    if path is None:
        return False, "audit/missing", "; ".join(errors)
    if errors:
        return False, "audit/invalid", "; ".join(errors)
    if payload is not None and payload.get("result", {}).get("status") != "in-progress":
        return False, "audit/closed", "the latest communication audit is finalized; initialize a new audit before another state write"
    return True, "", communication_audit.relative_display(root, path)


def _mission_context(root: Path, payload: dict[str, Any]) -> str:
    profile, detail, language = _style(root, payload)
    try:
        mission = _mission(root)
        mission_lines = (
            f"revision: {mission.get('revision', 'unknown')}",
            f"active_node: {mission.get('active_node_id') or 'none'}",
            f"stage: {mission.get('stage') or 'unknown'}",
            f"claim_readiness: {mission.get('claim_readiness') or 'unknown'}",
            f"next_action: {mission.get('next_action') or 'inspect the Mission Board'}",
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_state.CliError):
        mission_lines = ("state: unavailable; run the repository state validator",)
    _, audit_payload, errors = _audit(root)
    audit_ready = audit_payload is not None and not errors and audit_payload.get("result", {}).get("status") == "in-progress"
    audit_line = "audit: ready" if audit_ready else "audit_required: initialize and record communication-audit.v1 before state writes"
    return "\n".join((
        "DS Lite communication gate (observable receipt; not proof of scientific truth)",
        f"profile: {profile}", f"detail: {detail}", f"language: {language}", audit_line,
        "self-audit phases: before action -> after action -> before handoff",
        "checks: honor-01 honor-02 honor-03 honor-04 honor-05 honor-06 honor-07 honor-08",
        *mission_lines,
        "protected: commands, paths, JSON/YAML, logs, metrics, formulas, citations, definitions",
    ))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_strings(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
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


def _exit_code(payload: dict[str, Any]) -> int | None:
    value = payload.get("exit_code")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    for key in ("tool_result", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("exit_code"), int):
            return nested["exit_code"]
    success = payload.get("success")
    if isinstance(success, bool):
        return 0 if success else 1
    return None


def _block(result: dict[str, Any], category: str, reason: str) -> dict[str, Any]:
    result.update({"decision": "block", "failure_category": category, "reason": reason})
    return result


def _pre_tool_use(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = _base("pre-tool-use", root)
    tool_name = str(payload.get("tool_name", "")).lower()
    values = _strings(payload.get("tool_input", {}))
    normalized_values = [value.replace("\\", "/").lower() for value in values]
    direct_write_tool = any(token in tool_name for token in ("write", "edit", "apply_patch"))
    command = _command(payload)
    lowered = command.lower()
    graph_named = any("research/state/graph.json" in value for value in normalized_values)
    if direct_write_tool and graph_named:
        return _block(result, "state/direct-authority-write", "Graph v2 is authoritative; mutate it only through ds_lite_state.py with revision checks.")
    if re.search(r"\bgit\b[^\r\n;&|]*\b(?:reset|clean)\b", lowered) or re.search(r"\bgit\b[^\r\n;&|]*\bcheckout\b[^\r\n;&|]*--", lowered):
        return _block(result, "safety/destructive-command", "Destructive Git reset, clean, or checkout-overwrite operations are not permitted.")
    if ELEVATION_RE.search(command):
        return _block(result, "safety/privilege-escalation", "Explicit privilege escalation requires user-controlled approval outside the Lite hook boundary.")
    if re.search(r"\brm\s+(?:-[a-z]*r[a-z]*|--recursive)\b", lowered) or re.search(r"\bremove-item\b[^\r\n;&|]*-recurse\b", lowered) or re.search(r"\b(?:del|erase|rd|rmdir)\b[^\r\n;&|]*/s\b", lowered):
        return _block(result, "safety/recursive-delete", "Recursive deletion is outside the Lite action boundary and requires explicit handling.")
    if re.search(r"\btmux\b[^\r\n;&|]*\b(?:new-session|new-window|split-window|resize-pane)\b", lowered):
        return _block(result, "runtime/tmux-capacity", "Codex may inspect authorized tmux capacity but must not create or expand it.")

    state_mutation = direct_write_tool or graph_named or any(name in lowered for name in STATE_MUTATIONS)
    if state_mutation:
        allowed, category, reason = _audit_gate(root)
        if not allowed:
            return _block(result, category, reason)
    if "ds_lite_state.py" in lowered:
        mutation = next((name for name in STATE_MUTATIONS if re.search(rf"\b{re.escape(name)}\b", lowered)), "")
        if mutation and "--expected-revision" not in lowered:
            return _block(result, "state/missing-revision", "State mutation requires an explicit --expected-revision guard.")
    graph_mutator = any(token in lowered for token in (">", "set-content", "add-content", "out-file", "copy-item", "move-item"))
    if graph_named and graph_mutator and "ds_lite_state.py" not in lowered:
        return _block(result, "state/direct-authority-write", "Graph v2 is authoritative; mutate it only through ds_lite_state.py with revision checks.")
    return result


def _record_post_tool(root: Path, payload: dict[str, Any]) -> None:
    path, audit, errors = _audit(root)
    command = _command(payload)
    exit_code = _exit_code(payload)
    if path is None or audit is None or errors or audit.get("result", {}).get("status") != "in-progress" or not command or exit_code is None:
        return
    event = {
        "event": "PostToolUse",
        "tool_name": str(payload.get("tool_name", "")),
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "exit_code": exit_code,
        "result": "pass" if exit_code == 0 else "fail",
        "observed": True,
    }
    extensions = audit.setdefault("extensions", {})
    events = extensions.setdefault("post_tool_events", [])
    if isinstance(events, list):
        events.append(event)
    phase = audit.get("self_check", {}).get("after")
    if isinstance(phase, dict):
        phase["status"] = "recorded"
        phase.setdefault("items", []).append(f"PostToolUse exit_code={exit_code}")
    communication_audit.atomic_write(path, audit)


def _post_tool_context(root: Path) -> str:
    _, audit, errors = _audit(root)
    if audit is None:
        return "DS Lite communication audit: missing; no completion claim is supported."
    if errors:
        return "DS Lite communication audit: invalid; " + "; ".join(errors)
    try:
        mission = _mission(root)
        validation = mission.get("validation") or {}
        return (f"DS Lite consistency: errors={len(validation.get('errors') or [])}; "
                f"warnings={len(validation.get('warnings') or [])}; "
                f"audit_result={audit.get('result', {}).get('status', 'unknown')}; "
                f"post_tool_events={len(audit.get('extensions', {}).get('post_tool_events', []))}.")
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_state.CliError):
        return "DS Lite consistency: state unavailable; validation remains unverified."


def _iteration_gaps(root: Path) -> list[str]:
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
        iteration_path = (root / ref).resolve()
        iteration_path.relative_to(root.resolve())
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
            "observed_outcomes", "hypothesis_updates", "expectation_gap", "negative_results",
            "learned_boundaries", "next_candidates", "minimal_discriminating_test",
        )
    ):
        gaps.append("iteration reflection is missing")
    user_report = iteration.get("user_report")
    if not isinstance(user_report, dict) or not str(user_report.get("summary", "")).strip():
        gaps.append("user report is missing")
    return gaps


def _stop_gaps(root: Path) -> list[str]:
    _, audit, errors = _audit(root)
    if audit is None:
        return errors
    if errors:
        return ["audit validation failed: " + "; ".join(errors)]
    gaps: list[str] = []
    if audit.get("result", {}).get("status") == "in-progress":
        gaps.append("communication audit is not finalized")
    for item in audit.get("checks", []):
        if item.get("status") == "pending":
            gaps.append(f"{item.get('id')} is pending")
    for claim in audit.get("claims", []):
        if claim.get("kind") in {"verified", "fixed", "completed"} and claim.get("status") != "supported":
            gaps.append(f"claim/{claim.get('id')} is {claim.get('status')}")
    if audit.get("result", {}).get("status") == "completed" and not any(
        claim.get("kind") == "completed" and claim.get("status") == "supported"
        for claim in audit.get("claims", [])
    ):
        gaps.append("claim/unsupported-completion: supported completed claim is missing")
    handoff = audit.get("handoff", {})
    if handoff.get("status") != "recorded" or not handoff.get("summary") or not handoff.get("next_step"):
        gaps.append("handoff is missing or incomplete")
    for phase in ("before", "after", "before_handoff"):
        if audit.get("self_check", {}).get(phase, {}).get("status") != "recorded":
            gaps.append(f"self_check.{phase} is missing")
    gaps.extend(_iteration_gaps(root))
    return gaps


def handle_event(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unsupported hook event: {event_name}")
    root = _workspace_root(payload)
    result = _base(event_name, root)
    if root is None:
        result["continue_once"] = False
        return result
    if event_name == "user-prompt-submit":
        profile, detail, _ = _style(root, payload)
        _, audit, errors = _audit(root)
        result["profile"] = profile
        result["detail_mode"] = detail
        result["audit_required"] = audit is None or bool(errors) or audit.get("result", {}).get("status") != "in-progress"
        result["additional_context"] = _mission_context(root, payload)
        return result
    if event_name == "pre-tool-use":
        return _pre_tool_use(root, payload)
    if event_name == "post-tool-use":
        _record_post_tool(root, payload)
        result["additional_context"] = _post_tool_context(root)
        return result

    gaps = _stop_gaps(root)
    if not gaps:
        result["continue_once"] = False
        result["blocked"] = False
        return result
    result["additional_context"] = "DS Lite stop check: " + "; ".join(gaps) + ". Repair or report the blocker; do not claim success."
    result["decision"] = "block"
    result["failure_category"] = "claim/unsupported-completion" if any("claim/" in gap for gap in gaps) else "audit/incomplete"
    if payload.get("stop_hook_active") is True:
        result["continue_once"] = False
        result["blocked"] = True
        return result
    result["continue_once"] = True
    result["blocked"] = False
    return result


def install(root: Path, show: bool, apply: bool) -> tuple[int, dict[str, Any]]:
    config = root / ".codex" / "config.toml"
    hooks_path = Path(__file__).resolve().parents[1] / "hooks" / "hooks.json"
    proposed: Any = None
    if hooks_path.is_file():
        proposed = json.loads(hooks_path.read_text(encoding="utf-8"))
    payload: dict[str, Any] = {
        "ok": not apply,
        "host_supported": False,
        "applied": False,
        "config_path": communication_audit.relative_display(root, config),
        "existing_config": config.is_file(),
        "proposed_hooks": proposed,
        "reason": "host hook configuration format is not confirmed by official documentation or a real host acceptance run; no config was written",
    }
    return (1 if apply else 0), payload


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (AttributeError, OSError):
                pass
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "install":
        parser = argparse.ArgumentParser(description="Show or attempt optional DS Lite host hook registration.")
        parser.add_argument("install", nargs="?")
        parser.add_argument("--root", required=True)
        parser.add_argument("--show", action="store_true")
        parser.add_argument("--apply", action="store_true")
        args = parser.parse_args(argv)
        code, payload = install(Path(args.root).expanduser().resolve(), args.show, args.apply)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return code
    parser = argparse.ArgumentParser(description="Run one DeepScientist Lite hook event.")
    parser.add_argument("event", choices=tuple(EVENT_NAMES))
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        result = handle_event(args.event, payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
