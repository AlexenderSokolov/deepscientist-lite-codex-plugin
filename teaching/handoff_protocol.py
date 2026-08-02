#!/usr/bin/env python3
"""Validate redacted context handoffs between bounded DS Lite actions."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = "ds-lite.handoff.v1"
STATUSES = {"prepared", "ready", "blocked", "completed", "cancelled"}
KINDS = {"conversation", "delegation", "resume"}
FIELDS = {
    "schema_version", "handoff_id", "kind", "status", "goal", "observed_facts",
    "hypotheses", "authorization_boundary", "configuration", "evidence_refs",
    "failure_layer", "unverified", "next_action", "context_digest", "extensions",
}
FORBIDDEN = {
    "prompt", "full_prompt", "conversation", "raw_jsonl", "raw_response", "stderr",
    "token", "secret", "password", "credential", "environment_variables",
    "hidden_reasoning", "absolute_path", "workstation_root",
}
CONFIG_FIELDS = {
    "cli_version", "model", "reasoning_effort", "provider_route_status", "retry_policy",
    "shell_surface", "plugin_version", "skill_count", "workspace_ref", "source_digest",
}
ABSOLUTE_WINDOWS = re.compile(r"(?:^|\s)[A-Za-z]:[\\/]")
HOST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class HandoffError(ValueError):
    pass


def context_digest(*, goal: str, facts: list[str], configuration: dict[str, Any]) -> str:
    """Hash only the redacted handoff projection, never the source conversation."""
    payload = {"goal": goal, "observed_facts": facts, "configuration": configuration}
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _scan(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN:
                raise HandoffError(f"forbidden handoff field: {key}")
            _scan(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for child in value:
            _scan(child, path)
    elif isinstance(value, str):
        if ABSOLUTE_WINDOWS.search(value) or "http://" in value.lower() or "https://" in value.lower():
            raise HandoffError(f"absolute endpoint or workstation path at {path}")


def _refs(refs: Any) -> list[str]:
    if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
        raise HandoffError("evidence_refs must be non-empty strings")
    for ref in refs:
        path = PurePosixPath(ref)
        if "\\" in ref or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise HandoffError("evidence refs must be project-relative POSIX paths")
    return refs


def validate_handoff(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise HandoffError("handoff fields do not match ds-lite.handoff.v1")
    if payload["schema_version"] != SCHEMA_VERSION or payload["status"] not in STATUSES or payload["kind"] not in KINDS:
        raise HandoffError("handoff schema, kind, or status is invalid")
    for field in ("goal", "failure_layer", "next_action"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise HandoffError(f"{field} must be non-empty")
    for field in ("observed_facts", "hypotheses", "authorization_boundary", "unverified"):
        if not isinstance(payload[field], list) or not all(isinstance(item, str) and item.strip() for item in payload[field]):
            raise HandoffError(f"{field} must be a list of non-empty strings")
    if not isinstance(payload["configuration"], dict) or set(payload["configuration"]) - CONFIG_FIELDS:
        raise HandoffError("configuration contains an unsupported field")
    _refs(payload["evidence_refs"])
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["context_digest"])):
        raise HandoffError("context_digest must be a SHA-256 hex digest")
    expected = context_digest(goal=payload["goal"], facts=payload["observed_facts"], configuration=payload["configuration"])
    if payload["context_digest"] != expected:
        raise HandoffError("context_digest does not match the redacted projection")
    host_mapping = payload["extensions"].get("host_mapping") if isinstance(payload["extensions"], dict) else None
    if host_mapping is not None:
        expected_fields = {"schema_version", "coordinator_host_id", "worker_host_ids"}
        if not isinstance(host_mapping, dict) or set(host_mapping) != expected_fields:
            raise HandoffError("host_mapping fields do not match ds-lite.host-mapping.v1")
        if host_mapping["schema_version"] != "ds-lite.host-mapping.v1":
            raise HandoffError("host_mapping schema is unsupported")
        coordinator = host_mapping["coordinator_host_id"]
        workers = host_mapping["worker_host_ids"]
        if not isinstance(coordinator, str) or not HOST_ID.fullmatch(coordinator):
            raise HandoffError("coordinator_host_id is invalid")
        if not isinstance(workers, dict) or not workers:
            raise HandoffError("worker_host_ids must be a non-empty task-to-host mapping")
        for task_id, host_id in workers.items():
            if not isinstance(task_id, str) or not HOST_ID.fullmatch(task_id):
                raise HandoffError("worker task id is invalid")
            if not isinstance(host_id, str) or not HOST_ID.fullmatch(host_id):
                raise HandoffError("worker host id is invalid")
        if coordinator in workers.values() or len(set(workers.values())) != len(workers):
            raise HandoffError("host_mapping ids must be unique")
    _scan(payload)
    return payload


def build_handoff(*, handoff_id: str, kind: str, status: str, goal: str, observed_facts: list[str],
                  hypotheses: list[str], authorization_boundary: list[str], configuration: dict[str, Any],
                  evidence_refs: list[str], failure_layer: str, unverified: list[str], next_action: str,
                  extensions: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": handoff_id,
        "kind": kind,
        "status": status,
        "goal": goal,
        "observed_facts": observed_facts,
        "hypotheses": hypotheses,
        "authorization_boundary": authorization_boundary,
        "configuration": configuration,
        "evidence_refs": evidence_refs,
        "failure_layer": failure_layer,
        "unverified": unverified,
        "next_action": next_action,
        "context_digest": context_digest(goal=goal, facts=observed_facts, configuration=configuration),
        "extensions": extensions or {},
    }
    return validate_handoff(payload)


def write_fresh_handoff(path: Path | str, payload: dict[str, Any]) -> None:
    target = Path(path)
    if target.exists():
        raise HandoffError("handoff output already exists; refusing overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(validate_handoff(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
