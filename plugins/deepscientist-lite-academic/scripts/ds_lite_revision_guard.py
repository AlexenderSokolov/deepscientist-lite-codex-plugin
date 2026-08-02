#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


CONSTRAINTS_SCHEMA = "ds-lite.revision-constraints.v1"
ADVERSARIAL_SCHEMA = "ds-lite.adversarial-review.v1"
EFFECTS = {
    "prose-only", "new-citation", "new-number", "new-theorem",
    "delete-citation", "delete-section", "negative-result-preserved",
}
OPERATIONS = {"create", "modify", "delete", "rename"}


class RevisionGuardError(ValueError):
    pass


def _safe_ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RevisionGuardError(f"{label} must be a non-empty relative path")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or PureWindowsPath(value).is_absolute() or ".." in posix.parts:
        raise RevisionGuardError(f"{label} must be project-relative")
    return posix.as_posix()


def validate_constraints(payload: Any) -> dict[str, Any]:
    required = {
        "schema_version", "allowed_paths", "allow_new_citations", "allow_new_numbers",
        "allow_new_theorems", "allow_delete_citations", "allow_delete_sections",
        "max_files_changed", "max_operations", "approval_refs", "extensions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RevisionGuardError("revision constraint fields are invalid")
    if payload["schema_version"] != CONSTRAINTS_SCHEMA:
        raise RevisionGuardError("revision constraint schema is unsupported")
    if not isinstance(payload["allowed_paths"], list) or not payload["allowed_paths"]:
        raise RevisionGuardError("allowed_paths must be non-empty")
    for value in payload["allowed_paths"]:
        _safe_ref(value.rstrip("/"), "allowed_paths")
    for key in (
        "allow_new_citations", "allow_new_numbers", "allow_new_theorems",
        "allow_delete_citations", "allow_delete_sections",
    ):
        if not isinstance(payload[key], bool):
            raise RevisionGuardError(f"{key} must be boolean")
    for key in ("max_files_changed", "max_operations"):
        if not isinstance(payload[key], int) or payload[key] < 1:
            raise RevisionGuardError(f"{key} must be positive")
    if not isinstance(payload["approval_refs"], list):
        raise RevisionGuardError("approval_refs must be a list")
    for value in payload["approval_refs"]:
        _safe_ref(value, "approval_refs")
    if not isinstance(payload["extensions"], dict):
        raise RevisionGuardError("extensions must be an object")
    return json.loads(json.dumps(payload))


def _path_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = _safe_ref(path, "change.path")
    return any(
        normalized == allowed.rstrip("/") or (allowed.endswith("/") and normalized.startswith(allowed))
        for allowed in allowed_paths
    )


def evaluate_revision(constraints: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
    constraints = validate_constraints(constraints)
    if not isinstance(changes, list):
        raise RevisionGuardError("changes must be a list")
    violations: list[str] = []
    paths: set[str] = set()
    effect_rules = {
        "new-citation": ("allow_new_citations", "new-citation-not-approved"),
        "new-number": ("allow_new_numbers", "new-number-not-approved"),
        "new-theorem": ("allow_new_theorems", "new-theorem-not-approved"),
        "delete-citation": ("allow_delete_citations", "delete-citation-not-approved"),
        "delete-section": ("allow_delete_sections", "delete-section-not-approved"),
    }
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "operation", "effects"}:
            raise RevisionGuardError("change fields are invalid")
        path = _safe_ref(change["path"], "change.path")
        paths.add(path)
        if not _path_allowed(path, constraints["allowed_paths"]):
            violations.append("path-out-of-scope")
        if change["operation"] not in OPERATIONS:
            raise RevisionGuardError("change operation is invalid")
        if not isinstance(change["effects"], list) or not set(change["effects"]).issubset(EFFECTS):
            raise RevisionGuardError("change effects are invalid")
        for effect in change["effects"]:
            if effect in effect_rules and not constraints[effect_rules[effect][0]]:
                violations.append(effect_rules[effect][1])
    if len(paths) > constraints["max_files_changed"]:
        violations.append("file-limit-exceeded")
    if len(changes) > constraints["max_operations"]:
        violations.append("operation-limit-exceeded")
    approval_effects = set(effect_rules) & {effect for change in changes for effect in change["effects"]}
    if approval_effects and not constraints["approval_refs"]:
        violations.append("approval-ref-required")
    unique = list(dict.fromkeys(violations))
    return {
        "schema_version": "ds-lite.revision-check.v1",
        "status": "passed" if not unique else "blocked",
        "violations": unique,
        "changed_paths": sorted(paths),
        "operation_count": len(changes),
        "extensions": {},
    }


def build_adversarial_review(
    *,
    strongest_objection: str,
    attack_receipt: dict[str, Any] | None,
    adjudicator_receipt: dict[str, Any] | None,
    concerns: list[dict[str, str]],
) -> dict[str, Any]:
    if not isinstance(strongest_objection, str) or not strongest_objection.strip():
        raise RevisionGuardError("strongest_objection must be non-empty")
    if not isinstance(concerns, list):
        raise RevisionGuardError("concerns must be a list")
    for concern in concerns:
        if not isinstance(concern, dict) or set(concern) != {"id", "priority", "verdict"}:
            raise RevisionGuardError("concern fields are invalid")
        if concern["priority"] not in {"P0", "P1", "P2", "P3"}:
            raise RevisionGuardError("concern priority is invalid")
    isolated = bool(
        attack_receipt and adjudicator_receipt
        and attack_receipt.get("fresh") is True and adjudicator_receipt.get("fresh") is True
        and isinstance(attack_receipt.get("context_id"), str)
        and isinstance(adjudicator_receipt.get("context_id"), str)
        and attack_receipt["context_id"] != adjudicator_receipt["context_id"]
    )
    return {
        "schema_version": ADVERSARIAL_SCHEMA,
        "strongest_objections": [strongest_objection.strip()],
        "concerns": json.loads(json.dumps(concerns)),
        "isolation_status": "observed" if isolated else "not-observed",
        "attack_context_ref": str((attack_receipt or {}).get("context_id", "")),
        "adjudicator_context_ref": str((adjudicator_receipt or {}).get("context_id", "")),
        "automation": "bounded-checkpoint",
        "extensions": {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce DS Lite bounded manuscript revisions.")
    parser.add_argument("--constraints", required=True)
    parser.add_argument("--changes", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = evaluate_revision(
            json.loads(Path(args.constraints).read_text(encoding="utf-8")),
            json.loads(Path(args.changes).read_text(encoding="utf-8")),
        )
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = Path(args.output).expanduser().resolve()
            if output.exists():
                raise RevisionGuardError("output already exists; refusing overwrite")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0 if result["status"] == "passed" else 2
    except (OSError, UnicodeError, json.JSONDecodeError, RevisionGuardError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
