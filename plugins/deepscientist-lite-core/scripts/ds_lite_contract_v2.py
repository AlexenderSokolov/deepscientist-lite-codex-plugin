#!/usr/bin/env python3
"""Experiment Contract v2 for DS Lite v6.

Embeds Task Assessment/Answerability Gate. Establishes domain-neutral
scientific integrity kernel that blocks unanswerable tasks, protocol drift,
role contamination, and incomparable runs.

Schema: ds-lite.experiment-contract.v2
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

CONTRACT_SCHEMA = "ds-lite.experiment-contract.v2"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

CONTRACT_STATUSES = frozenset({
    "draft", "assessed", "active", "completed", "failed", "superseded",
})

FIDELITY_LEVELS = frozenset({
    "L0-static", "L1-connectivity", "L2-diagnostic",
    "L3-pilot", "L4-confirmatory",
})

COMPARISON_DOMAINS = frozenset({
    "same-dataset", "same-metric", "same-baseline",
    "cross-dataset", "cross-metric", "none",
})

ROLE_STATUSES = frozenset({
    "protected", "open", "contaminated", "unknown",
})


class ContractError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_experiment_contract_v2(
    document: Any,
    profile_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an experiment contract v2 document.

    Returns a result dict with:
    - verdict: "pass" | "blocked" | "warning"
    - rule_ids: list of triggered rule IDs
    - contract_digest: str
    """
    if not isinstance(document, dict):
        raise ContractError("contract must be an object")

    if document.get("schema_version") != CONTRACT_SCHEMA:
        raise ContractError(f"schema_version must be {CONTRACT_SCHEMA}")

    required_fields = {
        "schema_version", "contract_id", "work_unit_id", "mission_ref",
        "objective", "non_goals", "input_snapshot", "owner_id",
        "budget", "acceptance_criteria", "task_assessment_ref",
        "fidelity_level", "comparison_domain", "role_status",
        "evaluator", "baseline", "stop_conditions",
        "status", "revision", "created_at", "updated_at", "extensions",
    }

    missing = required_fields - set(document.keys())
    if missing:
        raise ContractError(f"missing required fields: {sorted(missing)}")

    contract_id = document["contract_id"]
    if not isinstance(contract_id, str) or not ID_RE.fullmatch(contract_id):
        raise ContractError("contract_id must match identifier pattern")

    work_unit_id = document["work_unit_id"]
    if not isinstance(work_unit_id, str) or not ID_RE.fullmatch(work_unit_id):
        raise ContractError("work_unit_id must match identifier pattern")

    objective = document["objective"]
    if not isinstance(objective, str) or not objective.strip():
        raise ContractError("objective must be a non-empty string")

    non_goals = document["non_goals"]
    if not isinstance(non_goals, list):
        raise ContractError("non_goals must be a list")

    budget = document["budget"]
    if not isinstance(budget, dict):
        raise ContractError("budget must be an object")

    acceptance_criteria = document["acceptance_criteria"]
    if not isinstance(acceptance_criteria, list) or len(acceptance_criteria) == 0:
        raise ContractError("acceptance_criteria must be a non-empty list")

    fidelity_level = document["fidelity_level"]
    if fidelity_level not in FIDELITY_LEVELS:
        raise ContractError(f"fidelity_level must be one of {sorted(FIDELITY_LEVELS)}")

    comparison_domain = document["comparison_domain"]
    if comparison_domain not in COMPARISON_DOMAINS:
        raise ContractError(f"comparison_domain must be one of {sorted(COMPARISON_DOMAINS)}")

    role_status = document["role_status"]
    if role_status not in ROLE_STATUSES:
        raise ContractError(f"role_status must be one of {sorted(ROLE_STATUSES)}")

    status = document["status"]
    if status not in CONTRACT_STATUSES:
        raise ContractError(f"status must be one of {sorted(CONTRACT_STATUSES)}")

    # Compute contract digest
    digest_data = {
        "contract_id": contract_id,
        "work_unit_id": work_unit_id,
        "objective": objective,
        "fidelity_level": fidelity_level,
        "comparison_domain": comparison_domain,
        "revision": document["revision"],
    }
    contract_digest = _digest(digest_data)

    # Apply validation rules
    rule_ids: list[str] = []
    verdict = "pass"

    # Rule: contract must have task assessment reference
    task_assessment_ref = document.get("task_assessment_ref")
    if not task_assessment_ref or not isinstance(task_assessment_ref, str):
        rule_ids.append("missing_task_assessment")
        verdict = "blocked"

    # Rule: contaminated roles must be blocked
    if role_status == "contaminated":
        rule_ids.append("contaminated_role")
        verdict = "blocked"

    # Rule: L4-confirmatory requires protected roles
    if fidelity_level == "L4-confirmatory" and role_status != "protected":
        rule_ids.append("confirmatory_requires_protected_role")
        verdict = "blocked"

    # Rule: budget must have max_tokens or max_seconds
    if "max_tokens" not in budget and "max_seconds" not in budget:
        rule_ids.append("missing_budget_limit")
        if verdict == "pass":
            verdict = "warning"

    # Rule: stop_conditions must be non-empty
    stop_conditions = document.get("stop_conditions", [])
    if not isinstance(stop_conditions, list) or len(stop_conditions) == 0:
        rule_ids.append("empty_stop_conditions")
        verdict = "blocked"

    # Rule: evaluator must be specified
    evaluator = document.get("evaluator")
    if not evaluator or not isinstance(evaluator, dict):
        rule_ids.append("missing_evaluator")
        verdict = "blocked"

    # Rule: baseline must be specified for comparison_domain != none
    baseline = document.get("baseline")
    if comparison_domain != "none" and (not baseline or not isinstance(baseline, dict)):
        rule_ids.append("missing_baseline_for_comparison")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "contract_digest": contract_digest,
    }
    return result


def validate_contract_revision(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate that a contract revision is valid.

    Checks:
    - revision number must increase
    - scientific/authorization boundary changes require new generation
    - metric changes without revision are blocked
    """
    rule_ids: list[str] = []
    verdict = "pass"

    base_revision = base.get("revision", 0)
    candidate_revision = candidate.get("revision", 0)

    if candidate_revision <= base_revision:
        rule_ids.append("revision_must_increase")
        verdict = "blocked"

    # Check if metric changed without revision
    base_metrics = json.dumps(base.get("acceptance_criteria", []), sort_keys=True)
    candidate_metrics = json.dumps(candidate.get("acceptance_criteria", []), sort_keys=True)
    if base_metrics != candidate_metrics and candidate_revision <= base_revision:
        rule_ids.append("metric_change_requires_new_revision")
        verdict = "blocked"

    # Check if objective changed
    if base.get("objective") != candidate.get("objective"):
        if candidate_revision <= base_revision + 1:
            rule_ids.append("objective_change_requires_major_revision")
            verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "domain_status": "protocol_authority_conflict" if verdict == "blocked" else "ok",
    }
    return result


def read_v1_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Read a v1 contract and return a LegacyContractView."""
    if not isinstance(document, dict):
        raise ContractError("contract must be an object")

    return {
        "schema_version": "ds-lite.experiment-contract.v1-legacy",
        "contract_id": document.get("contract_id", "unknown"),
        "objective": document.get("objective", ""),
        "non_goals": document.get("non_goals", []),
        "budget": document.get("budget", {}),
        "acceptance_criteria": document.get("acceptance_criteria", []),
        "status": document.get("status", "unknown"),
        "revision": document.get("revision", 0),
        "legacy_fields": {k: v for k, v in document.items()
                         if k not in {"contract_id", "objective", "non_goals",
                                      "budget", "acceptance_criteria", "status", "revision"}},
    }


def create_contract(
    contract_id: str,
    work_unit_id: str,
    mission_ref: str,
    objective: str,
    non_goals: list[str],
    input_snapshot: dict[str, Any],
    owner_id: str,
    budget: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    task_assessment_ref: str,
    fidelity_level: str,
    comparison_domain: str,
    role_status: str,
    evaluator: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    stop_conditions: list[str] | None = None,
) -> dict[str, Any]:
    """Create an experiment contract v2 document."""
    if not ID_RE.fullmatch(contract_id):
        raise ContractError("contract_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise ContractError("work_unit_id must match identifier pattern")
    if fidelity_level not in FIDELITY_LEVELS:
        raise ContractError(f"fidelity_level must be one of {sorted(FIDELITY_LEVELS)}")
    if comparison_domain not in COMPARISON_DOMAINS:
        raise ContractError(f"comparison_domain must be one of {sorted(COMPARISON_DOMAINS)}")
    if role_status not in ROLE_STATUSES:
        raise ContractError(f"role_status must be one of {sorted(ROLE_STATUSES)}")

    now = _now_iso()
    document = {
        "schema_version": CONTRACT_SCHEMA,
        "contract_id": contract_id,
        "work_unit_id": work_unit_id,
        "mission_ref": mission_ref,
        "objective": objective,
        "non_goals": non_goals,
        "input_snapshot": input_snapshot,
        "owner_id": owner_id,
        "budget": budget,
        "acceptance_criteria": acceptance_criteria,
        "task_assessment_ref": task_assessment_ref,
        "fidelity_level": fidelity_level,
        "comparison_domain": comparison_domain,
        "role_status": role_status,
        "evaluator": evaluator,
        "baseline": baseline or {},
        "stop_conditions": stop_conditions or [],
        "status": "draft",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
        "extensions": {},
    }
    return document


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Experiment Contract v2 for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--document", required=True, help="Path to contract JSON")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_experiment_contract_v2(doc)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        return 1
    except (ContractError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())