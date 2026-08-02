#!/usr/bin/env python3
"""Lightweight, host-invoked hooks for DeepScientist Lite workspaces."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import ds_lite_protocol
import ds_lite_state
import ds_lite_learning
import ds_lite_quality
import ds_lite_user_action
import ds_lite_communication_audit


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
LEARNING_HELPER = "ds_lite_learning.py"
USER_ACTION_HELPER = "ds_lite_user_action.py"
QUALITY_PLAN_REFS = ("research/quality/plan.json", "research/quality-plan.json")
QUALITY_RESULT_REFS = ("research/quality/result.json", "research/quality-result.json")
AUTONOMY_CONTRACT_REF = "research/autonomy/contract.json"
AUTONOMY_RUN_REF = "research/autonomy/run"
AUTONOMY_RESUME_COMMAND = (
    "powershell -ExecutionPolicy Bypass -File .\\run_autonomy.ps1 -Resume"
    if os.name == "nt"
    else "bash run_autonomy.sh --resume"
)
AUTONOMY_RESUME_TIMEOUT_SECONDS = 120
AUTORESEARCH_JOB_REF = "research/autoresearch/job.json"
AUTORESEARCH_RUNNER_TIMEOUT_SECONDS = 900
AUTORESEARCH_RUNNER_MODE = "watch"


def _project_temp_env(root: Path) -> dict[str, str]:
    """Keep controller child-process scratch data on the project volume."""
    temp_root = (root / "research" / ".validation-tmp").resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(temp_root)
    env["TMP"] = str(temp_root)
    env["TEMP_ROOT"] = str(temp_root)
    env["PYTHONPYCACHEPREFIX"] = str(temp_root / "pycache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


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
        # Stable controller-facing vocabulary. ``decision`` remains the
        # host-compatible allow/block field; this records what the external
        # session runner must do next.
        "control_action": "allow",
        "failure_layer": "none",
        "recovery_ref": "",
        "workspace_detected": root is not None,
    }


def _is_resume_request(payload: dict[str, Any]) -> bool:
    """Recognize an explicit checkpoint request without storing its prompt."""
    text = str(payload.get("prompt", payload.get("text", ""))).casefold()
    return any(token in text for token in ("resume", "checkpoint", "continue", "断点", "重跑", "继续"))


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


def _active_skill(payload: dict[str, Any]) -> str:
    for key in ("skill", "active_skill", "selected_skill", "skill_name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("skill", "active_skill", "selected_skill", "skill_name"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _learning_context(root: Path, skill: str) -> tuple[bool, str]:
    if not skill:
        return True, "learning: not-observed (host did not identify an active skill)"
    try:
        receipt = ds_lite_learning.ensure(root, skill)
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_learning.LearningError) as exc:
        return False, f"learning: blocked for ${skill}; create a current receipt before side effects ({exc})"
    return True, f"learning: current; summary={receipt.get('summary_ref', 'unavailable')}"


def _learning_helper(command: str) -> bool:
    lowered = command.lower()
    return LEARNING_HELPER.lower() in lowered and any(
        token in lowered for token in ("learn", "ensure", "catalog")
    )


def _user_action_helper(command: str) -> bool:
    lowered = command.lower()
    return USER_ACTION_HELPER.lower() in lowered and any(
        token in lowered for token in ("request", "respond")
    )


def _requires_user_action(tool_name: str, command: str) -> tuple[str, str] | None:
    text = f"{tool_name} {command}".lower()
    patterns = (
        (r"\bcodex\b.*\bapp-server\b|\bthread/(?:start|resume)\b|\bturn/(?:start|steer)\b", "provider-session", "在已批准 provider 上运行一次隔离 app-server fresh thread 验收"),
        (r"firecrawl|playwright|agent-browser|browser|invoke-webrequest|curl\b|requests\b", "web-provider", "执行一次公开资料浏览器或网络 provider 验收"),
        (r"tmux\b.*(?:new-session|new-window|split-window|resize-pane)|long-task|external-task", "long-task", "在独立稳定 shell 中执行已生成的固定 socket bootstrap"),
        (r"delegate|child[-_ ]task|spawn[-_ ]agent|nested_delegation", "delegation", "在受信任宿主中启动一次有界子任务验收"),
        (r"openscience|fresh[-_ ]desktop|plugin\s+(?:add|install|marketplace)|formal[-_ ]release|release", "host-or-release", "在指定宿主或发布环境中执行一次新身份验收"),
    )
    for pattern, scope, action in patterns:
        if re.search(pattern, text):
            return scope, action
    return None


def _user_action_gate(root: Path, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    command = _command(payload)
    if _user_action_helper(command):
        result["user_action"] = "helper-whitelisted"
        return result
    requirement = _requires_user_action(str(payload.get("tool_name", "")), command)
    if requirement is None:
        return result
    scope, action = requirement
    available: tuple[dict[str, Any], dict[str, Any]] | None = None
    pending: tuple[dict[str, Any], Path] | None = None
    directory = root / "research" / "artifacts"
    if directory.is_dir():
        for request_path in sorted(directory.glob("user-action-request-*.json")):
            request_id = request_path.stem.removeprefix("user-action-request-")
            try:
                request = ds_lite_user_action.validate_request(json.loads(request_path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_user_action.UserActionError):
                continue
            if request.get("extensions", {}).get("scope") != scope:
                continue
            response_path = ds_lite_user_action.response_path(root, request_id)
            if response_path.is_file():
                try:
                    response = ds_lite_user_action.validate_response(json.loads(response_path.read_text(encoding="utf-8")))
                except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_user_action.UserActionError):
                    continue
                if response.get("status") == "available":
                    available = (request, response)
                    break
            elif pending is None:
                pending = (request, request_path)
    if available is not None:
        request, response = available
        try:
            consumed = ds_lite_user_action.consume(root, request, response)
        except ds_lite_user_action.UserActionError as exc:
            return _block(result, "user-action/invalid-response", str(exc))
        result["user_action"] = {"status": "consumed", "scope": scope, "receipt_ref": consumed["receipt_ref"]}
        return result
    if pending is None:
        try:
            request = ds_lite_user_action.create_request(
                root,
                reason=f"宿主能力 {scope} 不在 Core 自主权限内，必须先获得用户一次性确认。",
                action=action,
                scope=scope,
                expected_receipt=f"research/artifacts/{scope}-acceptance.json",
            )
            request_id = request["request_id"]
            request_ref = f"research/artifacts/user-action-request-{request_id}.json"
        except (OSError, UnicodeError, ds_lite_user_action.UserActionError) as exc:
            return _block(result, "user-action/request-write", f"无法创建用户动作请求：{exc}")
    else:
        request, request_path = pending
        request_ref = request_path.relative_to(root).as_posix()
    return _block(
        result,
        "user-action/required",
        f"当前任务被阻断于【{scope}】。请执行【{request.get('exact_action', action)}】并回传【{request_ref} 对应的 response receipt】。在收到并验证该结果前，不会启动该副作用。",
    )


def _is_read_only(payload: dict[str, Any], command: str) -> bool:
    if not command.strip():
        return False
    lowered = command.lower().strip()
    return bool(
        re.match(r"^(get-content|type|cat|head|tail|rg|grep|findstr|dir|ls|pwd|git\s+(status|diff|show|log))\b", lowered)
    )


def _quality_plan(root: Path) -> Path | None:
    for ref in QUALITY_PLAN_REFS:
        path = root / Path(*ref.split("/"))
        if path.is_file():
            return path
    return None


def _quality_result(root: Path) -> Path | None:
    for ref in QUALITY_RESULT_REFS:
        path = root / Path(*ref.split("/"))
        if path.is_file():
            return path
    return None


def _audit(root: Path) -> tuple[Path, dict[str, Any]] | None:
    directory = root / "research" / "artifacts"
    if not directory.is_dir():
        return None
    paths = sorted(directory.glob("communication-audit-*.json"))
    if not paths:
        return None
    path = paths[-1]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors = ds_lite_communication_audit.validate_payload(root, payload)
        if errors:
            return path, {"__errors__": errors}
        return path, payload
    except (OSError, UnicodeError, json.JSONDecodeError):
        return path, {"__errors__": ["communication audit cannot be read"]}


def _audit_preflight(root: Path) -> tuple[bool, str, str]:
    loaded = _audit(root)
    if loaded is None:
        return False, "audit/missing", "Initialize a communication audit before side effects."
    _, payload = loaded
    if payload.get("__errors__"):
        return False, "audit/invalid", "; ".join(payload["__errors__"])
    if payload.get("result", {}).get("status") != "in-progress":
        return False, "audit/closed", "Communication audit is finalized; initialize a new audit before new writes."
    return True, "", "audit: current"


def _audit_post_event(root: Path, payload: dict[str, Any]) -> None:
    loaded = _audit(root)
    if loaded is None:
        return
    path, audit = loaded
    if audit.get("__errors__") or audit.get("result", {}).get("status") != "in-progress":
        return
    events = audit.setdefault("extensions", {}).setdefault("post_tool_events", [])
    events.append({
        "tool_name": str(payload.get("tool_name", "unknown"))[:80],
        "exit_code": payload.get("exit_code"),
        "observed": True,
    })
    ds_lite_communication_audit.atomic_write(path, audit)


def _audit_stop_gaps(root: Path) -> list[str]:
    loaded = _audit(root)
    if loaded is None:
        return []
    _, audit = loaded
    if audit.get("__errors__"):
        return ["communication audit is invalid"]
    result = audit.get("result", {}).get("status")
    if result == "completed":
        claims = audit.get("claims", [])
        supported_completed = any(
            claim.get("kind") == "completed" and claim.get("status") == "supported"
            for claim in claims
        )
        unsupported = [claim for claim in claims if claim.get("status") != "supported"]
        if unsupported or not supported_completed:
            return ["claim/unsupported-completion: finalized audit contains unsupported claims"]
    if result in {"failed", "blocked"}:
        return [f"communication audit is {result}; do not report completion"]
    return []


def _quality_preflight(root: Path) -> tuple[bool, str]:
    plan = _quality_plan(root)
    if plan is None:
        return True, "quality: no project quality plan declared"
    try:
        ds_lite_quality.validate_plan(json.loads(plan.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_quality.QualityError) as exc:
        return False, f"quality: blocked; invalid plan ({exc})"
    return True, "quality: plan current"


def _block(result: dict[str, Any], category: str, reason: str) -> dict[str, Any]:
    if category.startswith("user-action/"):
        control_action = "block-awaiting-user-action"
    elif category.startswith(("safety/", "runtime/", "state/", "audit/", "learning/", "quality/")):
        control_action = "blocked"
    else:
        control_action = "block-and-resume"
    result.update(
        {
            "decision": "block",
            "control_action": control_action,
            "failure_category": category,
            "failure_layer": category,
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
    if re.search(r"\bsudo\b|\brunas\b|start-process[^\r\n]*-verb\s+runas", lowered):
        return _block(result, "safety/privilege-escalation", "Privilege escalation requires an explicit, separately reviewed user action.")
    if re.search(r"\bgit\b[^\r\n;&|]*\b(?:reset|clean)\b", lowered) or re.search(
        r"\bgit\b[^\r\n;&|]*\bcheckout\b[^\r\n;&|]*--", lowered
    ):
        return _block(result, "safety/destructive-command", "Destructive Git reset, clean, or checkout-overwrite operations are not permitted.")
    if re.search(r"\brm\s+(?:-[a-z]*r[a-z]*|--recursive)\b|\bremove-item\b[^\r\n;&|]*-recurse\b|\b(?:del|erase|rd|rmdir)\b[^\r\n;&|]*/s\b", lowered):
        return _block(result, "safety/recursive-delete", "Recursive deletion is outside the Lite action boundary and requires explicit handling.")
    gated = _user_action_gate(root, payload, result)
    if gated.get("decision") == "block" or gated.get("user_action"):
        return gated
    skill = _active_skill(payload)
    side_effect = bool(
        any(token in tool_name for token in ("write", "edit", "apply_patch"))
        or (command.strip() and not _is_read_only(payload, command))
    )
    if side_effect and not _learning_helper(command):
        audit_ok, audit_category, audit_message = _audit_preflight(root)
        result["audit"] = audit_message
        if not audit_ok:
            return _block(result, audit_category, audit_message)
        learned, learning_message = _learning_context(root, skill)
        result["learning"] = learning_message
        if not learned:
            return _block(result, "learning/missing", learning_message)
        quality_ok, quality_message = _quality_preflight(root)
        result["quality"] = quality_message
        if not quality_ok:
            return _block(result, "quality/plan", quality_message)
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


def _stop_quality_gaps(root: Path) -> list[str]:
    plan = _quality_plan(root)
    if plan is None:
        return []
    result = _quality_result(root)
    if result is None:
        return ["quality result is missing"]
    try:
        plan_payload = json.loads(plan.read_text(encoding="utf-8"))
        result_payload = json.loads(result.read_text(encoding="utf-8"))
        ds_lite_quality.validate_plan(plan_payload)
        if result_payload.get("plan_id") != plan_payload.get("plan_id") or result_payload.get("risk") != plan_payload.get("risk"):
            return ["quality result does not match the active quality plan"]
        ds_lite_quality.evaluate_result(result_payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_quality.QualityError) as exc:
        return [f"quality result is not passing: {exc}"]
    return []


def _user_action_gaps(root: Path) -> list[str]:
    pending = ds_lite_user_action.load_pending(root)
    if pending is None:
        return []
    request, path = pending
    return [f"user action request {request['request_id']} is unresolved ({path.relative_to(root).as_posix()})"]


def _autonomy_context(root: Path) -> str:
    contract = root / AUTONOMY_CONTRACT_REF
    if not contract.is_file():
        return ""
    run_dir = root / AUTONOMY_RUN_REF
    progress = sorted(run_dir.glob("progress-*.json")) if run_dir.is_dir() else []
    if not progress:
        return (
            "Autonomy controller: contract active; progress receipt is missing. "
            f"Do not conclude this task. Automatically continue with: {AUTONOMY_RESUME_COMMAND}."
        )
    try:
        payload = json.loads(progress[-1].read_text(encoding="utf-8"))
        gate = str(payload.get("active_gate", "unknown"))
        status = str(payload.get("status", "unknown"))
        next_action = str(payload.get("next_action", "unknown"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "Autonomy controller: progress receipt is unreadable; inspect the controller output."
    summaries = []
    if (run_dir / "summary.json").is_file():
        summaries.append(run_dir / "summary.json")
    summaries.extend(sorted(run_dir.glob("summary-resume-*.json")))
    if not summaries:
        return (
            f"Autonomy controller: gate={gate}; status={status}; next_action={next_action}. "
            f"Do not conclude this task. Automatically continue with: {AUTONOMY_RESUME_COMMAND}."
        )
    return f"Autonomy controller: gate={gate}; status={status}; next_action={next_action}."


def _autonomy_stop_gaps(root: Path) -> list[str]:
    contract = root / AUTONOMY_CONTRACT_REF
    if not contract.is_file():
        return []
    run_dir = root / AUTONOMY_RUN_REF
    summaries = []
    if (run_dir / "summary.json").is_file():
        summaries.append(run_dir / "summary.json")
    summaries.extend(sorted(run_dir.glob("summary-resume-*.json")))
    if not summaries:
        return ["autonomy controller summary is missing"]
    summary = summaries[-1]
    progress = sorted(run_dir.glob("progress-*.json"))
    if not progress:
        return ["autonomy progress receipt is missing"]
    try:
        payload = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["autonomy controller summary is unreadable"]
    if payload.get("schema_version") != "ds-lite.autonomy-summary.v1":
        return ["autonomy controller summary schema is invalid"]
    if payload.get("status") != "completed":
        return [f"autonomy controller is not terminal: {payload.get('status', 'unknown')}"]
    return []


def _autonomy_is_active(root: Path) -> bool:
    """Return whether the active contract still requires controller ownership."""
    return bool(_autonomy_stop_gaps(root))


def _stop_first_protocol(root: Path) -> bool:
    """Return whether this workspace delegates controller execution to its runner."""
    marker = root / "research" / "autonomy" / "stop-first.json"
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return value == {
        "schema_version": "ds-lite.stop-first-protocol.v1",
        "status": "prepared",
    }


def _autonomy_resume_context(root: Path) -> str:
    if not _autonomy_is_active(root):
        return ""
    return (
        "Autonomy continuity gate: this conversation remains controller-owned. "
        "Do not provide a phase-complete or final answer. "
        f"Run the next automatic action now: {AUTONOMY_RESUME_COMMAND}."
    )


def _resume_autonomy_controller(root: Path) -> tuple[bool, str]:
    """Run one approved controller resume in the foreground without retaining output."""
    contract = root / AUTONOMY_CONTRACT_REF
    output = root / AUTONOMY_RUN_REF
    bundled_cli = Path(__file__).resolve().with_name("ds_lite_autonomy.py")
    configured_cli = os.environ.get("DS_LITE_AUTONOMY_CLI", "").strip()
    candidate_cli = Path(configured_cli).expanduser() if configured_cli else bundled_cli
    # A relative ambient override changes meaning once the Hook switches to the
    # project workspace. Only an existing absolute override may replace Core.
    cli = candidate_cli.resolve() if candidate_cli.is_absolute() and candidate_cli.is_file() else bundled_cli
    if not contract.is_file() or not cli.is_file():
        return False, "autonomy/controller-unavailable"
    command = [
        sys.executable, str(cli), "--root", str(root), "--contract", str(contract),
        "--output", str(output), "--resume",
    ]
    try:
        completed = subprocess.run(
            command, cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", timeout=AUTONOMY_RESUME_TIMEOUT_SECONDS,
            check=False,
            env=_project_temp_env(root),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "autonomy/controller-execution"
    if completed.returncode != 0:
        return False, "autonomy/controller-terminal"
    if _autonomy_is_active(root):
        return False, "autonomy/controller-incomplete"
    return True, "autonomy/controller-completed"


def _autoresearch_job(root: Path) -> tuple[dict[str, Any], Path] | None:
    path = root / AUTORESEARCH_JOB_REF
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != "ds-lite.autoresearch-job.v1":
        return None
    return payload, path


def _autoresearch_state(root: Path) -> tuple[dict[str, Any], Path] | None:
    job = _autoresearch_job(root)
    if job is None:
        return None
    payload, _ = job
    state_ref = payload.get("state_dir", "research/autoresearch/run")
    if not isinstance(state_ref, str) or "\\" in state_ref or state_ref.startswith("/") or ".." in state_ref.split("/"):
        return None
    state_dir = root.joinpath(*state_ref.split("/"))
    meta = state_dir / "meta.json"
    if not meta.is_file():
        return {"status": "pending", "job_id": str(payload.get("job_id", ""))}, state_dir
    try:
        value = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "failed", "failure_layer": "runner-state-invalid"}, state_dir
    return value if isinstance(value, dict) else {"status": "failed", "failure_layer": "runner-state-invalid"}, state_dir


def _autoresearch_stop_gaps(root: Path) -> list[str]:
    state = _autoresearch_state(root)
    if state is None:
        return []
    payload, _ = state
    status = str(payload.get("status", "pending"))
    if status == "completed":
        return []
    if status == "awaiting_user_action":
        return ["autoresearch runner is awaiting user action"]
    return [f"autoresearch runner is not completed: {status}"]


def _resume_autoresearch_controller(root: Path) -> tuple[bool, str]:
    if os.environ.get("DS_LITE_AUTORESEARCH_CHILD") == "1":
        return False, "autoresearch/controller-child-guard"
    state = _autoresearch_state(root)
    job = _autoresearch_job(root)
    if state is None or job is None:
        return False, "autoresearch/controller-unavailable"
    payload, _ = job
    _, state_dir = state
    runner = Path(__file__).with_name("ds_lite_autoresearch_runner.py")
    job_id = str(payload.get("job_id", ""))
    if not runner.is_file() or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", job_id):
        return False, "autoresearch/controller-invalid-job"
    status = str(state[0].get("status", "pending"))
    prompt = payload.get("initial_prompt", payload.get("prompt", ""))
    goals = payload.get("frozen_goals", [])
    if not isinstance(prompt, str) or not prompt.strip() or not isinstance(goals, list):
        return False, "autoresearch/controller-invalid-job"
    normalized_goals = [item.strip() for item in goals if isinstance(item, str) and item.strip()]
    if len(normalized_goals) != len(goals) or not normalized_goals:
        return False, "autoresearch/controller-invalid-job"
    runner_mode = payload.get("runner_mode", AUTORESEARCH_RUNNER_MODE)
    if runner_mode not in {"watch", "bounded"}:
        return False, "autoresearch/controller-invalid-job"
    if runner_mode == "watch":
        command = [sys.executable, str(runner), "watch"]
    else:
        command = [
            sys.executable,
            str(runner),
            "run" if status == "pending" else "resume",
        ]
    command = [
        *command,
        "--root",
        str(root),
        "--job-id",
        job_id,
        "--state-dir",
        str(state_dir),
    ]
    if runner_mode == "watch" or status == "pending":
        command.extend(["--prompt", prompt])
        for goal in normalized_goals:
            command.extend(["--goal", goal])
    if runner_mode == "watch":
        # ``watch`` is the durable lifecycle owner modeled on vendor
        # ``runLoop``: a budget boundary becomes needs_resume, then the same
        # session is resumed until completion or a terminal blocker.
        command.extend(["--poll-seconds", "0"])
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=AUTORESEARCH_RUNNER_TIMEOUT_SECONDS,
            check=False,
            env=_project_temp_env(root),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "autoresearch/controller-execution"
    state_after = _autoresearch_state(root)
    if completed.returncode == 0 and state_after and state_after[0].get("status") == "completed":
        return True, "autoresearch/controller-completed"
    if state_after and state_after[0].get("status") == "awaiting_user_action":
        return False, "autoresearch/controller-awaiting-user-action"
    if state_after and state_after[0].get("status") == "failed":
        return False, str(state_after[0].get("failure_layer", "autoresearch/controller-failed"))
    return False, "autoresearch/controller-needs-resume"

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
        autonomy_was_active = _autonomy_is_active(root)
        result["additional_context"] = _mission_context(root)
        result["audit_required"] = True
        result["additional_context"] += "\nCommunication audit: profile: research-peer; detail: adaptive; before side effects, record auditable evidence for honor-01 through honor-08."
        autonomy = _autonomy_context(root)
        if autonomy:
            result["additional_context"] += "\n" + autonomy
        if autonomy_was_active:
            result["next_automatic_action"] = "resume-autonomy-controller"
        autoresearch = _autoresearch_state(root)
        if autoresearch is not None and _is_resume_request(payload):
            state, state_dir = autoresearch
            if state.get("status") in {"pending", "needs_resume"}:
                result["next_automatic_action"] = "resume-autoresearch-session"
                result["recovery_ref"] = str(state_dir.relative_to(root).as_posix())
            elif state.get("status") == "awaiting_user_action":
                completion = state.get("last_completion")
                result["control_action"] = "block-awaiting-user-action"
                result["failure_layer"] = str(completion.get("failure_layer", "awaiting-user-action")) if isinstance(completion, dict) else "awaiting-user-action"
                result["next_automatic_action"] = "await-user-action"
        pending = ds_lite_user_action.load_pending(root)
        if pending is not None:
            request, path = pending
            result["additional_context"] += (
                "\n当前任务被阻断于【用户动作确认】。"
                f"请执行【{request['exact_action']}】并回传【{path.relative_to(root).as_posix()} 对应的 response receipt】。"
                "在收到并验证该结果前，不启动 provider、浏览器、长任务、子任务或发布流程。"
            )
            result["user_action_request"] = {
                "request_id": request["request_id"],
                "scope": request["extensions"].get("scope", "unknown"),
                "request_ref": path.relative_to(root).as_posix(),
            }
        skill = _active_skill(payload)
        if skill:
            _, learning_message = _learning_context(root, skill)
            result["additional_context"] += "\n" + learning_message
        return result
    if event_name == "pre-tool-use":
        return _pre_tool_use(root, payload)
    if event_name == "post-tool-use":
        _audit_post_event(root, payload)
        autonomy_was_active = _autonomy_is_active(root)
        result["additional_context"] = _post_tool_context(root)
        autonomy = _autonomy_context(root)
        resume = _autonomy_resume_context(root)
        if autonomy:
            result["additional_context"] += "\n" + autonomy
        if autonomy_was_active or resume:
            result["additional_context"] += "\n" + (
                resume or "Autonomy controller has unfinished work; an external controller must resume it."
            )
            result["next_automatic_action"] = "resume-autonomy-controller"
        return result

    result["continue_once"] = False
    autonomy_was_active = _autonomy_is_active(root)
    autoresearch_was_active = bool(_autoresearch_stop_gaps(root))
    gaps = _stop_gaps(root)
    gaps.extend(_stop_quality_gaps(root))
    gaps.extend(_user_action_gaps(root))
    gaps.extend(_audit_stop_gaps(root))
    gaps.extend(_autonomy_stop_gaps(root))
    gaps.extend(_autoresearch_stop_gaps(root))
    skill = _active_skill(payload)
    if skill:
        try:
            ds_lite_learning.ensure(root, skill)
        except (OSError, UnicodeError, json.JSONDecodeError, ds_lite_learning.LearningError):
            gaps.append(f"learning receipt is missing or stale for ${skill}")
    if not gaps:
        return result
    result["control_action"] = "hook-in-turn-repair"
    result["failure_layer"] = "controller-incomplete"
    result["additional_context"] = (
        "DS Lite stop check: " + "; ".join(gaps) + ". Finalize once, report to the user, then stop."
    )
    autonomy_resume = _autonomy_resume_context(root)
    if autonomy_resume:
        result["additional_context"] += "\n" + autonomy_resume
        result["next_automatic_action"] = "resume-autonomy-controller"
        # Codex Stop hooks require a dedicated prompt to turn a block into a
        # continuation. additional_context alone is observational.
        result["prompt"] = autonomy_resume
    if autoresearch_was_active:
        result["next_automatic_action"] = "resume-autoresearch-session"
        result["controller_action"] = "external-controller-required"
        result["prompt"] = (
            "Resume the active DS Lite autoresearch session, complete the remaining frozen goals, "
            "and attempt Stop again."
        )
    elif not autonomy_resume:
        result["prompt"] = (
            "Finalize the unresolved DS Lite requirements below, write the required "
            "receipt or report, and then attempt Stop again. " + "; ".join(gaps)
        )
    if payload.get("stop_hook_active") is True:
        result["decision"] = "allow"
        result["control_action"] = "hook-handoff"
        result["hook_handoff"] = True
        result["continue_once"] = False
        result["continue"] = False
        return result
    result["decision"] = "block"
    result["control_action"] = "hook-in-turn-repair"
    result["continue_once"] = True
    # `continue_once` is retained for older hook consumers. Current Codex
    # continuation handling uses the explicit boolean together with `prompt`.
    result["continue"] = True
    result["failure_category"] = "iteration/incomplete-handoff"
    if any(item.startswith("claim/unsupported-completion") for item in gaps):
        result["failure_category"] = "claim/unsupported-completion"
    if any(item.startswith("communication audit is ") for item in gaps):
        result["blocked"] = True
    return result


def _write_host_acceptance_event(event_name: str, result: dict[str, Any], hook_input: dict[str, Any]) -> None:
    raw_directory = os.environ.get("DS_LITE_HOOK_ACCEPTANCE_DIR", "").strip()
    if not raw_directory:
        return
    directory = Path(raw_directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": HOST_EVENT_SCHEMA,
        "event_type": event_name,
        "decision": str(result.get("decision", "unknown")),
        "control_action": str(result.get("control_action", "unknown")),
        "stop_hook_active": hook_input.get("stop_hook_active") is True,
        "reason_present": bool(str(result.get("reason") or result.get("prompt") or "").strip()),
    }
    path = directory / f"{uuid.uuid4().hex}-{event_name}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
        handle.write("\n")


def _host_output(event_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Project DS Lite's internal decision into Codex's strict Hook JSON schema."""
    payload: dict[str, Any] = {}
    context = result.get("additional_context")
    if event_name in {"user-prompt-submit", "pre-tool-use", "post-tool-use"} and isinstance(context, str) and context:
        payload["hookSpecificOutput"] = {
            "hookEventName": EVENT_NAMES[event_name],
            "additionalContext": context,
        }
    if result.get("decision") == "block":
        reason = result.get("prompt")
        if not isinstance(reason, str) or not reason.strip():
            reason = context
        if isinstance(reason, str) and reason.strip():
            payload["decision"] = "block"
            payload["reason"] = reason
    return payload


def _install_result(root: str, apply: bool) -> tuple[dict[str, Any], int]:
    payload = {
        "host_supported": False,
        "config_written": False,
        "root": "project-relative-only",
        "reason": "Codex host hook installation is not supported by this helper; use the marketplace/host contract.",
    }
    return payload, 1 if apply else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one DeepScientist Lite hook event.")
    parser.add_argument(
        "event",
        choices=("user-prompt-submit", "pre-tool-use", "post-tool-use", "stop", "install"),
    )
    parser.add_argument("--root")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.event == "install":
        result, code = _install_result(args.root or "", args.apply)
        # Hook stdout is consumed by heterogeneous Windows/Unix hosts; keep the
        # transport ASCII-safe and let JSON consumers decode the escaped text.
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return code
    try:
        # Codex hosts may launch Python with a legacy Windows console code page.
        # Hook payloads can contain project paths with Chinese characters, so
        # stdin must be decoded as UTF-8 independently of the console locale.
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="strict")
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
        result = handle_event(args.event, payload)
        _write_host_acceptance_event(args.event, result, payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(_host_output(args.event, result), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
