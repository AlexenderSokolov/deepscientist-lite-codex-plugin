#!/usr/bin/env python3
"""Score sanitized plugin-applicability and user-explanation assessments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any


APPLICABILITY = {"applicable", "needs-intake", "not-applicable"}
STATUSES = {"pass", "fail", "not-run"}
FIELDS = {
    "expected_applicability",
    "claimed_applicability",
    "expected_skill",
    "claimed_skill",
    "evidence_refs",
    "observed_refs",
    "action",
    "stop_condition",
    "verification",
    "unverified",
    "next_action",
    "decision_needed",
    "artifact_refs",
    "unsupported_completion_claims",
    "status",
}
VERIFICATION_FIELDS = {"command", "status", "ref"}
FORBIDDEN = {
    "prompt",
    "raw_jsonl",
    "stderr",
    "secret",
    "token",
    "api_key",
    "credential",
    "hidden_reasoning",
    "chain_of_thought",
    "environment_variables",
}


class ExplainabilityError(ValueError):
    pass


def _scan_forbidden(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN:
                raise ExplainabilityError(f"forbidden sensitive field: {path + '.' if path else ''}{key}")
            _scan_forbidden(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]")


def _ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ExplainabilityError(f"{label} must be a project-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ExplainabilityError(f"{label} must not escape the project root")
    return value


def _refs(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ExplainabilityError(f"{label} must be a list of relative refs")
    refs = [_ref(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(refs) != len(set(refs)):
        raise ExplainabilityError(f"{label} contains duplicate refs")
    return refs


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ExplainabilityError(f"{label} must be a string")
    return value.strip()


def assess_case(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ExplainabilityError("assessment must be an object")
    unknown = set(payload) - FIELDS
    missing = FIELDS - set(payload)
    if missing:
        raise ExplainabilityError(f"assessment missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ExplainabilityError(f"assessment has unsupported fields: {', '.join(sorted(unknown))}")
    _scan_forbidden(payload)

    expected = payload["expected_applicability"]
    claimed = payload["claimed_applicability"]
    if expected not in APPLICABILITY or claimed not in APPLICABILITY:
        raise ExplainabilityError("applicability must be applicable, needs-intake, or not-applicable")
    expected_skill = _text(payload["expected_skill"], "expected_skill")
    claimed_skill = _text(payload["claimed_skill"], "claimed_skill")
    evidence_refs = _refs(payload["evidence_refs"], "evidence_refs")
    observed_refs = _refs(payload["observed_refs"], "observed_refs")
    action = _text(payload["action"], "action")
    stop_condition = _text(payload["stop_condition"], "stop_condition")
    unverified = payload["unverified"]
    if not isinstance(unverified, list) or not all(isinstance(item, str) and item.strip() for item in unverified):
        raise ExplainabilityError("unverified must be a list of non-empty strings")
    next_action = _text(payload["next_action"], "next_action")
    decision_needed = _text(payload["decision_needed"], "decision_needed")
    artifact_refs = _refs(payload["artifact_refs"], "artifact_refs")
    if not isinstance(payload["unsupported_completion_claims"], int) or payload["unsupported_completion_claims"] < 0:
        raise ExplainabilityError("unsupported_completion_claims must be a non-negative integer")
    status = payload["status"]
    if status not in {"completed", "partial", "blocked", "failed", "ambiguous"}:
        raise ExplainabilityError("status must be a terminal sanitized case status")

    verification = payload["verification"]
    if not isinstance(verification, list):
        raise ExplainabilityError("verification must be a list")
    valid_verification = True
    for index, item in enumerate(verification):
        if not isinstance(item, dict) or set(item) != VERIFICATION_FIELDS:
            raise ExplainabilityError(f"verification[{index}] must contain command, status, and ref")
        if not _text(item["command"], f"verification[{index}].command"):
            raise ExplainabilityError(f"verification[{index}].command must not be empty")
        if item["status"] not in STATUSES:
            raise ExplainabilityError(f"verification[{index}].status is invalid")
        _ref(item["ref"], f"verification[{index}].ref")
        valid_verification = valid_verification and item["status"] in STATUSES

    applicability_accuracy = int(expected == claimed)
    false_positive = int(expected == "not-applicable" and claimed == "applicable")
    false_negative = int(expected == "applicable" and claimed == "not-applicable")
    rationale_evidence_coverage = sum(
        (
            bool(evidence_refs),
            bool(observed_refs) and set(observed_refs).issubset(set(evidence_refs)),
            bool(expected_skill == claimed_skill and (claimed_skill or expected == "not-applicable")),
            bool(action and stop_condition),
        )
    )
    verification_traceability = sum(
        (
            bool(verification),
            valid_verification and bool(verification),
            all(item["status"] != "not-run" for item in verification) if verification else False,
        )
    )
    user_decision_clarity = sum((bool(next_action), bool(decision_needed), bool(unverified)))
    unsupported = payload["unsupported_completion_claims"]
    if status == "completed" and (
        applicability_accuracy == 0
        or not verification
        or not action
        or not stop_condition
        or not evidence_refs
    ):
        unsupported += 1
    artifact_recoverability = int(bool(artifact_refs) and all(ref.startswith("research/artifacts/") for ref in artifact_refs))
    return {
        "applicability_accuracy": applicability_accuracy,
        "activation_false_positive": false_positive,
        "activation_false_negative": false_negative,
        "rationale_evidence_coverage": rationale_evidence_coverage,
        "verification_traceability": verification_traceability,
        "user_decision_clarity": user_decision_clarity,
        "unsupported_completion_count": unsupported,
        "artifact_recoverability": artifact_recoverability,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a sanitized DS Lite explainability assessment")
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result = assess_case(payload)
    except (OSError, json.JSONDecodeError, ExplainabilityError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
