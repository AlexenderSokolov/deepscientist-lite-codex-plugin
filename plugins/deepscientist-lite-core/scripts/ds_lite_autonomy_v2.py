#!/usr/bin/env python3
"""Generic, non-release autonomy contract for DS Lite 0.10 beta."""
from __future__ import annotations

import hashlib
import json
import importlib.util
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_SCHEMA = "ds-lite.autonomy-contract.v2"
SUMMARY_SCHEMA = "ds-lite.autonomy-summary.v2"
TERMINAL_POLICIES = {"report", "handoff", "release"}


class AutonomyV2Error(ValueError):
    pass


def _relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AutonomyV2Error(f"{field} must be a project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AutonomyV2Error(f"{field} must be a project-relative POSIX path")
    return value


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
    if not isinstance(budget, dict) or not isinstance(budget.get("max_seconds"), int) or budget["max_seconds"] <= 0:
        raise AutonomyV2Error("budget.max_seconds must be positive")
    authorization = value["authorization"]
    if not isinstance(authorization, dict) or authorization.get("status") != "approved" or not authorization.get("scope"):
        raise AutonomyV2Error("authorization.scope must be explicitly approved")
    if value["terminal_policy"] not in TERMINAL_POLICIES:
        raise AutonomyV2Error("terminal_policy is invalid")
    if value["terminal_policy"] == "release" and authorization.get("release_gate") is not True:
        raise AutonomyV2Error("release requires a separate formal release gate")
    gates = value["gates"]
    if not isinstance(gates, list) or not gates or any(not isinstance(gate, dict) or not gate.get("id") for gate in gates):
        raise AutonomyV2Error("gates must contain identified gate objects")
    gate_ids = {gate["id"] for gate in gates}
    if len(gate_ids) != len(gates):
        raise AutonomyV2Error("gate ids must be unique")
    for gate in gates:
        for dependency in gate.get("depends_on", []):
            if dependency not in gate_ids:
                raise AutonomyV2Error("gate dependency is unknown")
    normalized = dict(value)
    normalized["continuity"] = dict(value.get("continuity") or {})
    normalized["terminal_policy"] = value["terminal_policy"]
    return normalized


def summarize(contract: dict[str, Any], *, status: str, completed: list[str], blocked: list[str], next_action: str) -> dict[str, Any]:
    normalized = validate_contract(contract)
    release_authorized = normalized["terminal_policy"] == "release" and normalized["authorization"].get("release_gate") is True
    return {
        "schema_version": SUMMARY_SCHEMA,
        "work_unit_ref": normalized["work_unit_ref"],
        "goals": normalized["goals"],
        "status": status,
        "completed_gates": sorted(set(completed)),
        "blocked_gates": sorted(set(blocked)),
        "terminal_policy": normalized["terminal_policy"],
        "release_authorized": release_authorized,
        "next_action": "formal-release-gate" if status == "completed" and normalized["terminal_policy"] == "release" and not release_authorized else next_action,
        "goal_digest": hashlib.sha256(json.dumps(sorted(normalized["goals"]), separators=(",", ":")).encode()).hexdigest(),
        "raw_output_persisted": False,
    }


def _load_v1_controller():
    """Load the legacy bounded executor without making v2 depend on package imports."""
    path = Path(__file__).with_name("ds_lite_autonomy.py")
    spec = importlib.util.spec_from_file_location("ds_lite_autonomy_v1_runtime", path)
    if spec is None or spec.loader is None:
        raise AutonomyV2Error("v1 controller is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_foreground(root: Path, contract_path: Path, output: Path, *, resume: bool = False) -> dict[str, Any]:
    """Execute a v2 contract through the bounded v1 engine when an execution plan is present.

    v2 intentionally separates policy from commands. A contract without an explicit
    ``execution`` projection is therefore reported as blocked instead of silently
    inventing commands or release authority.
    """
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutonomyV2Error(f"cannot read autonomy contract: {exc}") from exc
    normalized = validate_contract(contract, project_root=root)
    execution = normalized.get("execution")
    if not isinstance(execution, dict) or not isinstance(execution.get("contract"), dict):
        blocked = summarize(normalized, status="blocked", completed=[], blocked=["execution-plan"], next_action="awaiting-user-action")
        blocked["failure_layer"] = "autonomy-v2"
        blocked["blocked_reason"] = "v2 contract requires an explicit execution projection"
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(blocked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return blocked
    legacy = execution["contract"]
    if not isinstance(legacy, dict):
        raise AutonomyV2Error("execution.contract must be an object")
    legacy = dict(legacy)
    # v1's parser requires this compatibility bit to be true. It is an
    # internal adapter value only; the v2 result below always clears release
    # authorization and routes completion through the formal release gate.
    legacy["release"] = {"authorized": True, "required_gates": [g.get("id") for g in legacy.get("gates", [])]}
    legacy["schema_version"] = "ds-lite.autonomy-contract.v1"
    output.mkdir(parents=True, exist_ok=True)
    # Pass the normalized adapter contract in memory so the v2 runner does not
    # leave an internal contract file inside the user-visible run directory.
    result = _load_v1_controller().run(root, legacy, output, resume=resume)
    result["schema_version"] = SUMMARY_SCHEMA
    result["terminal_policy"] = normalized["terminal_policy"]
    result["release_authorized"] = False
    if result.get("status") == "completed":
        if normalized["terminal_policy"] == "release":
            result["next_action"] = "formal-release-gate"
        elif normalized["terminal_policy"] == "handoff":
            result["next_action"] = "handoff"
        else:
            result["next_action"] = "final-report"
    else:
        result["next_action"] = result.get("next_action", "resume-independent-gate")
    summary_path = output / "summary-v2.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


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
