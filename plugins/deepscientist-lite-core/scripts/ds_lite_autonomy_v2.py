#!/usr/bin/env python3
"""Bounded foreground autonomy contract with policy/execution binding."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_SCHEMA = "ds-lite.autonomy-contract.v2"
SUMMARY_SCHEMA = "ds-lite.autonomy-summary.v2"
EXECUTION_SCHEMA = "ds-lite.autonomy-execution.v1"
TERMINAL_POLICIES = {"report", "handoff", "release"}
EFFECTS = {"read", "workspace-write", "external-write", "release"}
RETRY_CLASSES = {"none", "transient"}
ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,79}$")


class AutonomyV2Error(ValueError):
    pass


def _relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AutonomyV2Error(f"{field} must be a project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AutonomyV2Error(f"{field} must be a project-relative POSIX path")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _validate_authorization(value: Any) -> dict[str, Any]:
    required = {"status", "authority", "ref", "allowed_effects", "release_gate"}
    if not isinstance(value, dict) or set(value) != required:
        raise AutonomyV2Error("authorization fields are invalid")
    if value["status"] != "approved" or not ID_RE.fullmatch(str(value["authority"])):
        raise AutonomyV2Error("authorization must be explicitly approved")
    ref = _relative(value["ref"], "authorization.ref")
    allowed = value["allowed_effects"]
    if not isinstance(allowed, list) or not allowed or len(set(allowed)) != len(allowed) or set(allowed) - EFFECTS:
        raise AutonomyV2Error("authorization.allowed_effects is invalid")
    if not isinstance(value["release_gate"], bool):
        raise AutonomyV2Error("authorization.release_gate is invalid")
    return {
        "status": "approved",
        "authority": value["authority"],
        "ref": ref,
        "allowed_effects": sorted(allowed),
        "release_gate": value["release_gate"],
    }


def _validate_execution_gate(value: Any, field: str) -> dict[str, Any]:
    required = {"command", "receipt_ref", "retry_class"}
    optional = {"continuation_command", "continuation_receipt_ref"}
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - optional:
        raise AutonomyV2Error(f"{field} fields are invalid")
    if not isinstance(value["command"], list) or not value["command"] or not all(isinstance(item, str) and item for item in value["command"]):
        raise AutonomyV2Error(f"{field}.command is invalid")
    if value["retry_class"] not in RETRY_CLASSES:
        raise AutonomyV2Error(f"{field}.retry_class is invalid")
    result = {
        "command": list(value["command"]),
        "receipt_ref": _relative(value["receipt_ref"], f"{field}.receipt_ref"),
        "retry_class": value["retry_class"],
    }
    continuation = {"continuation_command", "continuation_receipt_ref"}
    if continuation & set(value) and not continuation.issubset(value):
        raise AutonomyV2Error(f"{field} continuation fields must be supplied together")
    if continuation.issubset(value):
        if not isinstance(value["continuation_command"], list) or not value["continuation_command"] or not all(isinstance(item, str) and item for item in value["continuation_command"]):
            raise AutonomyV2Error(f"{field}.continuation_command is invalid")
        result["continuation_command"] = list(value["continuation_command"])
        result["continuation_receipt_ref"] = _relative(value["continuation_receipt_ref"], f"{field}.continuation_receipt_ref")
    return result


def _legacy_execution(contract: dict[str, Any], legacy: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(legacy, dict):
        raise AutonomyV2Error("execution.contract must be an object")
    if legacy.get("schema_version") != "ds-lite.autonomy-contract.v1":
        raise AutonomyV2Error("legacy execution contract schema is invalid")
    if legacy.get("goals") != contract["goals"]:
        raise AutonomyV2Error("legacy execution goals do not match policy goals")
    budget = legacy.get("budget")
    if not isinstance(budget, dict) or budget.get("max_seconds") != contract["budget"]["max_seconds"] or budget.get("max_attempts_per_gate") != contract["budget"]["max_attempts_per_gate"]:
        raise AutonomyV2Error("legacy execution budget does not match policy budget")
    authorization = legacy.get("authorization")
    expected = contract["authorization"]
    if not isinstance(authorization, dict) or authorization != {"status": "approved", "authority": expected["authority"], "ref": expected["ref"]}:
        raise AutonomyV2Error("legacy execution authorization does not match policy authorization")
    gates = legacy.get("gates")
    if not isinstance(gates, list) or len(gates) != len(contract["gates"]):
        raise AutonomyV2Error("legacy execution gate count does not match policy gates")
    policy_by_id = {gate["id"]: gate for gate in contract["gates"]}
    result: dict[str, dict[str, Any]] = {}
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("id") not in policy_by_id:
            raise AutonomyV2Error("legacy execution gate is unknown")
        policy = policy_by_id[gate["id"]]
        if gate.get("depends_on") != policy["depends_on"]:
            raise AutonomyV2Error("legacy execution dependencies do not match policy gates")
        result[gate["id"]] = _validate_execution_gate(gate, f"execution.contract.gates[{gate['id']}]")
    if set(result) != set(policy_by_id):
        raise AutonomyV2Error("legacy execution gate ids do not match policy gates")
    return result


def _execution_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    execution = contract.get("execution")
    if execution is None:
        return None
    if not isinstance(execution, dict):
        raise AutonomyV2Error("execution must be an object")
    if "contract" in execution:
        if set(execution) != {"contract"}:
            raise AutonomyV2Error("legacy execution projection has unsupported fields")
        return _legacy_execution(contract, execution["contract"])
    if set(execution) != {"schema_version", "gates"} or execution.get("schema_version") != EXECUTION_SCHEMA:
        raise AutonomyV2Error("execution projection is invalid")
    gates = execution["gates"]
    if not isinstance(gates, dict):
        raise AutonomyV2Error("execution.gates must be an object keyed by gate id")
    policy_ids = {gate["id"] for gate in contract["gates"]}
    if set(gates) != policy_ids:
        raise AutonomyV2Error("execution gate ids do not match policy gates")
    return {gate_id: _validate_execution_gate(value, f"execution.gates.{gate_id}") for gate_id, value in gates.items()}


def validate_contract(value: Any, *, project_root: Path | None = None) -> dict[str, Any]:
    required = {"schema_version", "work_unit_ref", "goals", "gates", "budget", "authorization", "continuity", "terminal_policy"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise AutonomyV2Error("autonomy contract v2 fields are incomplete")
    if value["schema_version"] != CONTRACT_SCHEMA:
        raise AutonomyV2Error("schema_version must be ds-lite.autonomy-contract.v2")
    work_unit = _relative(value["work_unit_ref"], "work_unit_ref")
    if project_root is not None and not (project_root / Path(*PurePosixPath(work_unit).parts)).is_file():
        raise AutonomyV2Error("work_unit_ref is not present")
    goals = value["goals"]
    if not isinstance(goals, list) or not goals or not all(isinstance(item, str) and item.strip() for item in goals):
        raise AutonomyV2Error("goals must be a non-empty list")
    budget = value["budget"]
    if not isinstance(budget, dict) or set(budget) != {"max_seconds", "max_attempts_per_gate"}:
        raise AutonomyV2Error("budget fields are invalid")
    if not isinstance(budget["max_seconds"], int) or budget["max_seconds"] <= 0:
        raise AutonomyV2Error("budget.max_seconds must be positive")
    if not isinstance(budget["max_attempts_per_gate"], int) or not 1 <= budget["max_attempts_per_gate"] <= 12:
        raise AutonomyV2Error("budget.max_attempts_per_gate is invalid")
    authorization = _validate_authorization(value["authorization"])
    if value["terminal_policy"] not in TERMINAL_POLICIES:
        raise AutonomyV2Error("terminal_policy is invalid")
    gates = value["gates"]
    if not isinstance(gates, list) or not gates:
        raise AutonomyV2Error("gates must contain identified gate objects")
    normalized_gates: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict) or set(gate) != {"id", "depends_on", "effect"} or not ID_RE.fullmatch(str(gate.get("id", ""))):
            raise AutonomyV2Error(f"gates[{index}] is invalid")
        gate_id = gate["id"]
        if gate_id in ids:
            raise AutonomyV2Error("gate ids must be unique")
        ids.add(gate_id)
        if not isinstance(gate["depends_on"], list) or not all(isinstance(item, str) and ID_RE.fullmatch(item) for item in gate["depends_on"]):
            raise AutonomyV2Error(f"gates[{index}].depends_on is invalid")
        if gate["effect"] not in EFFECTS or gate["effect"] not in authorization["allowed_effects"]:
            raise AutonomyV2Error(f"gates[{index}].effect is not authorized")
        if gate["effect"] == "release" and (value["terminal_policy"] != "release" or not authorization["release_gate"]):
            raise AutonomyV2Error("release effect requires terminal_policy=release and a formal release gate")
        normalized_gates.append({"id": gate_id, "depends_on": list(gate["depends_on"]), "effect": gate["effect"]})
    if any(dependency not in ids for gate in normalized_gates for dependency in gate["depends_on"]):
        raise AutonomyV2Error("gate dependency is unknown")
    if value["terminal_policy"] == "release" and (not authorization["release_gate"] or "release" not in authorization["allowed_effects"]):
        raise AutonomyV2Error("release requires a separate formal release gate")
    continuity = value["continuity"]
    if not isinstance(continuity, dict) or continuity.get("mode") != "foreground-bounded":
        raise AutonomyV2Error("continuity.mode must be foreground-bounded")
    normalized = {
        "schema_version": CONTRACT_SCHEMA,
        "work_unit_ref": work_unit,
        "goals": list(goals),
        "gates": normalized_gates,
        "budget": {"max_seconds": budget["max_seconds"], "max_attempts_per_gate": budget["max_attempts_per_gate"]},
        "authorization": authorization,
        "continuity": dict(continuity),
        "terminal_policy": value["terminal_policy"],
    }
    if "execution" in value:
        normalized["execution"] = value["execution"]
    return normalized


def _summary(contract: dict[str, Any], result: dict[str, Any] | None, *, status: str, next_action: str, blocked_reason: str | None = None) -> dict[str, Any]:
    authorization = contract["authorization"]
    release_authorized = contract["terminal_policy"] == "release" and authorization["release_gate"]
    payload = {
        "schema_version": SUMMARY_SCHEMA,
        "work_unit_ref": contract["work_unit_ref"],
        "goals": contract["goals"],
        "goal_digest": _digest(sorted(contract["goals"])),
        "gate_ids": sorted(gate["id"] for gate in contract["gates"]),
        "authorization_ref": authorization["ref"],
        "authorization_digest": _digest(authorization),
        "status": status,
        "completed_gates": sorted((result or {}).get("completed_gates", [])),
        "blocked_gates": sorted((result or {}).get("blocked_gates", [])),
        "awaiting_user_action_gates": sorted((result or {}).get("awaiting_user_action_gates", [])),
        "gates": (result or {}).get("gates", {}),
        "terminal_policy": contract["terminal_policy"],
        "release_authorized": release_authorized,
        "next_action": next_action,
        "raw_output_persisted": False,
    }
    if blocked_reason:
        payload["failure_layer"] = "autonomy-v2"
        payload["blocked_reason"] = blocked_reason
    return payload


def summarize(contract: dict[str, Any], *, status: str, completed: list[str], blocked: list[str], next_action: str) -> dict[str, Any]:
    normalized = validate_contract(contract)
    return _summary(normalized, {"completed_gates": completed, "blocked_gates": blocked}, status=status, next_action=next_action)


def _load_v1_controller():
    path = Path(__file__).with_name("ds_lite_autonomy.py")
    spec = importlib.util.spec_from_file_location("ds_lite_autonomy_v1_runtime", path)
    if spec is None or spec.loader is None:
        raise AutonomyV2Error("v1 controller is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _to_v1_contract(contract: dict[str, Any], execution: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gate_ids = [gate["id"] for gate in contract["gates"]]
    v1_gates = []
    for policy in contract["gates"]:
        entry = {"id": policy["id"], "depends_on": policy["depends_on"], **execution[policy["id"]]}
        v1_gates.append(entry)
    release_authorized = contract["terminal_policy"] == "release" and contract["authorization"]["release_gate"]
    return {
        "schema_version": "ds-lite.autonomy-contract.v1",
        "autonomy_id": f"v2-{_digest([contract['work_unit_ref'], contract['goals'], gate_ids])[:24]}",
        "status": "prepared",
        "goals": contract["goals"],
        "gates": v1_gates,
        "budget": contract["budget"],
        "authorization": {
            "status": "approved",
            "authority": contract["authorization"]["authority"],
            "ref": contract["authorization"]["ref"],
        },
        "release": {"authorized": release_authorized, "required_gates": gate_ids},
    }


def run_foreground(root: Path, contract_path: Path, output: Path, *, resume: bool = False) -> dict[str, Any]:
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutonomyV2Error(f"cannot read autonomy contract: {exc}") from exc
    normalized = validate_contract(contract, project_root=root)
    execution = _execution_map(normalized)
    output.mkdir(parents=True, exist_ok=True)
    if execution is None:
        blocked = _summary(normalized, None, status="blocked", next_action="awaiting-user-action", blocked_reason="v2 contract requires an explicit execution projection")
        (output / "summary-v2.json").write_text(json.dumps(blocked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return blocked
    result = _load_v1_controller().run(root, _to_v1_contract(normalized, execution), output, resume=resume)
    if result.get("status") == "completed":
        next_action = "formal-release-gate" if normalized["terminal_policy"] == "release" else ("handoff" if normalized["terminal_policy"] == "handoff" else "final-report")
    else:
        next_action = result.get("next_action", "resume-independent-gate")
    summary = _summary(normalized, result, status=result.get("status", "blocked"), next_action=next_action)
    (output / "summary-v2.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a bounded DS Lite autonomy v2 contract.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_foreground(Path(args.root), Path(args.contract), Path(args.output), resume=args.resume)
    except (OSError, UnicodeError, json.JSONDecodeError, AutonomyV2Error) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "autonomy-v2", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": result.get("status", "blocked"), "next_action": result.get("next_action", "awaiting-user-action")}, ensure_ascii=True))
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
