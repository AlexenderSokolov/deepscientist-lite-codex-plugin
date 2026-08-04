#!/usr/bin/env python3
"""Method Fidelity Manifest for DS Lite v6.

Records the original method, adaptations, deletions, and actual code
identity. Ensures method fidelity is auditable.

Schema: ds-lite.method-fidelity.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

FIDELITY_SCHEMA = "ds-lite.method-fidelity.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

ADAPTATION_TYPES = frozenset({
    "parameter-change", "data-preprocessing", "model-architecture",
    "training-schedule", "evaluation-metric", "dataset-subset",
    "feature-engineering", "regularization", "other",
})

DELETION_TYPES = frozenset({
    "step-removed", "component-removed", "parameter-removed",
    "validation-removed", "other",
})


class FidelityError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_method_fidelity_manifest(document: Any) -> dict[str, Any]:
    """Validate a Method Fidelity Manifest document."""
    if not isinstance(document, dict):
        raise FidelityError("document must be an object")

    if document.get("schema_version") != FIDELITY_SCHEMA:
        raise FidelityError(f"schema_version must be {FIDELITY_SCHEMA}")

    required = {
        "schema_version", "method_id", "method_name",
        "original_method_ref", "adaptations", "deletions",
        "actual_code_ref", "code_identity_digest",
        "fidelity_assessment", "created_at", "extensions",
    }
    missing = required - set(document.keys())
    if missing:
        raise FidelityError(f"missing required fields: {sorted(missing)}")

    if not ID_RE.fullmatch(document["method_id"]):
        raise FidelityError("method_id must match identifier pattern")

    if not isinstance(document["adaptations"], list):
        raise FidelityError("adaptations must be a list")

    if not isinstance(document["deletions"], list):
        raise FidelityError("deletions must be a list")

    # Validate adaptations
    for i, adapt in enumerate(document["adaptations"]):
        if not isinstance(adapt, dict):
            raise FidelityError(f"adaptation {i} must be an object")
        if adapt.get("type") not in ADAPTATION_TYPES:
            raise FidelityError(f"adaptation {i} type must be one of {sorted(ADAPTATION_TYPES)}")
        if not isinstance(adapt.get("description"), str) or not adapt["description"].strip():
            raise FidelityError(f"adaptation {i} description must be non-empty")

    # Validate deletions
    for i, deletion in enumerate(document["deletions"]):
        if not isinstance(deletion, dict):
            raise FidelityError(f"deletion {i} must be an object")
        if deletion.get("type") not in DELETION_TYPES:
            raise FidelityError(f"deletion {i} type must be one of {sorted(DELETION_TYPES)}")
        if not isinstance(deletion.get("description"), str) or not deletion["description"].strip():
            raise FidelityError(f"deletion {i} description must be non-empty")

    # Validate fidelity assessment
    assessment = document.get("fidelity_assessment", {})
    if not isinstance(assessment, dict):
        raise FidelityError("fidelity_assessment must be an object")

    return {
        "verdict": "pass",
        "fidelity_digest": _digest({
            "method_id": document["method_id"],
            "method_name": document["method_name"],
            "adaptations_count": len(document["adaptations"]),
            "deletions_count": len(document["deletions"]),
        }),
    }


def create_method_fidelity_manifest(
    method_id: str,
    method_name: str,
    original_method_ref: str,
    adaptations: list[dict[str, Any]],
    deletions: list[dict[str, Any]],
    actual_code_ref: str,
    code_identity_digest: str,
    fidelity_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Method Fidelity Manifest document."""
    if not ID_RE.fullmatch(method_id):
        raise FidelityError("method_id must match identifier pattern")

    now = _now_iso()
    document = {
        "schema_version": FIDELITY_SCHEMA,
        "method_id": method_id,
        "method_name": method_name,
        "original_method_ref": original_method_ref,
        "adaptations": adaptations,
        "deletions": deletions,
        "actual_code_ref": actual_code_ref,
        "code_identity_digest": code_identity_digest,
        "fidelity_assessment": fidelity_assessment or {
            "fidelity_level": "high",
            "major_deviations": [],
            "notes": "",
        },
        "created_at": now,
        "extensions": {},
    }
    return document


def check_code_identity(manifest: dict[str, Any], actual_code_ref: str) -> dict[str, Any]:
    """Check if the actual code identity matches the manifest."""
    manifest_code_ref = manifest.get("actual_code_ref", "")
    manifest_digest = manifest.get("code_identity_digest", "")

    matches = manifest_code_ref == actual_code_ref

    return {
        "matches": matches,
        "manifest_code_ref": manifest_code_ref,
        "actual_code_ref": actual_code_ref,
        "manifest_digest": manifest_digest,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Method Fidelity Manifest for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--document", required=True)

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_method_fidelity_manifest(doc)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (FidelityError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())