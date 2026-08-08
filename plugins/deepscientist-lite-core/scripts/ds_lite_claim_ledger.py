#!/usr/bin/env python3
"""Claim Ledger — binds claims to evidence at creation time for DS Lite v6.

Each claim is bound to its selector, digest, transformation chain, dependence
group, executed code, and verifier at the moment it is created. Claims can be
superseded or retracted but never deleted.

Schema: ds-lite.claim-ledger.v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from ds_lite_protocol import ProtocolError, validate_review_result

CLAIM_LEDGER_SCHEMA = "ds-lite.claim-ledger.v1"
CLAIM_SCHEMA = "ds-lite.claim.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
CLAIM_STATUSES = frozenset({"draft", "supported", "contested", "superseded", "retracted"})
FIDELITY_LEVELS = frozenset({"low", "medium", "high", "confirmatory"})
CLAIM_TYPES = frozenset({
    "positive-result", "negative-result", "null-result", "method-valid",
    "method-invalid", "boundary-confirmed", "boundary-violated",
    "reproducibility-confirmed", "reproducibility-failed",
})


class ClaimError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _claim_digest(claim: dict[str, Any]) -> str:
    """Compute a stable SHA-256 digest of a claim's core fields."""
    core = json.dumps({
        "claim_id": claim["claim_id"],
        "claim_type": claim["claim_type"],
        "statement": claim["statement"],
        "selector": claim["selector"],
        "evidence_refs": sorted(claim["evidence_refs"]),
        "dependence_group": claim["dependence_group"],
        "fidelity": claim["fidelity"],
    }, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(core.encode("utf-8")).hexdigest()


def validate_claim(payload: Any) -> dict[str, Any]:
    """Validate a single claim against ds-lite.claim.v1."""
    if not isinstance(payload, dict):
        raise ClaimError("claim must be an object")
    required = {
        "claim_id", "claim_type", "statement", "selector", "evidence_refs",
        "dependence_group", "transformation_chain", "executed_code_ref",
        "verifier", "fidelity", "status", "created_at", "extensions",
    }
    if set(payload) != required:
        raise ClaimError(f"claim must contain exactly {', '.join(sorted(required))}")

    if not isinstance(payload["claim_id"], str) or not ID_RE.fullmatch(payload["claim_id"]):
        raise ClaimError("claim_id must match identifier pattern")

    if payload["claim_type"] not in CLAIM_TYPES:
        raise ClaimError(f"claim_type must be one of {', '.join(sorted(CLAIM_TYPES))}")

    if not isinstance(payload["statement"], str) or not payload["statement"].strip():
        raise ClaimError("statement must be a non-empty string")

    selector = payload["selector"]
    if not isinstance(selector, dict):
        raise ClaimError("selector must be an object")
    if not isinstance(selector.get("type"), str) or not selector["type"].strip():
        raise ClaimError("selector.type must be a non-empty string")
    if not isinstance(selector.get("query"), str) or not selector["query"].strip():
        raise ClaimError("selector.query must be a non-empty string")

    if not isinstance(payload["evidence_refs"], list):
        raise ClaimError("evidence_refs must be a list")
    if not payload["evidence_refs"]:
        raise ClaimError("evidence_refs must be non-empty")
    if not all(isinstance(ref, str) and ref.strip() for ref in payload["evidence_refs"]):
        raise ClaimError("each evidence_ref must be a non-empty string")

    if not isinstance(payload["dependence_group"], str) or not payload["dependence_group"].strip():
        raise ClaimError("dependence_group must be a non-empty string")

    tc = payload["transformation_chain"]
    if not isinstance(tc, list):
        raise ClaimError("transformation_chain must be a list")
    for step in tc:
        if not isinstance(step, dict):
            raise ClaimError("each transformation step must be an object")
        if not isinstance(step.get("operation"), str) or not step["operation"].strip():
            raise ClaimError("transformation step.operation must be non-empty")
        if not isinstance(step.get("input_ref"), str) or not step["input_ref"].strip():
            raise ClaimError("transformation step.input_ref must be non-empty")
        if not isinstance(step.get("output_ref"), str) or not step["output_ref"].strip():
            raise ClaimError("transformation step.output_ref must be non-empty")

    if not isinstance(payload["executed_code_ref"], str):
        raise ClaimError("executed_code_ref must be a string")

    verifier = payload["verifier"]
    if not isinstance(verifier, dict):
        raise ClaimError("verifier must be an object")
    if not isinstance(verifier.get("type"), str) or not verifier["type"].strip():
        raise ClaimError("verifier.type must be a non-empty string")
    if not isinstance(verifier.get("result"), str) or not verifier["result"].strip():
        raise ClaimError("verifier.result must be a non-empty string")

    if payload["fidelity"] not in FIDELITY_LEVELS:
        raise ClaimError(f"fidelity must be one of {', '.join(sorted(FIDELITY_LEVELS))}")

    if payload["status"] not in CLAIM_STATUSES:
        raise ClaimError(f"status must be one of {', '.join(sorted(CLAIM_STATUSES))}")

    if not isinstance(payload["created_at"], str) or not payload["created_at"].strip():
        raise ClaimError("created_at must be a non-empty ISO-8601 string")

    if not isinstance(payload["extensions"], dict):
        raise ClaimError("extensions must be an object")

    # Fidelity constraints
    if payload["fidelity"] == "confirmatory" and payload["status"] == "supported":
        # Confirmatory claims require a pre-registration ref
        if not payload["extensions"].get("pre_registration_ref"):
            raise ClaimError("confirmatory supported claims require extensions.pre_registration_ref")

    return json.loads(json.dumps(payload))


def create_ledger(ledger_id: str, work_unit_id: str, root: str) -> dict[str, Any]:
    """Create a new claim ledger file."""
    if not ID_RE.fullmatch(ledger_id):
        raise ClaimError("ledger_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise ClaimError("work_unit_id must match identifier pattern")

    ledger_path = Path(root) / "research" / "artifacts" / f"claim-ledger-{ledger_id}.json"
    if ledger_path.exists():
        raise ClaimError(f"ledger already exists: {ledger_path}")

    ledger = {
        "schema_version": CLAIM_LEDGER_SCHEMA,
        "ledger_id": ledger_id,
        "work_unit_id": work_unit_id,
        "claims": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return ledger


def append_claim(ledger_path: str, claim: dict[str, Any]) -> dict[str, Any]:
    """Append a validated claim to the ledger."""
    path = Path(ledger_path)
    if not path.exists():
        raise ClaimError(f"ledger not found: {path}")

    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != CLAIM_LEDGER_SCHEMA:
        raise ClaimError("invalid ledger schema")

    validated = validate_claim(claim)
    if validated["status"] != "draft":
        raise ClaimError("new claims must start as draft and be promoted by typed review")

    existing_ids = {c["claim_id"] for c in ledger["claims"]}
    if validated["claim_id"] in existing_ids:
        raise ClaimError(f"claim_id '{validated['claim_id']}' already exists in ledger")

    validated["claim_digest"] = _claim_digest(validated)

    ledger["claims"].append(validated)
    ledger["updated_at"] = _now_iso()
    path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return validated


def supersede_claim(ledger_path: str, old_claim_id: str, new_claim_id: str) -> dict[str, Any]:
    """Mark a claim as superseded by another claim."""
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))

    for claim in ledger["claims"]:
        if claim["claim_id"] == old_claim_id:
            claim["status"] = "superseded"
            claim.setdefault("extensions", {})["superseded_by"] = new_claim_id
            ledger["updated_at"] = _now_iso()
            path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
            return claim
    raise ClaimError(f"claim '{old_claim_id}' not found in ledger")


def promote_claim_from_review(ledger_path: str, claim_id: str, review_path: str) -> dict[str, Any]:
    """Promote a draft claim only after validating a typed review result.

    The review must name the claim in ``extensions.claim_id`` and may only
    inspect evidence already bound to that claim.  A passing/supportable
    review yields ``supported``; a failing/refuted review yields ``contested``.
    Human or inconclusive outcomes are intentionally non-promoting.
    """
    path = Path(ledger_path)
    review_file = Path(review_path)
    if not path.exists():
        raise ClaimError(f"ledger not found: {path}")
    if not review_file.exists():
        raise ClaimError(f"review not found: {review_file}")
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
        review_payload = json.loads(review_file.read_text(encoding="utf-8"))
        review = validate_review_result(review_payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ProtocolError) as exc:
        raise ClaimError(f"invalid review: {exc}") from exc
    if review.get("extensions", {}).get("claim_id") != claim_id:
        raise ClaimError("review extensions.claim_id must match claim_id")

    claim = next((item for item in ledger.get("claims", []) if item.get("claim_id") == claim_id), None)
    if claim is None:
        raise ClaimError(f"claim '{claim_id}' not found in ledger")
    if claim.get("status") != "draft":
        raise ClaimError("only draft claims can be promoted from review")
    claim_refs = set(claim.get("evidence_refs", []))
    reviewed_refs = set(review["reviewed_evidence_refs"])
    if not reviewed_refs.issubset(claim_refs):
        raise ClaimError("reviewed evidence refs must be a subset of claim evidence refs")

    if review["verdict"] == "pass" and review["claim_assessment"] == "supportable":
        target_status = "supported"
    elif review["verdict"] == "fail" and review["claim_assessment"] == "refuted":
        target_status = "contested"
    else:
        raise ClaimError("review outcome is non-promoting")

    review_digest = hashlib.sha256(review_file.read_bytes()).hexdigest()
    extensions = claim.setdefault("extensions", {})
    extensions.update({
        "review_ref": review["review_artifact_ref"],
        "review_sha256": review_digest,
        "review_verdict": review["verdict"],
        "review_claim_assessment": review["claim_assessment"],
    })
    claim["status"] = target_status
    claim["claim_digest"] = _claim_digest(claim)
    ledger["updated_at"] = _now_iso()
    path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return claim


def list_claims(ledger_path: str, status: str | None = None) -> list[dict[str, Any]]:
    """List claims in a ledger, optionally filtered by status."""
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    claims = ledger.get("claims", [])
    if status:
        claims = [c for c in claims if c.get("status") == status]
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim Ledger for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--ledger-id", required=True)
    create_parser.add_argument("--work-unit-id", required=True)
    create_parser.add_argument("--root", required=True)

    append_parser = sub.add_parser("append")
    append_parser.add_argument("--ledger", required=True)
    append_parser.add_argument("--claim", required=True, help="Path to claim JSON file")

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--ledger", required=True)
    list_parser.add_argument("--status", choices=sorted(CLAIM_STATUSES))

    supersede_parser = sub.add_parser("supersede")
    supersede_parser.add_argument("--ledger", required=True)
    supersede_parser.add_argument("--old-id", required=True)
    supersede_parser.add_argument("--new-id", required=True)

    promote_parser = sub.add_parser("promote-from-review")
    promote_parser.add_argument("--ledger", required=True)
    promote_parser.add_argument("--claim-id", required=True)
    promote_parser.add_argument("--review", required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_ledger(args.ledger_id, args.work_unit_id, args.root)
        elif args.command == "append":
            claim = json.loads(Path(args.claim).read_text(encoding="utf-8"))
            result = append_claim(args.ledger, claim)
        elif args.command == "list":
            result = list_claims(args.ledger, getattr(args, "status", None))
        elif args.command == "supersede":
            result = supersede_claim(args.ledger, args.old_id, args.new_id)
        elif args.command == "promote-from-review":
            result = promote_claim_from_review(args.ledger, args.claim_id, args.review)
        else:
            print(json.dumps({"error": f"unknown command: {args.command}"}))
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ClaimError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
