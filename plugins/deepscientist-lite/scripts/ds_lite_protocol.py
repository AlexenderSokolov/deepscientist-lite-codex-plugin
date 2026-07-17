#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ds_lite_evidence import EvidenceError, normalize_protocol_path

WORK_UNIT_SCHEMA = "ds-lite.work-unit.v1"
REVIEW_RESULT_SCHEMA = "ds-lite.review-result.v1"
FACTOR_CARD_SCHEMA = "ds-lite.factor-card.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
EXECUTION_MODES = {"none", "inline", "external", "human"}
WORK_UNIT_STATES = {"proposed", "active", "blocked", "done"}
SUBJECT_KINDS = {"conversation", "worker", "terminal", "job", "request", "artifact", "human"}
REVIEW_VERDICTS = {"pass", "fail", "needs-human"}
CLAIM_ASSESSMENTS = {"none", "inconclusive", "refuted", "supportable"}
CHANNEL_STATUSES = {"pass", "fail", "needs-human", "not-applicable"}
FACTOR_CARD_STATUSES = {"draft", "assessed", "reviewed"}
FACTOR_CARD_DECISIONS = {"explore", "verify-first", "park", "reject", "needs-human"}
FACTOR_CONFIDENCE = {"unknown", "low", "medium", "high"}
FACTOR_NAMES = {
    "novelty",
    "feasibility",
    "evidence_strength",
    "cost",
    "risk",
    "alignment",
}
FORBIDDEN_KEYS = {
    "thought",
    "chain_of_thought",
    "hidden_thought",
    "reasoning_trace",
    "env",
    "environment_variables",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "access_key",
    "private_key",
    "client_secret",
    "authorization",
    "cookie",
}
WORK_UNIT_REQUIRED = {
    "schema_version",
    "work_unit_id",
    "title",
    "goal",
    "execution_mode",
    "profile_id",
    "state",
    "prerequisites",
    "required_capabilities",
    "evidence_requirements",
    "evidence_refs",
    "resource_limits",
    "subjects",
    "active_iteration_ref",
    "extensions",
}
REVIEW_RESULT_REQUIRED = {
    "schema_version",
    "review_id",
    "work_unit_id",
    "profile_id",
    "review_node_id",
    "reviewed_node_id",
    "reviewed_evidence_refs",
    "evidence_validator",
    "evidence_digest",
    "verdict",
    "claim_assessment",
    "channels",
    "limitations",
    "review_artifact_ref",
    "completed_at",
    "extensions",
}
FACTOR_CARD_REQUIRED = {
    "schema_version",
    "factor_card_id",
    "work_unit_id",
    "profile_id",
    "subject_ref",
    "status",
    "factors",
    "decision",
    "minimal_test",
    "created_at",
    "updated_at",
    "extensions",
}


class ProtocolError(Exception):
    pass


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def find_forbidden_key(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = _normalized_key(key)
            location = f"{prefix}.{key}" if prefix else str(key)
            if (
                normalized in FORBIDDEN_KEYS
                or normalized.endswith("_token")
                or normalized.endswith("_password")
                or normalized.endswith("_secret")
                or normalized.endswith("_api_key")
                or normalized.endswith("_credential")
            ):
                return location
            found = find_forbidden_key(item, location)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_forbidden_key(item, f"{prefix}[{index}]")
            if found:
                return found
    return None


def validate_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ProtocolError(f"{label} must match [a-z0-9][a-z0-9._-]{{0,127}}")
    return value


def validate_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ProtocolError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ProtocolError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_ref(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    try:
        normalized = normalize_protocol_path(value)
    except EvidenceError as exc:
        raise ProtocolError(f"{label} must be a normalized project-relative or external path: {exc}") from exc
    if normalized != value:
        raise ProtocolError(f"{label} must be normalized: {value}")
    return normalized


def _require_object(payload: Any, schema: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProtocolError(f"{schema} must contain a JSON object")
    missing = required - set(payload)
    unknown = set(payload) - required
    if missing:
        raise ProtocolError(f"{schema} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ProtocolError(f"{schema} has unsupported fields: {', '.join(sorted(unknown))}")
    sensitive = find_forbidden_key(payload)
    if sensitive:
        raise ProtocolError(f"{schema} contains a sensitive or hidden-reasoning field: {sensitive}")
    if payload.get("schema_version") != schema:
        raise ProtocolError(f"schema_version must be {schema}")
    if not isinstance(payload.get("extensions"), dict):
        raise ProtocolError("extensions must be an object")
    return payload


def _validate_unique_refs(value: Any, label: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        suffix = "" if allow_empty else " and must not be empty"
        raise ProtocolError(f"{label} must be a list of paths{suffix}")
    refs = [validate_ref(item, f"{label}[{index}]") for index, item in enumerate(value)]
    if len(refs) != len(set(refs)):
        raise ProtocolError(f"{label} contains duplicate paths")
    return refs


def validate_work_unit(payload: Any) -> dict[str, Any]:
    payload = _require_object(payload, WORK_UNIT_SCHEMA, WORK_UNIT_REQUIRED)
    validate_id(payload["work_unit_id"], "work_unit_id")
    validate_id(payload["profile_id"], "profile_id")
    for field in ("title", "goal"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise ProtocolError(f"{field} must be a non-empty string")
    if payload["execution_mode"] not in EXECUTION_MODES:
        raise ProtocolError("execution_mode must be none, inline, external, or human")
    if payload["state"] not in WORK_UNIT_STATES:
        raise ProtocolError("state must be proposed, active, blocked, or done")
    _validate_unique_refs(payload["prerequisites"], "prerequisites")
    _validate_unique_refs(payload["evidence_refs"], "evidence_refs")
    validate_ref(payload["active_iteration_ref"], "active_iteration_ref", allow_empty=True)

    capabilities = payload["required_capabilities"]
    if not isinstance(capabilities, list):
        raise ProtocolError("required_capabilities must be a list")
    normalized_capabilities = [validate_id(item, "required_capabilities item") for item in capabilities]
    if len(normalized_capabilities) != len(set(normalized_capabilities)):
        raise ProtocolError("required_capabilities contains duplicates")

    requirements = payload["evidence_requirements"]
    if not isinstance(requirements, list):
        raise ProtocolError("evidence_requirements must be a list")
    requirement_ids: set[tuple[str, str]] = set()
    for index, item in enumerate(requirements):
        if not isinstance(item, dict) or set(item) - {"kind", "validator", "extensions"}:
            raise ProtocolError(f"evidence_requirements[{index}] has unsupported fields")
        if set(item) < {"kind", "validator"}:
            raise ProtocolError(f"evidence_requirements[{index}] missing fields")
        kind = validate_id(item["kind"], f"evidence_requirements[{index}].kind")
        validator = validate_id(item["validator"], f"evidence_requirements[{index}].validator")
        if "extensions" in item and not isinstance(item["extensions"], dict):
            raise ProtocolError(f"evidence_requirements[{index}].extensions must be an object")
        identity = (kind, validator)
        if identity in requirement_ids:
            raise ProtocolError("evidence_requirements contains duplicate kind/validator pairs")
        requirement_ids.add(identity)

    limits = payload["resource_limits"]
    if not isinstance(limits, list):
        raise ProtocolError("resource_limits must be a list")
    limit_ids: set[tuple[str, str]] = set()
    for index, item in enumerate(limits):
        if not isinstance(item, dict) or set(item) != {"dimension", "unit", "value"}:
            raise ProtocolError(f"resource_limits[{index}] must contain exactly dimension, unit, and value")
        dimension = validate_id(item["dimension"], f"resource_limits[{index}].dimension")
        unit = validate_id(item["unit"], f"resource_limits[{index}].unit")
        value = item["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ProtocolError(f"resource_limits[{index}].value must be a non-negative number")
        identity = (dimension, unit)
        if identity in limit_ids:
            raise ProtocolError("resource_limits contains duplicate dimension/unit pairs")
        limit_ids.add(identity)

    subjects = payload["subjects"]
    if not isinstance(subjects, list):
        raise ProtocolError("subjects must be a list")
    subject_ids: set[str] = set()
    for index, item in enumerate(subjects):
        if not isinstance(item, dict) or set(item) - {"kind", "id", "query_ref", "extensions"}:
            raise ProtocolError(f"subjects[{index}] has unsupported fields")
        if set(item) < {"kind", "id", "query_ref"}:
            raise ProtocolError(f"subjects[{index}] missing fields")
        if item["kind"] not in SUBJECT_KINDS:
            raise ProtocolError(f"subjects[{index}].kind is invalid")
        subject_id = validate_id(item["id"], f"subjects[{index}].id")
        if subject_id in subject_ids:
            raise ProtocolError(f"duplicate subject id: {subject_id}")
        subject_ids.add(subject_id)
        validate_ref(item["query_ref"], f"subjects[{index}].query_ref")
        if "extensions" in item and not isinstance(item["extensions"], dict):
            raise ProtocolError(f"subjects[{index}].extensions must be an object")
    return json.loads(json.dumps(payload))


def _validate_resource_limits(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise ProtocolError(f"{label} must be a list")
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"dimension", "unit", "value"}:
            raise ProtocolError(f"{label}[{index}] must contain exactly dimension, unit, and value")
        dimension = validate_id(item["dimension"], f"{label}[{index}].dimension")
        unit = validate_id(item["unit"], f"{label}[{index}].unit")
        amount = item["value"]
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
            raise ProtocolError(f"{label}[{index}].value must be a non-negative number")
        identity = (dimension, unit)
        if identity in identities:
            raise ProtocolError(f"{label} contains duplicate dimension/unit pairs")
        identities.add(identity)


def validate_factor_card(payload: Any) -> dict[str, Any]:
    payload = _require_object(payload, FACTOR_CARD_SCHEMA, FACTOR_CARD_REQUIRED)
    factor_card_id = validate_id(payload["factor_card_id"], "factor_card_id")
    work_unit_id = validate_id(payload["work_unit_id"], "work_unit_id")
    validate_id(payload["profile_id"], "profile_id")
    if factor_card_id == work_unit_id:
        raise ProtocolError("factor_card_id and work_unit_id must differ")
    validate_ref(payload["subject_ref"], "subject_ref")
    if payload["status"] not in FACTOR_CARD_STATUSES:
        raise ProtocolError("status must be draft, assessed, or reviewed")
    if payload["decision"] not in FACTOR_CARD_DECISIONS:
        raise ProtocolError("decision must be explore, verify-first, park, reject, or needs-human")

    factors = payload["factors"]
    if not isinstance(factors, list):
        raise ProtocolError("factors must be a list")
    seen: set[str] = set()
    factor_fields = {"name", "score", "confidence", "evidence_refs", "summary", "uncertainty", "extensions"}
    for index, factor in enumerate(factors):
        if not isinstance(factor, dict) or set(factor) != factor_fields:
            raise ProtocolError(f"factors[{index}] must contain exactly {', '.join(sorted(factor_fields))}")
        name = factor["name"]
        if name not in FACTOR_NAMES:
            raise ProtocolError(f"factors[{index}].name is invalid")
        if name in seen:
            raise ProtocolError("each required factor must appear exactly once")
        seen.add(name)
        score = factor["score"]
        if score is not None and (not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 4):
            raise ProtocolError(f"factors[{index}].score must be null or an integer from 0 to 4")
        confidence = factor["confidence"]
        if confidence not in FACTOR_CONFIDENCE:
            raise ProtocolError(f"factors[{index}].confidence is invalid")
        refs = _validate_unique_refs(factor["evidence_refs"], f"factors[{index}].evidence_refs")
        if score is None and confidence != "unknown":
            raise ProtocolError("an unknown factor score requires unknown confidence")
        if score is not None and confidence == "unknown":
            raise ProtocolError("a scored factor requires non-unknown confidence")
        if score is not None and not refs:
            raise ProtocolError("a scored factor requires evidence_refs")
        if not isinstance(factor["summary"], str) or not factor["summary"].strip():
            raise ProtocolError(f"factors[{index}].summary must be a non-empty string")
        if not isinstance(factor["uncertainty"], list) or not all(
            isinstance(item, str) and item.strip() for item in factor["uncertainty"]
        ):
            raise ProtocolError(f"factors[{index}].uncertainty must be a list of non-empty strings")
        if not isinstance(factor["extensions"], dict):
            raise ProtocolError(f"factors[{index}].extensions must be an object")
    if seen != FACTOR_NAMES:
        raise ProtocolError("each required factor must appear exactly once")

    minimal_test = payload["minimal_test"]
    minimal_fields = {
        "question",
        "method",
        "expected_evidence",
        "resource_limits",
        "stop_condition",
        "extensions",
    }
    if not isinstance(minimal_test, dict) or set(minimal_test) != minimal_fields:
        raise ProtocolError("minimal_test has unsupported or missing fields")
    for field in ("question", "method", "stop_condition"):
        if not isinstance(minimal_test[field], str) or not minimal_test[field].strip():
            raise ProtocolError(f"minimal_test.{field} must be a non-empty string")
    expected = minimal_test["expected_evidence"]
    if not isinstance(expected, list) or not expected or not all(isinstance(item, str) and item.strip() for item in expected):
        raise ProtocolError("minimal_test.expected_evidence must be a non-empty list of strings")
    _validate_resource_limits(minimal_test["resource_limits"], "minimal_test.resource_limits")
    if not isinstance(minimal_test["extensions"], dict):
        raise ProtocolError("minimal_test.extensions must be an object")
    validate_timestamp(payload["created_at"], "created_at")
    validate_timestamp(payload["updated_at"], "updated_at")
    return json.loads(json.dumps(payload))


def validate_review_result(payload: Any) -> dict[str, Any]:
    payload = _require_object(payload, REVIEW_RESULT_SCHEMA, REVIEW_RESULT_REQUIRED)
    for field in ("review_id", "work_unit_id", "profile_id", "review_node_id", "reviewed_node_id"):
        validate_id(payload[field], field)
    if payload["review_id"] != payload["review_node_id"]:
        raise ProtocolError("review_id must match review_node_id")
    if payload["review_node_id"] == payload["reviewed_node_id"]:
        raise ProtocolError("review_node_id and reviewed_node_id must differ")
    refs = _validate_unique_refs(payload["reviewed_evidence_refs"], "reviewed_evidence_refs", allow_empty=False)
    validate_id(payload["evidence_validator"], "evidence_validator")
    if not isinstance(payload["evidence_digest"], str) or not SHA256_RE.fullmatch(payload["evidence_digest"]):
        raise ProtocolError("evidence_digest must be a lowercase SHA-256 hex digest")
    if payload["verdict"] not in REVIEW_VERDICTS:
        raise ProtocolError("verdict must be pass, fail, or needs-human")
    if payload["claim_assessment"] not in CLAIM_ASSESSMENTS:
        raise ProtocolError("claim_assessment must be none, inconclusive, refuted, or supportable")

    channels = payload["channels"]
    if not isinstance(channels, dict) or not channels:
        raise ProtocolError("channels must be a non-empty object")
    for channel, status in channels.items():
        validate_id(channel, "channel id")
        if status not in CHANNEL_STATUSES:
            raise ProtocolError(f"channel {channel} has invalid status")
    statuses = set(channels.values())
    if payload["verdict"] == "pass" and ("fail" in statuses or "needs-human" in statuses):
        raise ProtocolError("pass verdict conflicts with channel status")
    if payload["verdict"] == "fail" and "fail" not in statuses:
        raise ProtocolError("fail verdict requires a failing channel")
    if payload["verdict"] == "needs-human" and ("fail" in statuses or "needs-human" not in statuses):
        raise ProtocolError("needs-human verdict requires a needs-human channel and no failing channel")

    limitations = payload["limitations"]
    if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        raise ProtocolError("limitations must be a list of strings")
    validate_ref(payload["review_artifact_ref"], "review_artifact_ref")
    validate_timestamp(payload["completed_at"], "completed_at")
    if not refs:
        raise ProtocolError("reviewed_evidence_refs must not be empty")
    return json.loads(json.dumps(payload))


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def evidence_refs_digest(records: list[dict[str, str]]) -> str:
    ordered = sorted(records, key=lambda item: item["path"])
    return hashlib.sha256(canonical_json_bytes(ordered)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DeepScientist Lite sidecar protocols.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    factor_parser = subparsers.add_parser("validate-factor-card", help="Validate ds-lite.factor-card.v1 JSON.")
    factor_parser.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
        validated = validate_factor_card(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ProtocolError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "schema_version": validated["schema_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
