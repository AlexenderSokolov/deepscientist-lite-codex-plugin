#!/usr/bin/env python3
"""Cross-domain Evaluation Framework for DS Lite v6.

Uses real effects to decide which v6 mechanisms to release, preserving
no-go/partial outcomes. Generates decision.json with per-mechanism
release|shadow|revise|reject verdicts.

Schema: ds-lite.v6-evaluation.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

EVALUATION_SCHEMA = "ds-lite.v6-evaluation.v1"
DECISION_SCHEMA = "ds-lite.v6-decision.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

RELEASE_DECISIONS = frozenset({
    "release", "shadow", "revise", "reject",
})

EVALUATION_STATUSES = frozenset({
    "draft", "running", "completed", "failed",
})

TASK_DOMAINS = frozenset({
    "finance", "engineering", "algorithm", "systematic-review",
    "wet-lab", "social-science", "cross-disciplinary",
})

EVALUATION_PHASES = frozenset({
    "B0-condition-freeze", "B1-deterministic-fixtures",
    "B2-pilot", "B3-confirmatory-threshold-freeze",
    "B4-confirmatory-run", "B5-analysis", "B6-decision",
})


class EvaluationError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================================
# Evaluation Framework
# ============================================================================

def create_evaluation(
    evaluation_id: str,
    mechanisms: list[str],
    task_domains: list[str],
    conditions: dict[str, Any],
) -> dict[str, Any]:
    """Create a cross-domain evaluation framework.

    Args:
        evaluation_id: Unique evaluation identifier
        mechanisms: List of mechanism IDs to evaluate
        task_domains: List of task domains to test across
        conditions: B0-B4 conditions (frozen model/tool/budget, metrics, exclusions, stop/cost limits)

    Returns:
        Evaluation framework document
    """
    if not ID_RE.fullmatch(evaluation_id):
        raise EvaluationError("evaluation_id must match identifier pattern")

    for domain in task_domains:
        if domain not in TASK_DOMAINS:
            raise EvaluationError(f"task_domain must be one of {sorted(TASK_DOMAINS)}")

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "evaluation_id": evaluation_id,
        "mechanisms": mechanisms,
        "task_domains": task_domains,
        "conditions": {
            "B0_condition_freeze": conditions.get("B0_condition_freeze", {}),
            "B1_deterministic_fixtures": conditions.get("B1_deterministic_fixtures", {}),
            "B2_pilot": conditions.get("B2_pilot", {}),
            "B3_confirmatory_threshold_freeze": conditions.get("B3_confirmatory_threshold_freeze", {}),
            "B4_confirmatory_run": conditions.get("B4_confirmatory_run", {}),
        },
        "phases": list(EVALUATION_PHASES),
        "status": "draft",
        "created_at": _now_iso(),
        "extensions": {},
    }
    return evaluation


def record_phase_result(
    evaluation: dict[str, Any],
    phase: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Record the result of an evaluation phase.

    Args:
        evaluation: Evaluation framework document
        phase: Phase name (must be in EVALUATION_PHASES)
        result: Phase result dict with:
            - status: "pass" | "fail" | "partial" | "blocked"
            - metrics: dict of metric name to value
            - evidence_refs: list of evidence references
            - notes: str

    Returns:
        Updated phase result
    """
    if phase not in EVALUATION_PHASES:
        raise EvaluationError(f"phase must be one of {sorted(EVALUATION_PHASES)}")

    if not isinstance(result, dict):
        raise EvaluationError("result must be an object")

    status = result.get("status", "blocked")
    if status not in {"pass", "fail", "partial", "blocked"}:
        raise EvaluationError("result.status must be pass, fail, partial, or blocked")

    phase_result = {
        "phase": phase,
        "status": status,
        "metrics": result.get("metrics", {}),
        "evidence_refs": result.get("evidence_refs", []),
        "notes": result.get("notes", ""),
        "recorded_at": _now_iso(),
    }

    if "phase_results" not in evaluation:
        evaluation["phase_results"] = {}
    evaluation["phase_results"][phase] = phase_result

    # Update overall status
    all_passed = all(
        evaluation["phase_results"].get(p, {}).get("status") == "pass"
        for p in EVALUATION_PHASES
    )
    any_failed = any(
        evaluation["phase_results"].get(p, {}).get("status") == "fail"
        for p in EVALUATION_PHASES
    )
    if all_passed and len(evaluation.get("phase_results", {})) == len(EVALUATION_PHASES):
        evaluation["status"] = "completed"
    elif any_failed:
        evaluation["status"] = "failed"

    return phase_result


# ============================================================================
# Decision Generation
# ============================================================================

def generate_decision(
    evaluation: dict[str, Any],
    mechanism_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a decision.json from evaluation results.

    For each mechanism, determines: release|shadow|revise|reject

    Decision logic:
    - release: All phases passed across at least 3 structurally different task domains
    - shadow: Some phases passed but not all; mechanism can run in shadow mode
    - revise: Mechanism has design issues that need revision before re-evaluation
    - reject: Mechanism fundamentally does not work or causes harm

    Args:
        evaluation: Evaluation framework document with phase_results
        mechanism_results: Optional per-mechanism results override

    Returns:
        Decision document with per-mechanism verdicts
    """
    phase_results = evaluation.get("phase_results", {})
    mechanisms = evaluation.get("mechanisms", [])
    task_domains = evaluation.get("task_domains", [])

    decisions: list[dict[str, Any]] = []

    for mechanism_id in mechanisms:
        # Get mechanism-specific results if available
        mech_results = (mechanism_results or {}).get(mechanism_id, {})

        # Count passed phases
        passed_phases = sum(
            1 for p in EVALUATION_PHASES
            if phase_results.get(p, {}).get("status") == "pass"
        )

        # Count failed phases
        failed_phases = sum(
            1 for p in EVALUATION_PHASES
            if phase_results.get(p, {}).get("status") == "fail"
        )

        # Count task domains with passing results
        passing_domains = mech_results.get("passing_domains", len(task_domains))

        # Determine decision
        if passed_phases == len(EVALUATION_PHASES) and passing_domains >= 3:
            decision = "release"
            rationale = "All phases passed across sufficient task domains"
        elif failed_phases > 0 and passed_phases < len(EVALUATION_PHASES) // 2:
            decision = "reject"
            rationale = f"Too many failed phases ({failed_phases})"
        elif passed_phases >= len(EVALUATION_PHASES) // 2:
            decision = "shadow"
            rationale = "Sufficient phases passed for shadow mode"
        else:
            decision = "revise"
            rationale = "Mechanism needs revision before re-evaluation"

        # Collect evidence digests
        evidence_digests = []
        for p in EVALUATION_PHASES:
            pr = phase_results.get(p, {})
            if pr.get("evidence_refs"):
                evidence_digests.extend(pr["evidence_refs"])

        decisions.append({
            "mechanism_id": mechanism_id,
            "decision": decision,
            "rationale": rationale,
            "passed_phases": passed_phases,
            "failed_phases": failed_phases,
            "total_phases": len(EVALUATION_PHASES),
            "passing_domains": passing_domains,
            "evidence_digests": evidence_digests,
            "unmet_gates": mech_results.get("unmet_gates", []),
        })

    decision_doc = {
        "schema_version": DECISION_SCHEMA,
        "evaluation_id": evaluation.get("evaluation_id", ""),
        "decisions": decisions,
        "summary": {
            "total_mechanisms": len(mechanisms),
            "released": sum(1 for d in decisions if d["decision"] == "release"),
            "shadowed": sum(1 for d in decisions if d["decision"] == "shadow"),
            "revised": sum(1 for d in decisions if d["decision"] == "revise"),
            "rejected": sum(1 for d in decisions if d["decision"] == "reject"),
        },
        "generated_at": _now_iso(),
        "extensions": {},
    }

    # Compute decision digest
    decision_doc["decision_digest"] = _digest({
        "evaluation_id": decision_doc["evaluation_id"],
        "decisions": decisions,
    })

    return decision_doc


# ============================================================================
# Evaluation Validation
# ============================================================================

def validate_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Validate an evaluation framework document."""
    if not isinstance(evaluation, dict):
        raise EvaluationError("evaluation must be an object")

    if evaluation.get("schema_version") != EVALUATION_SCHEMA:
        raise EvaluationError(f"schema_version must be {EVALUATION_SCHEMA}")

    rule_ids: list[str] = []
    verdict = "pass"

    # Check: at least 3 task domains
    task_domains = evaluation.get("task_domains", [])
    if len(task_domains) < 3:
        rule_ids.append("insufficient_task_domains")
        verdict = "blocked"

    # Check: at least one mechanism
    mechanisms = evaluation.get("mechanisms", [])
    if len(mechanisms) == 0:
        rule_ids.append("no_mechanisms_to_evaluate")
        verdict = "blocked"

    # Check: all phases present
    phases = evaluation.get("phases", [])
    if set(phases) != EVALUATION_PHASES:
        rule_ids.append("missing_evaluation_phases")
        verdict = "blocked"

    # Check: B0 conditions frozen
    conditions = evaluation.get("conditions", {})
    b0 = conditions.get("B0_condition_freeze", {})
    if not b0.get("frozen", False):
        rule_ids.append("B0_conditions_not_frozen")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
    }
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Cross-domain Evaluation Framework for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--evaluation-id", required=True)
    create_parser.add_argument("--mechanisms", required=True, help="Comma-separated mechanism IDs")
    create_parser.add_argument("--domains", required=True, help="Comma-separated task domains")
    create_parser.add_argument("--conditions", required=True, help="Path to conditions JSON")

    decision_parser = sub.add_parser("decision")
    decision_parser.add_argument("--evaluation", required=True, help="Path to evaluation JSON")

    args = parser.parse_args()
    try:
        if args.command == "create":
            conditions = json.loads(open(args.conditions, encoding="utf-8").read())
            result = create_evaluation(
                args.evaluation_id,
                args.mechanisms.split(","),
                args.domains.split(","),
                conditions,
            )
        elif args.command == "decision":
            evaluation = json.loads(open(args.evaluation, encoding="utf-8").read())
            result = generate_decision(evaluation)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (EvaluationError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())