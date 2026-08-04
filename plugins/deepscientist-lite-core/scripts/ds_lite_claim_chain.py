#!/usr/bin/env python3
"""Chain of Evidence for DS Lite v6.

Validates that each atomic claim is bound to its selector, transformation
chain, dependence group, executed code, and verifier at creation time.
Detects shared dependencies across claims.

Schema: ds-lite.chain-of-evidence.v1
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

CHAIN_SCHEMA = "ds-lite.chain-of-evidence.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

SELECTOR_TYPES = frozenset({
    "file-range", "cell-range", "line-range", "json-path",
    "xpath", "regex-match", "commit-hash", "artifact-ref",
})

TRANSFORMATION_TYPES = frozenset({
    "identity", "aggregation", "filtering", "normalization",
    "statistical-test", "machine-learning", "manual-annotation",
    "code-execution", "data-join", "custom",
})

DEPENDENCE_TYPES = frozenset({
    "shared-dataset", "shared-code", "shared-author",
    "shared-derivation", "shared-method", "independent",
})


class ChainError(RuntimeError):
    pass


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_selector(selector: Any) -> dict[str, Any]:
    """Validate a claim selector."""
    if not isinstance(selector, dict):
        raise ChainError("selector must be an object")
    if not isinstance(selector.get("type"), str):
        raise ChainError("selector.type must be a string")
    if selector["type"] not in SELECTOR_TYPES:
        raise ChainError(f"selector.type must be one of {sorted(SELECTOR_TYPES)}")
    if not isinstance(selector.get("value"), str) or not selector["value"].strip():
        raise ChainError("selector.value must be a non-empty string")
    if not isinstance(selector.get("artifact_ref"), str):
        raise ChainError("selector.artifact_ref must be a string")
    return selector


def validate_transformation_chain(chain: Any) -> list[dict[str, Any]]:
    """Validate a transformation chain."""
    if not isinstance(chain, list):
        raise ChainError("transformation_chain must be a list")
    validated = []
    for step in chain:
        if not isinstance(step, dict):
            raise ChainError("each transformation step must be an object")
        if not isinstance(step.get("type"), str):
            raise ChainError("transformation step.type must be a string")
        if step["type"] not in TRANSFORMATION_TYPES:
            raise ChainError(f"transformation type must be one of {sorted(TRANSFORMATION_TYPES)}")
        if not isinstance(step.get("description"), str) or not step["description"].strip():
            raise ChainError("transformation step.description must be non-empty")
        if not isinstance(step.get("input_ref"), str):
            raise ChainError("transformation step.input_ref must be a string")
        if not isinstance(step.get("output_ref"), str):
            raise ChainError("transformation step.output_ref must be a string")
        validated.append(step)
    return validated


def validate_chain_of_evidence(claim: dict[str, Any], evidence_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the chain of evidence for a single claim.

    Returns a result dict with:
    - verdict: "pass" | "blocked" | "warning"
    - rule_ids: list of triggered rule IDs
    - chain_digest: str
    """
    rule_ids: list[str] = []
    verdict = "pass"

    # Rule: claim must have a selector
    selector = claim.get("selector")
    try:
        validate_selector(selector)
    except ChainError:
        rule_ids.append("missing_or_invalid_selector")
        verdict = "blocked"
        selector = None

    # Rule: transformation chain must be valid
    chain = claim.get("transformation_chain", [])
    try:
        validated_chain = validate_transformation_chain(chain)
    except ChainError:
        rule_ids.append("invalid_transformation_chain")
        verdict = "blocked"
        validated_chain = []

    # Rule: claim must have evidence refs
    evidence_refs = claim.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or len(evidence_refs) == 0:
        rule_ids.append("missing_evidence_refs")
        verdict = "blocked"

    # Rule: claim must have executed code ref
    executed_code_ref = claim.get("executed_code_ref", "")
    if not isinstance(executed_code_ref, str) or not executed_code_ref.strip():
        rule_ids.append("missing_executed_code_ref")
        verdict = "blocked"

    # Rule: claim must have a verifier
    verifier = claim.get("verifier", {})
    if not isinstance(verifier, dict) or not verifier.get("type"):
        rule_ids.append("missing_verifier")
        verdict = "blocked"

    # Rule: dependence group must be specified
    dependence_group = claim.get("dependence_group", "")
    if not isinstance(dependence_group, str) or not dependence_group.strip():
        rule_ids.append("missing_dependence_group")
        verdict = "blocked"

    # Rule: empty transformation chain triggers warning
    if len(validated_chain) == 0 and verdict != "blocked":
        rule_ids.append("empty_transformation_chain")
        verdict = "warning"

    # Compute chain digest
    digest_data = {
        "claim_id": claim.get("claim_id", "unknown"),
        "selector": selector,
        "transformation_chain": validated_chain,
        "evidence_refs": sorted(evidence_refs) if isinstance(evidence_refs, list) else [],
        "dependence_group": dependence_group,
        "executed_code_ref": executed_code_ref,
        "verifier": verifier,
    }
    chain_digest = _digest(digest_data)

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "chain_digest": chain_digest,
    }
    return result


def check_dependency_group(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Check for shared dependencies across claims.

    Returns a DependencyAudit with:
    - has_shared_dependency: bool
    - shared_groups: dict mapping dependence_group to list of claim_ids
    - independent_count: int
    - shared_count: int
    """
    if not isinstance(claims, list):
        raise ChainError("claims must be a list")

    groups: dict[str, list[str]] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        dep_group = claim.get("dependence_group", "unknown")
        claim_id = claim.get("claim_id", "unknown")
        groups.setdefault(dep_group, []).append(claim_id)

    shared_groups = {k: v for k, v in groups.items() if len(v) > 1}
    shared_count = sum(len(v) for v in shared_groups.values())
    independent_count = len(claims) - shared_count

    result = {
        "has_shared_dependency": len(shared_groups) > 0,
        "shared_groups": shared_groups,
        "independent_count": independent_count,
        "shared_count": shared_count,
        "total_claims": len(claims),
    }
    return result


def validate_claim_ledger(document: Any) -> dict[str, Any]:
    """Validate a claim ledger document.

    Returns a result dict with:
    - verdict: "pass" | "blocked" | "warning"
    - rule_ids: list of triggered rule IDs
    - ledger_digest: str
    """
    if not isinstance(document, dict):
        raise ChainError("ledger must be an object")

    if document.get("schema_version") != "ds-lite.claim-ledger.v1":
        raise ChainError("invalid ledger schema")

    claims = document.get("claims", [])
    if not isinstance(claims, list):
        raise ChainError("claims must be a list")

    rule_ids: list[str] = []
    verdict = "pass"

    # Validate each claim's chain of evidence
    for i, claim in enumerate(claims):
        result = validate_chain_of_evidence(claim)
        if result["verdict"] == "blocked":
            rule_ids.append(f"claim_{i}_blocked")
            verdict = "blocked"
        elif result["verdict"] == "warning" and verdict != "blocked":
            rule_ids.append(f"claim_{i}_warning")
            verdict = "warning"

    # Check dependency groups
    dep_audit = check_dependency_group(claims)
    if dep_audit["has_shared_dependency"]:
        rule_ids.append("shared_dependencies_detected")
        if verdict == "pass":
            verdict = "warning"

    # Compute ledger digest
    ledger_data = {
        "ledger_id": document.get("ledger_id", "unknown"),
        "claim_count": len(claims),
        "claim_ids": sorted([c.get("claim_id", "") for c in claims if isinstance(c, dict)]),
    }
    ledger_digest = _digest(ledger_data)

    result = {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "ledger_digest": ledger_digest,
        "dependency_audit": dep_audit,
    }
    return result


def create_chain_entry(
    claim_id: str,
    selector_type: str,
    selector_value: str,
    artifact_ref: str,
    transformation_chain: list[dict[str, Any]],
    evidence_refs: list[str],
    dependence_group: str,
    executed_code_ref: str,
    verifier_type: str,
    verifier_result: str,
) -> dict[str, Any]:
    """Create a chain of evidence entry for a claim."""
    entry = {
        "claim_id": claim_id,
        "selector": {
            "type": selector_type,
            "value": selector_value,
            "artifact_ref": artifact_ref,
        },
        "transformation_chain": transformation_chain,
        "evidence_refs": evidence_refs,
        "dependence_group": dependence_group,
        "executed_code_ref": executed_code_ref,
        "verifier": {
            "type": verifier_type,
            "result": verifier_result,
        },
    }
    return entry


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Chain of Evidence for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--ledger", required=True, help="Path to claim ledger JSON")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.ledger, encoding="utf-8").read())
            result = validate_claim_ledger(doc)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        return 1
    except (ChainError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())