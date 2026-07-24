#!/usr/bin/env python3
"""Deterministic, redacted gates for external acceptance experiments."""

from __future__ import annotations

import copy
import re
from pathlib import PurePosixPath
from typing import Any


SCHEMA_VERSION = "ds-lite.acceptance-gate.v1"
STATUSES = {"running", "passed", "blocked", "not-verified", "ambiguous"}
FAILURE_CATEGORIES = {
    "none",
    "precondition",
    "authorization",
    "transport",
    "observation",
    "state",
    "evidence",
    "review",
    "delegation",
}
FIELDS = {
    "schema_version",
    "gate_id",
    "status",
    "input_refs",
    "authorization_ref",
    "expected_observations",
    "actual_observations",
    "evidence_refs",
    "failure_category",
    "next_action",
    "usage",
    "graph_revision",
    "status_revision",
    "extensions",
}
SENSITIVE_KEYS = {
    "api_key",
    "password",
    "secret",
    "token",
    "credential",
    "raw_jsonl",
    "stderr",
    "hidden_reasoning",
    "chain_of_thought",
    "environment_variables",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class GateError(ValueError):
    """Raised when an audit record would weaken an acceptance claim."""


def _validate_ref(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or not value or "\\" in value:
        raise GateError(f"{label} must be a project-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("/") or ":" in path.parts[0] or ".." in path.parts:
        raise GateError(f"{label} must be a project-relative path")
    return value


def _scan_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS:
                raise GateError(f"sensitive field is forbidden: {key}")
            _scan_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _scan_sensitive(child)


def _validate_id(value: Any) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise GateError("gate_id must be a stable id")
    return value


def _validate_list(value: Any, label: str, *, refs: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise GateError(f"{label} must be a list of strings")
    if refs:
        for item in value:
            _validate_ref(item, f"{label} item")
    return value


def start_gate(
    *,
    gate_id: str,
    input_refs: list[str],
    authorization_ref: str,
    expected_observations: list[str],
) -> dict[str, Any]:
    """Create a running gate with no implicit authorization or evidence."""
    record = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": gate_id,
        "status": "running",
        "input_refs": list(input_refs),
        "authorization_ref": authorization_ref,
        "expected_observations": list(expected_observations),
        "actual_observations": [],
        "evidence_refs": [],
        "failure_category": "none",
        "next_action": "",
        "usage": None,
        "graph_revision": None,
        "status_revision": None,
        "extensions": {},
    }
    validate_audit_record(record)
    return record


def record_observation(record: dict[str, Any], observation: str) -> dict[str, Any]:
    """Append one public event category, preserving insertion order."""
    validate_audit_record(record)
    if record["status"] != "running":
        raise GateError("observations can only be added to a running gate")
    if not isinstance(observation, str) or not observation or len(observation) > 128:
        raise GateError("observation must be a short non-empty category")
    if observation not in record["actual_observations"]:
        record["actual_observations"].append(observation)
    return record


def cross_check_artifacts(
    record: dict[str, Any],
    *,
    evidence_refs: list[str],
    graph_revision: int | None = None,
    status_revision: int | None = None,
) -> dict[str, Any]:
    """Attach relative refs and require Graph/STATUS revisions to agree."""
    validate_audit_record(record)
    if graph_revision is not None and status_revision is not None and graph_revision != status_revision:
        raise GateError("graph and status revision mismatch")
    if record.get("graph_revision") is not None and graph_revision is not None and record["graph_revision"] != graph_revision:
        raise GateError("existing graph revision mismatch")
    if record.get("status_revision") is not None and status_revision is not None and record["status_revision"] != status_revision:
        raise GateError("existing status revision mismatch")
    record["evidence_refs"] = list(evidence_refs)
    record["graph_revision"] = graph_revision
    record["status_revision"] = status_revision
    validate_audit_record(record)
    return record


def finalize_gate(
    record: dict[str, Any],
    *,
    status: str,
    failure_category: str,
    next_action: str,
) -> dict[str, Any]:
    """Perform the terminal transition; passing requires observable execution proof."""
    validate_audit_record(record)
    if record["status"] != "running":
        raise GateError("gate is already terminal")
    if status not in STATUSES - {"running"}:
        raise GateError("terminal status is invalid")
    if failure_category not in FAILURE_CATEGORIES:
        raise GateError("failure_category is invalid")
    if not isinstance(next_action, str) or not next_action.strip():
        raise GateError("next_action is required")
    candidate = copy.deepcopy(record)
    candidate["status"] = status
    candidate["failure_category"] = failure_category
    candidate["next_action"] = next_action.strip()
    if status == "passed":
        missing = sorted(set(candidate["expected_observations"]) - set(candidate["actual_observations"]))
        if missing:
            raise GateError(f"missing observations: {', '.join(missing)}")
        usage = candidate.get("usage")
        if not isinstance(usage, dict) or not isinstance(usage.get("total_tokens"), int) or usage["total_tokens"] <= 0:
            raise GateError("passed gate requires nonzero usage")
        if failure_category != "none":
            raise GateError("passed gate cannot carry a failure category")
    validate_audit_record(candidate)
    record.clear()
    record.update(candidate)
    return record


def can_enter_next_gate(record: dict[str, Any]) -> bool:
    """Only a fully validated passed gate unlocks the next gate."""
    validate_audit_record(record)
    return record["status"] == "passed" and record["failure_category"] == "none"


def validate_audit_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise GateError("audit record must be an object")
    unknown = sorted(set(record) - FIELDS)
    if unknown:
        raise GateError(f"unsupported audit fields: {', '.join(unknown)}")
    missing = sorted(FIELDS - set(record))
    if missing:
        raise GateError(f"missing audit fields: {', '.join(missing)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise GateError("unsupported schema_version")
    _validate_id(record["gate_id"])
    if record["status"] not in STATUSES:
        raise GateError("status is invalid")
    _validate_list(record["input_refs"], "input_refs", refs=True)
    _validate_ref(record["authorization_ref"], "authorization_ref")
    _validate_list(record["expected_observations"], "expected_observations")
    _validate_list(record["actual_observations"], "actual_observations")
    _validate_list(record["evidence_refs"], "evidence_refs", refs=True)
    if record["failure_category"] not in FAILURE_CATEGORIES:
        raise GateError("failure_category is invalid")
    if not isinstance(record["next_action"], str):
        raise GateError("next_action must be a string")
    if record["usage"] is not None and not isinstance(record["usage"], dict):
        raise GateError("usage must be an object or null")
    for label in ("graph_revision", "status_revision"):
        if record[label] is not None and (not isinstance(record[label], int) or record[label] < 0):
            raise GateError(f"{label} must be a nonnegative integer or null")
    if not isinstance(record["extensions"], dict):
        raise GateError("extensions must be an object")
    _scan_sensitive(record)
    return record
