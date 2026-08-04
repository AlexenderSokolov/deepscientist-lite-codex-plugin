#!/usr/bin/env python3
"""Mission Handoff Quality Protocol for DS Lite v6.

Implements six-stage Handoff (offer -> accept -> execute -> return ->
integrate -> close), seven quality gates G0-G6, Quality Contract, and
Review Package.

Schema: ds-lite.mission-handoff-quality.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

PROTOCOL_SCHEMA = "ds-lite.mission-handoff-quality.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

HANDOFF_PHASES = frozenset({
    "offer", "accept", "execute", "return", "integrate", "close",
})

MISSION_STATUSES = frozenset({
    "offered", "accepted", "executing", "returned", "integrated", "closed",
    "rejected", "failed",
})

QUALITY_GATES = frozenset({
    "G0-identity", "G1-requirements", "G2-security-privacy",
    "G3-license-supply-chain", "G4-engineering-quality",
    "G5-scientific-method", "G6-release-readiness",
})

GATE_STATUSES = frozenset({
    "pass", "fail", "unknown", "not-run", "waived",
})

RISK_LEVELS = frozenset({"Q0", "Q1", "Q2", "Q3", "Q4"})

REVIEW_STATUSES = frozenset({
    "draft", "in-review", "approved", "rejected", "superseded",
})

FINDING_SEVERITIES = frozenset({
    "blocker", "critical", "major", "minor", "info",
})

FINDING_STATUSES = frozenset({
    "open", "addressed", "wont-fix", "false-positive", "deferred",
})


class HandoffQualityError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================================
# Mission Order Validation
# ============================================================================

def validate_mission_order(document: Any) -> dict[str, Any]:
    """Validate a mission order document."""
    if not isinstance(document, dict):
        raise HandoffQualityError("mission order must be an object")

    if document.get("schema_version") != PROTOCOL_SCHEMA:
        raise HandoffQualityError(f"schema_version must be {PROTOCOL_SCHEMA}")

    required = {
        "schema_version", "mission_id", "project_id", "objective",
        "non_goals", "owner_id", "budget", "acceptance_criteria",
        "stop_conditions", "authority_digest", "status", "created_at",
        "extensions",
    }
    missing = required - set(document.keys())
    if missing:
        raise HandoffQualityError(f"missing required fields: {sorted(missing)}")

    rule_ids: list[str] = []
    verdict = "pass"

    if not ID_RE.fullmatch(document["mission_id"]):
        rule_ids.append("invalid_mission_id")
        verdict = "blocked"

    if not isinstance(document["objective"], str) or not document["objective"].strip():
        rule_ids.append("empty_objective")
        verdict = "blocked"

    if not isinstance(document["acceptance_criteria"], list) or len(document["acceptance_criteria"]) == 0:
        rule_ids.append("empty_acceptance_criteria")
        verdict = "blocked"

    if not isinstance(document["stop_conditions"], list) or len(document["stop_conditions"]) == 0:
        rule_ids.append("empty_stop_conditions")
        verdict = "blocked"

    if not isinstance(document["authority_digest"], str) or not document["authority_digest"].strip():
        rule_ids.append("missing_authority_digest")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "mission_digest": _digest({
            "mission_id": document["mission_id"],
            "project_id": document.get("project_id", ""),
            "objective": document["objective"],
        }),
    }
    return result


# ============================================================================
# Handoff Phase Validation
# ============================================================================

def validate_handoff_phase(document: dict[str, Any], phase: str) -> dict[str, Any]:
    """Validate a handoff phase transition.

    Key rule: returned does not equal integrated.
    """
    if phase not in HANDOFF_PHASES:
        raise HandoffQualityError(f"phase must be one of {sorted(HANDOFF_PHASES)}")

    rule_ids: list[str] = []
    verdict = "pass"

    current_status = document.get("status", "")
    mission_id = document.get("mission_id", "unknown")

    # Rule: returned does not equal integrated
    if phase == "integrate" and current_status == "returned":
        # This is the correct transition: returned -> integrated
        pass
    elif phase == "close" and current_status != "integrated":
        # Cannot close without integration
        rule_ids.append("cannot_close_without_integration")
        verdict = "blocked"

    # Rule: cannot skip phases
    if phase == "execute" and current_status not in ("accepted", "executing"):
        rule_ids.append("cannot_execute_without_acceptance")
        verdict = "blocked"

    if phase == "return" and current_status not in ("executing", "returned"):
        rule_ids.append("cannot_return_without_execution")
        verdict = "blocked"

    if phase == "integrate" and current_status not in ("returned", "integrated"):
        rule_ids.append("cannot_integrate_without_return")
        verdict = "blocked"

    # Rule: rejected missions cannot proceed
    if current_status == "rejected" and phase != "close":
        rule_ids.append("rejected_mission_cannot_proceed")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "phase": phase,
        "mission_id": mission_id,
    }
    return result


# ============================================================================
# Quality Contract Validation
# ============================================================================

def validate_quality_contract(document: Any) -> dict[str, Any]:
    """Validate a quality contract document.

    Key rule: unknown or not-run gates cannot aggregate into pass.
    """
    if not isinstance(document, dict):
        raise HandoffQualityError("quality contract must be an object")

    if document.get("schema_version") != PROTOCOL_SCHEMA:
        raise HandoffQualityError(f"schema_version must be {PROTOCOL_SCHEMA}")

    rule_ids: list[str] = []
    verdict = "pass"

    gates = document.get("gates", {})
    if not isinstance(gates, dict):
        raise HandoffQualityError("gates must be an object")

    # Check each gate
    for gate_id, gate_status in gates.items():
        if gate_id not in QUALITY_GATES:
            rule_ids.append(f"unknown_gate_{gate_id}")
            verdict = "blocked"
            continue

        if gate_status not in GATE_STATUSES:
            rule_ids.append(f"invalid_gate_status_{gate_id}")
            verdict = "blocked"
            continue

        # Rule: unknown or not-run gates cannot aggregate into pass
        if gate_status in ("unknown", "not-run"):
            rule_ids.append(f"gate_{gate_id}_not_resolved")
            verdict = "blocked"

        if gate_status == "fail":
            rule_ids.append(f"gate_{gate_id}_failed")
            verdict = "blocked"

    # Rule: all required gates must be present
    missing_gates = QUALITY_GATES - set(gates.keys())
    if missing_gates:
        rule_ids.append(f"missing_gates_{sorted(missing_gates)}")
        verdict = "blocked"

    # Check risk level
    risk_level = document.get("risk_level", "Q0")
    if risk_level not in RISK_LEVELS:
        rule_ids.append("invalid_risk_level")
        verdict = "blocked"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "contract_digest": _digest({
            "gates": gates,
            "risk_level": risk_level,
        }),
    }
    return result


# ============================================================================
# Review Package
# ============================================================================

def create_review_package(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a review package from findings.

    The review package can be machine-aggregated and preserves disagreements.
    """
    if not isinstance(findings, list):
        raise HandoffQualityError("findings must be a list")

    validated_findings: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if not isinstance(finding.get("finding_id"), str) or not finding.get("finding_id"):
            continue
        if finding.get("severity") not in FINDING_SEVERITIES:
            continue
        if finding.get("status") not in FINDING_STATUSES:
            continue
        validated_findings.append(finding)

    # Aggregate findings
    severity_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for f in validated_findings:
        sev = f.get("severity", "info")
        stat = f.get("status", "open")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        status_counts[stat] = status_counts.get(stat, 0) + 1

    # Determine overall verdict
    has_blocker = any(f.get("severity") == "blocker" and f.get("status") == "open" for f in validated_findings)
    has_critical = any(f.get("severity") == "critical" and f.get("status") == "open" for f in validated_findings)

    if has_blocker:
        overall = "blocked"
    elif has_critical:
        overall = "blocked"
    else:
        overall = "pass"

    package = {
        "schema_version": PROTOCOL_SCHEMA,
        "review_id": f"review-{_now_iso()}",
        "findings": validated_findings,
        "aggregation": {
            "total_findings": len(validated_findings),
            "severity_counts": severity_counts,
            "status_counts": status_counts,
            "overall_verdict": overall,
        },
        "created_at": _now_iso(),
        "extensions": {},
    }
    return package


def create_mission_order(
    mission_id: str,
    project_id: str,
    objective: str,
    non_goals: list[str],
    owner_id: str,
    budget: dict[str, Any],
    acceptance_criteria: list[dict[str, Any]],
    stop_conditions: list[str],
    authority_digest: str,
) -> dict[str, Any]:
    """Create a mission order document."""
    if not ID_RE.fullmatch(mission_id):
        raise HandoffQualityError("mission_id must match identifier pattern")
    if not ID_RE.fullmatch(project_id):
        raise HandoffQualityError("project_id must match identifier pattern")

    now = _now_iso()
    document = {
        "schema_version": PROTOCOL_SCHEMA,
        "mission_id": mission_id,
        "project_id": project_id,
        "objective": objective,
        "non_goals": non_goals,
        "owner_id": owner_id,
        "budget": budget,
        "acceptance_criteria": acceptance_criteria,
        "stop_conditions": stop_conditions,
        "authority_digest": authority_digest,
        "status": "offered",
        "created_at": now,
        "extensions": {},
    }
    return document


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Mission Handoff Quality Protocol for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_mission_parser = sub.add_parser("validate-mission")
    validate_mission_parser.add_argument("--document", required=True)

    validate_handoff_parser = sub.add_parser("validate-handoff")
    validate_handoff_parser.add_argument("--document", required=True)
    validate_handoff_parser.add_argument("--phase", required=True)

    validate_quality_parser = sub.add_parser("validate-quality")
    validate_quality_parser.add_argument("--document", required=True)

    args = parser.parse_args()
    try:
        if args.command == "validate-mission":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_mission_order(doc)
        elif args.command == "validate-handoff":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_handoff_phase(doc, args.phase)
        elif args.command == "validate-quality":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_quality_contract(doc)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (HandoffQualityError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())