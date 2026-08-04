#!/usr/bin/env python3
"""Task Assessment / Answerability Gate for DS Lite v6.

Determines what a task can answer now, what evidence level is reachable,
and what cannot be claimed even if successful. Embedded in Experiment
Contract v2, not a separate task contract.

Schema: ds-lite.task-assessment.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

ASSESSMENT_SCHEMA = "ds-lite.task-assessment.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

EVIDENCE_LEVELS = frozenset({
    "none", "anecdotal", "exploratory", "diagnostic", "pilot", "confirmatory",
})

ANSWERABILITY_STATUSES = frozenset({
    "answerable", "partially-answerable", "not-answerable", "needs-human",
})

TASK_KINDS = frozenset({
    "diagnostic", "exploratory", "pilot", "confirmatory",
    "systematic-review", "engineering", "replication",
})

RESOURCE_STATUSES = frozenset({
    "available", "partial", "missing", "unknown",
})

PERMISSION_STATUSES = frozenset({
    "granted", "partial", "denied", "unknown",
})


class AssessmentError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_task_assessment(document: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a task assessment document.

    Returns a result dict with:
    - verdict: "pass" | "blocked" | "warning"
    - rule_ids: list of triggered rule IDs
    - reachable_evidence_level: str
    - answerability_status: str
    - assessment_digest: str
    """
    if not isinstance(document, dict):
        raise AssessmentError("assessment must be an object")

    if document.get("schema_version") != ASSESSMENT_SCHEMA:
        raise AssessmentError(f"schema_version must be {ASSESSMENT_SCHEMA}")

    required_fields = {
        "schema_version", "assessment_id", "work_unit_id", "task_kind",
        "question", "input_roles", "resources", "permissions",
        "reachable_evidence_level", "answerability_status",
        "non_claims", "preconditions", "created_at", "extensions",
    }

    missing = required_fields - set(document.keys())
    if missing:
        raise AssessmentError(f"missing required fields: {sorted(missing)}")

    assessment_id = document["assessment_id"]
    if not isinstance(assessment_id, str) or not ID_RE.fullmatch(assessment_id):
        raise AssessmentError("assessment_id must match identifier pattern")

    work_unit_id = document["work_unit_id"]
    if not isinstance(work_unit_id, str) or not ID_RE.fullmatch(work_unit_id):
        raise AssessmentError("work_unit_id must match identifier pattern")

    task_kind = document["task_kind"]
    if task_kind not in TASK_KINDS:
        raise AssessmentError(f"task_kind must be one of {sorted(TASK_KINDS)}")

    question = document["question"]
    if not isinstance(question, str) or not question.strip():
        raise AssessmentError("question must be a non-empty string")

    input_roles = document["input_roles"]
    if not isinstance(input_roles, list) or len(input_roles) == 0:
        raise AssessmentError("input_roles must be a non-empty list")

    resources = document["resources"]
    if not isinstance(resources, dict):
        raise AssessmentError("resources must be an object")

    permissions = document["permissions"]
    if not isinstance(permissions, dict):
        raise AssessmentError("permissions must be an object")

    reachable_evidence_level = document["reachable_evidence_level"]
    if reachable_evidence_level not in EVIDENCE_LEVELS:
        raise AssessmentError(f"reachable_evidence_level must be one of {sorted(EVIDENCE_LEVELS)}")

    answerability_status = document["answerability_status"]
    if answerability_status not in ANSWERABILITY_STATUSES:
        raise AssessmentError(f"answerability_status must be one of {sorted(ANSWERABILITY_STATUSES)}")

    non_claims = document["non_claims"]
    if not isinstance(non_claims, list):
        raise AssessmentError("non_claims must be a list")

    preconditions = document["preconditions"]
    if not isinstance(preconditions, list):
        raise AssessmentError("preconditions must be a list")

    # Compute assessment digest
    digest_data = {
        "assessment_id": assessment_id,
        "work_unit_id": work_unit_id,
        "task_kind": task_kind,
        "question": question,
        "reachable_evidence_level": reachable_evidence_level,
        "answerability_status": answerability_status,
    }
    assessment_digest = _digest(digest_data)

    # Apply validation rules
    rule_ids: list[str] = []
    verdict = "pass"

    # Rule: diagnostic task cannot enter confirmatory
    if task_kind == "diagnostic" and reachable_evidence_level == "confirmatory":
        rule_ids.append("diagnostic_cannot_be_confirmatory")
        verdict = "blocked"

    # Rule: not-answerable tasks must be blocked
    if answerability_status == "not-answerable":
        rule_ids.append("not_answerable_blocked")
        verdict = "blocked"

    # Rule: needs-human tasks must be blocked
    if answerability_status == "needs-human":
        rule_ids.append("needs_human_blocked")
        verdict = "blocked"

    # Rule: missing resources must trigger warning
    resource_statuses = list(resources.values())
    if any(s == "missing" for s in resource_statuses if isinstance(s, str)):
        rule_ids.append("missing_resources")
        if verdict == "pass":
            verdict = "warning"

    # Rule: denied permissions must trigger blocked
    permission_statuses = list(permissions.values())
    if any(s == "denied" for s in permission_statuses if isinstance(s, str)):
        rule_ids.append("denied_permissions")
        verdict = "blocked"

    # Rule: unknown permissions must trigger warning
    if any(s == "unknown" for s in permission_statuses if isinstance(s, str)):
        rule_ids.append("unknown_permissions")
        if verdict == "pass":
            verdict = "warning"

    # Rule: non_claims must be non-empty for confirmatory tasks
    if task_kind == "confirmatory" and len(non_claims) == 0:
        rule_ids.append("confirmatory_requires_non_claims")
        verdict = "blocked"

    # Rule: preconditions must be non-empty
    if len(preconditions) == 0:
        rule_ids.append("empty_preconditions")
        if verdict == "pass":
            verdict = "warning"

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "reachable_evidence_level": reachable_evidence_level,
        "answerability_status": answerability_status,
        "assessment_digest": assessment_digest,
    }
    return result


def create_assessment(
    assessment_id: str,
    work_unit_id: str,
    task_kind: str,
    question: str,
    input_roles: list[str],
    resources: dict[str, str],
    permissions: dict[str, str],
    reachable_evidence_level: str,
    answerability_status: str,
    non_claims: list[str] | None = None,
    preconditions: list[str] | None = None,
) -> dict[str, Any]:
    """Create a task assessment document."""
    if not ID_RE.fullmatch(assessment_id):
        raise AssessmentError("assessment_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise AssessmentError("work_unit_id must match identifier pattern")
    if task_kind not in TASK_KINDS:
        raise AssessmentError(f"task_kind must be one of {sorted(TASK_KINDS)}")
    if reachable_evidence_level not in EVIDENCE_LEVELS:
        raise AssessmentError(f"reachable_evidence_level must be one of {sorted(EVIDENCE_LEVELS)}")
    if answerability_status not in ANSWERABILITY_STATUSES:
        raise AssessmentError(f"answerability_status must be one of {sorted(ANSWERABILITY_STATUSES)}")

    document = {
        "schema_version": ASSESSMENT_SCHEMA,
        "assessment_id": assessment_id,
        "work_unit_id": work_unit_id,
        "task_kind": task_kind,
        "question": question,
        "input_roles": input_roles,
        "resources": resources,
        "permissions": permissions,
        "reachable_evidence_level": reachable_evidence_level,
        "answerability_status": answerability_status,
        "non_claims": non_claims or [],
        "preconditions": preconditions or [],
        "created_at": _now_iso(),
        "extensions": {},
    }
    return document


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Task Assessment for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--document", required=True, help="Path to assessment JSON")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_task_assessment(doc)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        return 1
    except (AssessmentError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())