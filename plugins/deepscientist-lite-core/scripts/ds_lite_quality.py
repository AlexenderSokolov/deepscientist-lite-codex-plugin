#!/usr/bin/env python3
"""Strict, dependency-free quality-plan and quality-result gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "ds-lite.quality-plan.v1"
RESULT_SCHEMA = "ds-lite.quality-result.v1"
RISKS = {"low", "medium", "high"}


class QualityError(ValueError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualityError(f"quality file unavailable: {exc}") from exc


def validate_plan(payload: Any) -> dict[str, Any]:
    required = {"schema_version", "plan_id", "risk", "requirements", "allowed_paths", "authorization_ref", "metrics", "acceptance", "test_strategy", "rollback", "residual_risks", "extensions"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise QualityError("quality plan fields do not match ds-lite.quality-plan.v1")
    if payload["schema_version"] != PLAN_SCHEMA or payload["risk"] not in RISKS:
        raise QualityError("quality plan schema or risk is invalid")
    for field in ("requirements", "allowed_paths", "metrics", "acceptance", "test_strategy", "residual_risks"):
        if not isinstance(payload[field], list) or not payload[field] or not all(isinstance(value, str) and value.strip() for value in payload[field]):
            raise QualityError(f"quality plan {field} must be a non-empty string list")
    if not isinstance(payload["plan_id"], str) or not payload["plan_id"].strip() or not isinstance(payload["authorization_ref"], str) or not payload["authorization_ref"].strip() or not isinstance(payload["rollback"], str) or not payload["rollback"].strip():
        raise QualityError("quality plan identity, authorization, and rollback are required")
    strategy = {item.lower() for item in payload["test_strategy"]}
    required_by_risk = {"low": {"focused"}, "medium": {"unit", "gherkin", "coverage"}, "high": {"unit", "gherkin", "coverage", "mutation", "fresh-review", "recovery", "security"}}
    missing = sorted(required_by_risk[payload["risk"]] - strategy)
    if missing:
        raise QualityError("quality plan missing required test strategies: " + ", ".join(missing))
    if not isinstance(payload["extensions"], dict):
        raise QualityError("quality plan extensions must be an object")
    return json.loads(json.dumps(payload))


def _passed(value: Any) -> bool:
    return isinstance(value, dict) and value.get("status") == "passed"


def evaluate_result(payload: Any) -> dict[str, Any]:
    required = {"schema_version", "plan_id", "status", "risk", "requirement_trace", "security", "tests", "coverage", "mutation", "recovery", "review", "residual_risks", "extensions"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise QualityError("quality result fields do not match ds-lite.quality-result.v1")
    if payload["schema_version"] != RESULT_SCHEMA or payload["risk"] not in RISKS:
        raise QualityError("quality result schema or risk is invalid")
    trace = payload["requirement_trace"]
    if not isinstance(trace, list) or not trace or any(not isinstance(item, dict) or item.get("status") != "passed" or not isinstance(item.get("evidence"), list) or not item["evidence"] for item in trace):
        raise QualityError("every requirement must have passed evidence")
    if not _passed(payload["tests"]) or not isinstance(payload["tests"].get("commands"), list) or not payload["tests"]["commands"]:
        raise QualityError("passing quality result requires observed test commands")
    if payload["risk"] in {"medium", "high"} and payload["tests"].get("gherkin") != "passed":
        raise QualityError("medium/high-risk result requires passed Given/When/Then scenarios")
    if not _passed(payload["security"]):
        raise QualityError("security and authorization review is required")
    coverage = payload["coverage"]
    if payload["risk"] in {"medium", "high"}:
        minimum = 80 if payload["risk"] == "medium" else 90
        if (
            not isinstance(coverage, dict)
            or not isinstance(coverage.get("changed_lines"), (int, float))
            or not isinstance(coverage.get("threshold"), (int, float))
            or coverage["threshold"] < minimum
            or coverage["changed_lines"] < coverage["threshold"]
        ):
            raise QualityError(f"coverage threshold is not met (minimum {minimum})")
    elif not isinstance(coverage, dict):
        raise QualityError("coverage must be an object")
    if payload["risk"] == "high":
        mutation = payload["mutation"]
        if not isinstance(mutation, dict) or not isinstance(mutation.get("score"), (int, float)) or not isinstance(mutation.get("threshold"), (int, float)) or mutation["threshold"] < 80 or mutation["score"] < mutation["threshold"]:
            raise QualityError("high-risk result requires a passing mutation score")
        if not _passed(payload["recovery"]):
            raise QualityError("high-risk result requires recovery evidence")
        review = payload["review"]
        if not isinstance(review, dict) or review.get("fresh_reviewer") != "passed" or review.get("adjudicator") != "passed":
            raise QualityError("high-risk result requires fresh reviewer and adjudicator")
    if not isinstance(payload["residual_risks"], list) or not isinstance(payload["extensions"], dict):
        raise QualityError("residual_risks and extensions are invalid")
    return {"schema_version": RESULT_SCHEMA, "status": "passed", "plan_id": payload["plan_id"], "risk": payload["risk"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DS Lite quality contracts.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-plan", "evaluate-result"):
        command = sub.add_parser(name)
        command.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    try:
        result = validate_plan(_load(Path(args.path))) if args.command == "validate-plan" else evaluate_result(_load(Path(args.path)))
    except QualityError as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
