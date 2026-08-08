#!/usr/bin/env python3
"""Validate and record one bounded DeepScientist Lite iteration."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ds_lite_protocol


SCHEMA_VERSION = "ds-lite.iteration.v1"
ITERATION_STATUSES = {"running", "completed", "partial", "blocked", "failed", "ambiguous"}
TERMINAL_STATUSES = ITERATION_STATUSES - {"running"}
HYPOTHESIS_STATUSES = {
    "untested",
    "supported",
    "weakened",
    "refuted",
    "inconclusive",
    "parked",
}
VALIDATION_STATUSES = {"pass", "fail", "not-run"}
GRAPH_CHANGE_KINDS = {
    "add-node",
    "update-node",
    "add-edge",
    "set-active",
    "set-status",
    "link-path",
    "render-status",
    "none",
}
ACTION_KINDS = {
    "scout",
    "idea",
    "collect-evidence",
    "execute",
    "debug",
    "review",
    "analysis",
    "write",
    "branch",
    "rollback",
    "stop",
    "ask-human",
    "status-check",
}
SELECTED_SKILLS = {
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-review",
    "ds-lite-analysis-write",
    "ds-lite-iterate",
    "ds-lite-coordinate",
}
REQUIRED_FIELDS = {
    "schema_version",
    "iteration_id",
    "work_unit_id",
    "profile_id",
    "execution_mode",
    "status",
    "selected_skill",
    "expected_revision",
    "before_revision",
    "after_revision",
    "action",
    "input_refs",
    "output_refs",
    "graph_changes",
    "validations",
    "stop_reason",
    "reflection",
    "user_report",
    "started_at",
    "completed_at",
    "extensions",
}


class IterationError(RuntimeError):
    pass


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IterationError(f"{label} must be an object")
    missing = fields - set(value)
    unknown = set(value) - fields
    if missing:
        raise IterationError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise IterationError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")
    if not isinstance(value.get("extensions"), dict):
        raise IterationError(f"{label}.extensions must be an object")
    return value


def _nonempty(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "a string" if allow_empty else "a non-empty string"
        raise IterationError(f"{label} must be {suffix}")
    return value


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise IterationError(f"{label} must be a{' non-empty' if nonempty else ''} list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise IterationError(f"{label} must be a list of non-empty strings")
    return value


def _refs(value: Any, label: str) -> list[str]:
    try:
        return ds_lite_protocol._validate_unique_refs(value, label)
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc


def _validate_revision(value: Any, label: str, *, allow_none: bool = False) -> None:
    if allow_none and value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise IterationError(f"{label} must be a non-negative integer")


def _validate_action(value: Any) -> None:
    fields = {
        "kind",
        "summary",
        "prediction",
        "falsification_condition",
        "resource_limits",
        "stop_condition",
        "extensions",
    }
    action = _object(value, fields, "action")
    try:
        ds_lite_protocol.validate_id(action["kind"], "action.kind")
        ds_lite_protocol._validate_resource_limits(action["resource_limits"], "action.resource_limits")
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc
    if action["kind"] == "exploit":
        raise IterationError("action.kind must map legacy exploit to execute before validation")
    if action["kind"] not in ACTION_KINDS:
        raise IterationError("action.kind is not registered for a bounded Lite iteration")
    for field in ("summary", "prediction", "falsification_condition", "stop_condition"):
        _nonempty(action[field], f"action.{field}")


def _validate_graph_changes(value: Any) -> None:
    if not isinstance(value, list):
        raise IterationError("graph_changes must be a list")
    fields = {"kind", "subject_id", "summary", "extensions"}
    for index, item in enumerate(value):
        change = _object(item, fields, f"graph_changes[{index}]")
        if change["kind"] not in GRAPH_CHANGE_KINDS:
            raise IterationError(f"graph_changes[{index}].kind is invalid")
        try:
            ds_lite_protocol.validate_id(change["subject_id"], f"graph_changes[{index}].subject_id")
        except ds_lite_protocol.ProtocolError as exc:
            raise IterationError(str(exc)) from exc
        _nonempty(change["summary"], f"graph_changes[{index}].summary")


def _validate_validations(value: Any) -> None:
    if not isinstance(value, list):
        raise IterationError("validations must be a list")
    fields = {"command", "status", "summary", "extensions"}
    for index, item in enumerate(value):
        validation = _object(item, fields, f"validations[{index}]")
        _nonempty(validation["command"], f"validations[{index}].command")
        _nonempty(validation["summary"], f"validations[{index}].summary")
        if validation["status"] not in VALIDATION_STATUSES:
            raise IterationError(f"validations[{index}].status is invalid")


def _validate_hypothesis_records(value: Any, label: str, fields: set[str]) -> None:
    if not isinstance(value, list):
        raise IterationError(f"{label} must be a list")
    seen: set[str] = set()
    for index, item in enumerate(value):
        record = _object(item, fields, f"{label}[{index}]")
        try:
            hypothesis_id = ds_lite_protocol.validate_id(
                record["hypothesis_id"], f"{label}[{index}].hypothesis_id"
            )
        except ds_lite_protocol.ProtocolError as exc:
            raise IterationError(str(exc)) from exc
        if hypothesis_id in seen:
            raise IterationError(f"{label} contains duplicate hypothesis_id: {hypothesis_id}")
        seen.add(hypothesis_id)
        if record["status"] not in HYPOTHESIS_STATUSES:
            raise IterationError(f"{label}[{index}].status is invalid")


def _validate_reflection(value: Any) -> None:
    fields = {
        "observed_outcomes",
        "hypothesis_updates",
        "expectation_gap",
        "negative_results",
        "responsibility",
        "learned_boundaries",
        "next_candidates",
        "minimal_discriminating_test",
        "extensions",
    }
    reflection = _object(value, fields, "reflection")
    _string_list(reflection["observed_outcomes"], "reflection.observed_outcomes")
    _string_list(reflection["learned_boundaries"], "reflection.learned_boundaries")
    _nonempty(reflection["expectation_gap"], "reflection.expectation_gap", allow_empty=True)
    _nonempty(
        reflection["minimal_discriminating_test"],
        "reflection.minimal_discriminating_test",
        allow_empty=True,
    )

    update_fields = {"hypothesis_id", "status", "evidence_refs", "summary", "extensions"}
    _validate_hypothesis_records(reflection["hypothesis_updates"], "reflection.hypothesis_updates", update_fields)
    for index, item in enumerate(reflection["hypothesis_updates"]):
        refs = _refs(item["evidence_refs"], f"reflection.hypothesis_updates[{index}].evidence_refs")
        if item["status"] in {"supported", "weakened", "refuted"} and not refs:
            raise IterationError(
                f"{item['status']} hypothesis update requires evidence_refs"
            )
        _nonempty(item["summary"], f"reflection.hypothesis_updates[{index}].summary")

    negative_fields = {"summary", "evidence_refs", "extensions"}
    negatives = reflection["negative_results"]
    if not isinstance(negatives, list):
        raise IterationError("reflection.negative_results must be a list")
    for index, item in enumerate(negatives):
        result = _object(item, negative_fields, f"reflection.negative_results[{index}]")
        _nonempty(result["summary"], f"reflection.negative_results[{index}].summary")
        refs = _refs(result["evidence_refs"], f"reflection.negative_results[{index}].evidence_refs")
        if not refs:
            raise IterationError(
                f"reflection.negative_results[{index}].evidence_refs must not be empty"
            )

    responsibility_fields = {
        "authorization_basis",
        "boundaries_respected",
        "unresolved_obligations",
        "extensions",
    }
    responsibility = _object(reflection["responsibility"], responsibility_fields, "reflection.responsibility")
    _nonempty(responsibility["authorization_basis"], "reflection.responsibility.authorization_basis", allow_empty=True)
    _string_list(responsibility["boundaries_respected"], "reflection.responsibility.boundaries_respected")
    _string_list(
        responsibility["unresolved_obligations"],
        "reflection.responsibility.unresolved_obligations",
    )

    candidate_fields = {"hypothesis_id", "title", "status", "minimal_test", "extensions"}
    _validate_hypothesis_records(reflection["next_candidates"], "reflection.next_candidates", candidate_fields)
    for index, item in enumerate(reflection["next_candidates"]):
        _nonempty(item["title"], f"reflection.next_candidates[{index}].title")
        _nonempty(item["minimal_test"], f"reflection.next_candidates[{index}].minimal_test")


def _validate_user_report(value: Any) -> None:
    fields = {
        "summary",
        "files_changed",
        "validation_summary",
        "failure_layer",
        "unverified",
        "hypothesis_changes",
        "next_action",
        "decision_needed",
        "extensions",
    }
    report = _object(value, fields, "user_report")
    for field in ("summary", "validation_summary", "failure_layer", "next_action", "decision_needed"):
        _nonempty(report[field], f"user_report.{field}", allow_empty=True)
    _refs(report["files_changed"], "user_report.files_changed")
    _string_list(report["unverified"], "user_report.unverified")
    _string_list(report["hypothesis_changes"], "user_report.hypothesis_changes")


def validate_iteration(payload: Any) -> dict[str, Any]:
    iteration = _object(payload, REQUIRED_FIELDS, SCHEMA_VERSION)
    sensitive = ds_lite_protocol.find_forbidden_key(iteration)
    if sensitive:
        raise IterationError(
            f"{SCHEMA_VERSION} contains a sensitive or hidden-reasoning field: {sensitive}"
        )
    if iteration["schema_version"] != SCHEMA_VERSION:
        raise IterationError(f"schema_version must be {SCHEMA_VERSION}")
    try:
        iteration_id = ds_lite_protocol.validate_id(iteration["iteration_id"], "iteration_id")
        work_unit_id = ds_lite_protocol.validate_id(iteration["work_unit_id"], "work_unit_id")
        ds_lite_protocol.validate_id(iteration["profile_id"], "profile_id")
        ds_lite_protocol.validate_id(iteration["selected_skill"], "selected_skill")
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc
    if iteration_id == work_unit_id:
        raise IterationError("iteration_id and work_unit_id must differ")
    if iteration["selected_skill"] not in SELECTED_SKILLS:
        raise IterationError("selected_skill must name one registered DS Lite action skill")
    if iteration["execution_mode"] not in ds_lite_protocol.EXECUTION_MODES:
        raise IterationError("execution_mode must be none, inline, external, or human")
    if iteration["status"] not in ITERATION_STATUSES:
        raise IterationError("status must be running, completed, partial, blocked, failed, or ambiguous")
    _validate_revision(iteration["expected_revision"], "expected_revision")
    _validate_revision(iteration["before_revision"], "before_revision")
    _validate_revision(iteration["after_revision"], "after_revision", allow_none=True)
    if iteration["expected_revision"] != iteration["before_revision"]:
        raise IterationError("expected_revision must equal before_revision")
    _validate_action(iteration["action"])
    _refs(iteration["input_refs"], "input_refs")
    _refs(iteration["output_refs"], "output_refs")
    _validate_graph_changes(iteration["graph_changes"])
    _validate_validations(iteration["validations"])
    _nonempty(iteration["stop_reason"], "stop_reason")
    _validate_reflection(iteration["reflection"])
    _validate_user_report(iteration["user_report"])
    try:
        ds_lite_protocol.validate_timestamp(iteration["started_at"], "started_at")
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc

    if iteration["status"] == "running":
        if iteration["after_revision"] is not None or iteration["completed_at"] != "":
            raise IterationError("running iteration must have null after_revision and empty completed_at")
        if iteration["stop_reason"] != "in-progress":
            raise IterationError("running iteration stop_reason must be in-progress")
    else:
        if iteration["after_revision"] is None:
            raise IterationError("terminal iteration requires after_revision")
        if iteration["after_revision"] < iteration["before_revision"]:
            raise IterationError("after_revision must not be less than before_revision")
        try:
            ds_lite_protocol.validate_timestamp(iteration["completed_at"], "completed_at")
        except ds_lite_protocol.ProtocolError as exc:
            raise IterationError(str(exc)) from exc
        if not iteration["user_report"]["summary"].strip():
            raise IterationError("terminal iteration requires a user_report.summary")
    return json.loads(json.dumps(iteration))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IterationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise IterationError(f"{label} must contain a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise IterationError(f"iteration already exists: {path.name}") from exc


def _iteration_ref(iteration_id: str) -> str:
    return f"research/iterations/{iteration_id}.json"


def _resolve_iteration(root: Path, ref: str) -> Path:
    try:
        normalized = ds_lite_protocol.validate_ref(ref, "iteration ref")
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc
    if normalized.startswith("external://") or not normalized.startswith("research/iterations/"):
        raise IterationError("iteration ref must be a project-relative research/iterations JSON path")
    path = root / normalized
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise IterationError("iteration ref escapes the project root") from exc
    return path


def _load_context(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    graph = _read_json(root / "research" / "state" / "graph.json", "Graph v2")
    if graph.get("schema_version") != "ds-lite.graph.v2":
        raise IterationError("iteration lifecycle requires ds-lite.graph.v2")
    work_unit_raw = _read_json(root / "research" / "work-unit.json", "work unit")
    try:
        work_unit = ds_lite_protocol.validate_work_unit(work_unit_raw)
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(f"work unit is invalid: {exc}") from exc
    return graph, work_unit


def _ledger_projection(root: Path, work_unit_id: str) -> dict[str, Any]:
    """Read-only, bounded projection of v6 ledgers for an iteration receipt."""
    artifacts = root / "research" / "artifacts"
    projection: dict[str, Any] = {
        "signal_ledger_refs": [],
        "active_signal_count": 0,
        "claim_ledger_refs": [],
        "claim_readiness": "unknown",
        "frontier_refs": [],
        "selected_candidate": None,
    }
    if not artifacts.is_dir():
        return projection
    for path in sorted(artifacts.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("work_unit_id") != work_unit_id:
            continue
        schema = payload.get("schema_version")
        ref = path.relative_to(root).as_posix()
        if schema == "ds-lite.signal-ledger.v1":
            projection["signal_ledger_refs"].append(ref)
            projection["active_signal_count"] += sum(1 for item in payload.get("signals", []) if item.get("status") == "active")
        elif schema == "ds-lite.claim-ledger.v1":
            projection["claim_ledger_refs"].append(ref)
            claims = payload.get("claims", [])
            if claims:
                statuses = {item.get("status") for item in claims}
                projection["claim_readiness"] = "ready" if statuses <= {"supported"} else ("blocked" if "contested" in statuses else "draft")
        elif schema == "ds-lite.frontier.v1":
            projection["frontier_refs"].append(ref)
            selected = next((item.get("candidate_id") for item in payload.get("candidates", []) if item.get("status") == "selected"), None)
            if selected:
                projection["selected_candidate"] = selected
    return projection


def _blank_reflection() -> dict[str, Any]:
    return {
        "observed_outcomes": [],
        "hypothesis_updates": [],
        "expectation_gap": "",
        "negative_results": [],
        "responsibility": {
            "authorization_basis": "",
            "boundaries_respected": [],
            "unresolved_obligations": [],
            "extensions": {},
        },
        "learned_boundaries": [],
        "next_candidates": [],
        "minimal_discriminating_test": "",
        "extensions": {},
    }


def _blank_user_report() -> dict[str, Any]:
    return {
        "summary": "",
        "files_changed": [],
        "validation_summary": "",
        "failure_layer": "",
        "unverified": [],
        "hypothesis_changes": [],
        "next_action": "",
        "decision_needed": "",
        "extensions": {},
    }


def initialize_iteration(
    root: Path | str,
    *,
    iteration_id: str,
    selected_skill: str,
    action: dict[str, Any],
    input_refs: list[str],
    expected_revision: int,
) -> dict[str, Any]:
    project_root = Path(root)
    graph, work_unit = _load_context(project_root)
    current_revision = graph.get("revision")
    if current_revision != expected_revision:
        raise IterationError(
            f"stale revision: expected {expected_revision}, found {current_revision}"
        )
    try:
        ds_lite_protocol.validate_id(iteration_id, "iteration_id")
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(str(exc)) from exc
    ref = _iteration_ref(iteration_id)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "iteration_id": iteration_id,
        "work_unit_id": work_unit["work_unit_id"],
        "profile_id": work_unit["profile_id"],
        "execution_mode": work_unit["execution_mode"],
        "status": "running",
        "selected_skill": selected_skill,
        "expected_revision": expected_revision,
        "before_revision": current_revision,
        "after_revision": None,
        "action": action,
        "input_refs": input_refs,
        "output_refs": [],
        "graph_changes": [],
        "validations": [],
        "stop_reason": "in-progress",
        "reflection": _blank_reflection(),
        "user_report": _blank_user_report(),
        "started_at": _utc_now(),
        "completed_at": "",
        "extensions": {"iteration_ref": ref, "v6_projection": _ledger_projection(project_root, work_unit["work_unit_id"])},
    }
    validated = validate_iteration(payload)
    path = _resolve_iteration(project_root, ref)
    _write_new_json(path, validated)
    work_unit["active_iteration_ref"] = ref
    try:
        ds_lite_protocol.validate_work_unit(work_unit)
    except ds_lite_protocol.ProtocolError as exc:
        raise IterationError(f"cannot attach iteration to work unit: {exc}") from exc
    _atomic_write_json(project_root / "research" / "work-unit.json", work_unit)
    return validated


def verify_iteration(root: Path | str, ref: str) -> dict[str, Any]:
    project_root = Path(root)
    graph, work_unit = _load_context(project_root)
    payload = validate_iteration(_read_json(_resolve_iteration(project_root, ref), "iteration"))
    for field in ("work_unit_id", "profile_id", "execution_mode"):
        if payload[field] != work_unit[field]:
            raise IterationError(f"iteration {field} does not match active work unit")
    if work_unit["active_iteration_ref"] and work_unit["active_iteration_ref"] != ref:
        raise IterationError("iteration ref is not the active work unit iteration")
    current_revision = graph.get("revision")
    if not isinstance(current_revision, int):
        raise IterationError("Graph revision must be an integer")
    if payload["status"] == "running" and current_revision < payload["before_revision"]:
        raise IterationError("Graph revision regressed below the running iteration baseline")
    if payload["status"] in TERMINAL_STATUSES and current_revision != payload["after_revision"]:
        raise IterationError(
            f"terminal iteration after_revision {payload['after_revision']} does not match Graph revision {current_revision}"
        )
    return payload


def finalize_iteration(root: Path | str, ref: str, result: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(root)
    running = verify_iteration(project_root, ref)
    if running["status"] != "running":
        raise IterationError(f"iteration is already terminal: {running['status']}")
    result_fields = {
        "status",
        "after_revision",
        "output_refs",
        "graph_changes",
        "validations",
        "stop_reason",
        "reflection",
        "user_report",
        "completed_at",
        "extensions",
    }
    terminal = _object(result, result_fields, "iteration result")
    if terminal["status"] not in TERMINAL_STATUSES:
        raise IterationError("iteration result status must be terminal")
    finished = dict(running)
    finished.update(terminal)
    finished["extensions"] = {
        **running.get("extensions", {}),
        **terminal.get("extensions", {}),
    }
    validated = validate_iteration(finished)
    graph, _work_unit = _load_context(project_root)
    if validated["after_revision"] != graph.get("revision"):
        raise IterationError(
            f"after_revision {validated['after_revision']} does not match Graph revision {graph.get('revision')}"
        )
    _atomic_write_json(_resolve_iteration(project_root, ref), validated)
    return validated


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Validate and record one bounded DeepScientist Lite iteration."
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    initialize = subcommands.add_parser("init", help="Register a running iteration before action.")
    initialize.add_argument("--root", type=Path, required=True)
    initialize.add_argument("--iteration-id", required=True)
    initialize.add_argument("--selected-skill", required=True)
    initialize.add_argument("--action-json", type=Path, required=True)
    initialize.add_argument("--input-ref", action="append", default=[])
    initialize.add_argument("--expected-revision", type=int, required=True)
    finalize = subcommands.add_parser("finalize", help="Move one running iteration to a terminal state.")
    finalize.add_argument("--root", type=Path, required=True)
    finalize.add_argument("--path", required=True)
    finalize.add_argument("--result-json", type=Path, required=True)
    verify = subcommands.add_parser("verify", help="Validate an iteration and its current work-unit context.")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--path", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            payload = initialize_iteration(
                args.root,
                iteration_id=args.iteration_id,
                selected_skill=args.selected_skill,
                action=_read_json(args.action_json, "action JSON"),
                input_refs=args.input_ref,
                expected_revision=args.expected_revision,
            )
        elif args.command == "finalize":
            payload = finalize_iteration(
                args.root,
                args.path,
                _read_json(args.result_json, "result JSON"),
            )
        else:
            payload = verify_iteration(args.root, args.path)
    except (IterationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema_version": payload["schema_version"],
                "iteration_id": payload["iteration_id"],
                "status": payload["status"],
                "path": payload.get("extensions", {}).get("iteration_ref", args.path if hasattr(args, "path") else ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
