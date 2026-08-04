#!/usr/bin/env python3
"""Factor Card v2 — upgraded creative comparison for DS Lite v6.

Extends v1 with lineage, differentiation axes, recent work, falsification
predictions, signal bindings, and selection rationale. v1 cards remain
read-compatible.

Schema: ds-lite.factor-card.v2
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

FACTOR_CARD_V2_SCHEMA = "ds-lite.factor-card.v2"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
FACTOR_NAMES = frozenset({"novelty", "feasibility", "evidence_strength", "cost", "risk", "alignment"})
FACTOR_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})
CARD_STATUSES = frozenset({"draft", "assessed", "reviewed"})
CARD_DECISIONS = frozenset({"explore", "verify-first", "park", "reject", "needs-human"})
DIFF_AXES = frozenset({"mechanism", "target", "combination", "evidence_claim", "scope", "method"})


class FactorCardError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _card_digest(card: dict[str, Any]) -> str:
    """Compute a stable digest of a card's core fields."""
    core = json.dumps({
        "factor_card_id": card["factor_card_id"],
        "work_unit_id": card["work_unit_id"],
        "subject_ref": card["subject_ref"],
        "decision": card["decision"],
        "factors": [{"name": f["name"], "score": f["score"]} for f in card["factors"]],
    }, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(core.encode("utf-8")).hexdigest()


def validate_factor_card_v2(payload: Any) -> dict[str, Any]:
    """Validate a Factor Card v2 against ds-lite.factor-card.v2."""
    if not isinstance(payload, dict):
        raise FactorCardError("factor card must be an object")

    required = {
        "schema_version", "factor_card_id", "work_unit_id", "profile_id",
        "subject_ref", "status", "decision", "factors", "lineage",
        "differentiation_axes", "recent_work", "falsification_predictions",
        "signal_refs", "selection_rationale", "minimal_test",
        "created_at", "updated_at", "extensions",
    }
    if set(payload) != required:
        raise FactorCardError(f"factor card must contain exactly {', '.join(sorted(required))}")

    if payload["schema_version"] != FACTOR_CARD_V2_SCHEMA:
        raise FactorCardError(f"schema_version must be {FACTOR_CARD_V2_SCHEMA}")

    for field in ("factor_card_id", "work_unit_id", "profile_id"):
        if not isinstance(payload[field], str) or not ID_RE.fullmatch(payload[field]):
            raise FactorCardError(f"{field} must match identifier pattern")

    if payload["factor_card_id"] == payload["work_unit_id"]:
        raise FactorCardError("factor_card_id and work_unit_id must differ")

    if not isinstance(payload["subject_ref"], str) or not payload["subject_ref"].strip():
        raise FactorCardError("subject_ref must be a non-empty string")

    if payload["status"] not in CARD_STATUSES:
        raise FactorCardError(f"status must be one of {', '.join(sorted(CARD_STATUSES))}")

    if payload["decision"] not in CARD_DECISIONS:
        raise FactorCardError(f"decision must be one of {', '.join(sorted(CARD_DECISIONS))}")

    # Validate factors
    factors = payload["factors"]
    if not isinstance(factors, list):
        raise FactorCardError("factors must be a list")
    seen: set[str] = set()
    factor_fields = {"name", "score", "confidence", "evidence_refs", "summary", "uncertainty", "extensions"}
    for index, factor in enumerate(factors):
        if not isinstance(factor, dict) or set(factor) != factor_fields:
            raise FactorCardError(f"factors[{index}] must contain exactly {', '.join(sorted(factor_fields))}")
        name = factor["name"]
        if name not in FACTOR_NAMES:
            raise FactorCardError(f"factors[{index}].name is invalid")
        if name in seen:
            raise FactorCardError(f"factors[{index}].name is duplicated")
        seen.add(name)
        score = factor["score"]
        if score is not None and (not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 4):
            raise FactorCardError(f"factors[{index}].score must be null or 0-4")
        confidence = factor["confidence"]
        if confidence not in FACTOR_CONFIDENCE:
            raise FactorCardError(f"factors[{index}].confidence is invalid")
        if score is None and confidence != "unknown":
            raise FactorCardError("unknown score requires unknown confidence")
        if score is not None and confidence == "unknown":
            raise FactorCardError("scored factor requires non-unknown confidence")
        if not isinstance(factor["evidence_refs"], list):
            raise FactorCardError(f"factors[{index}].evidence_refs must be a list")
        if score is not None and not factor["evidence_refs"]:
            raise FactorCardError(f"factors[{index}] scored factor requires evidence_refs")
        if not isinstance(factor["summary"], str) or not factor["summary"].strip():
            raise FactorCardError(f"factors[{index}].summary must be non-empty")
        if not isinstance(factor["uncertainty"], list):
            raise FactorCardError(f"factors[{index}].uncertainty must be a list")
        if not isinstance(factor["extensions"], dict):
            raise FactorCardError(f"factors[{index}].extensions must be an object")
    if seen != FACTOR_NAMES:
        raise FactorCardError("each required factor must appear exactly once")

    # Validate lineage
    lineage = payload["lineage"]
    if not isinstance(lineage, dict):
        raise FactorCardError("lineage must be an object")
    if not isinstance(lineage.get("source_type"), str) or lineage["source_type"] not in ("novel", "derived", "adapted", "combined"):
        raise FactorCardError("lineage.source_type must be novel, derived, adapted, or combined")
    if not isinstance(lineage.get("parent_refs"), list):
        raise FactorCardError("lineage.parent_refs must be a list")
    if lineage["source_type"] in ("derived", "adapted", "combined") and not lineage["parent_refs"]:
        raise FactorCardError(f"lineage.source_type '{lineage['source_type']}' requires non-empty parent_refs")

    # Validate differentiation axes
    diff_axes = payload["differentiation_axes"]
    if not isinstance(diff_axes, list):
        raise FactorCardError("differentiation_axes must be a list")
    for axis in diff_axes:
        if not isinstance(axis, dict):
            raise FactorCardError("each differentiation axis must be an object")
        if axis.get("axis") not in DIFF_AXES:
            raise FactorCardError(f"differentiation axis must be one of {', '.join(sorted(DIFF_AXES))}")
        if not isinstance(axis.get("description"), str) or not axis["description"].strip():
            raise FactorCardError("differentiation axis.description must be non-empty")
        if not isinstance(axis.get("closest_known"), str):
            raise FactorCardError("differentiation axis.closest_known must be a string")

    # Validate recent work
    recent_work = payload["recent_work"]
    if not isinstance(recent_work, list):
        raise FactorCardError("recent_work must be a list")
    for work in recent_work:
        if not isinstance(work, dict):
            raise FactorCardError("each recent_work entry must be an object")
        if not isinstance(work.get("ref"), str) or not work["ref"].strip():
            raise FactorCardError("recent_work entry.ref must be non-empty")
        if not isinstance(work.get("relation"), str) or work["relation"] not in ("same", "adjacent", "competing", "precedent"):
            raise FactorCardError("recent_work entry.relation must be same, adjacent, competing, or precedent")

    # Validate falsification predictions
    predictions = payload["falsification_predictions"]
    if not isinstance(predictions, list) or not predictions:
        raise FactorCardError("falsification_predictions must be a non-empty list")
    for pred in predictions:
        if not isinstance(pred, dict):
            raise FactorCardError("each falsification prediction must be an object")
        if not isinstance(pred.get("prediction"), str) or not pred["prediction"].strip():
            raise FactorCardError("falsification prediction.prediction must be non-empty")
        if not isinstance(pred.get("falsifier"), str) or not pred["falsifier"].strip():
            raise FactorCardError("falsification prediction.falsifier must be non-empty")
        if not isinstance(pred.get("expected_outcome"), str) or pred["expected_outcome"] not in ("confirmed", "refuted", "inconclusive"):
            raise FactorCardError("falsification prediction.expected_outcome must be confirmed, refuted, or inconclusive")

    # Validate signal refs
    if not isinstance(payload["signal_refs"], list):
        raise FactorCardError("signal_refs must be a list")

    # Validate selection rationale
    if not isinstance(payload["selection_rationale"], str):
        raise FactorCardError("selection_rationale must be a string")

    # Validate minimal test
    minimal_test = payload["minimal_test"]
    if not isinstance(minimal_test, dict):
        raise FactorCardError("minimal_test must be an object")
    minimal_fields = {"question", "method", "expected_evidence", "resource_limits", "stop_condition", "extensions"}
    if set(minimal_test) != minimal_fields:
        raise FactorCardError("minimal_test has unsupported or missing fields")
    for field in ("question", "method", "stop_condition"):
        if not isinstance(minimal_test[field], str) or not minimal_test[field].strip():
            raise FactorCardError(f"minimal_test.{field} must be non-empty")

    # Validate timestamps
    for field in ("created_at", "updated_at"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise FactorCardError(f"{field} must be a non-empty ISO-8601 string")

    if not isinstance(payload["extensions"], dict):
        raise FactorCardError("extensions must be an object")

    return json.loads(json.dumps(payload))


def main() -> int:
    parser = argparse.ArgumentParser(description="Factor Card v2 validator for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--path", required=True, help="Path to factor card v2 JSON")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
            validated = validate_factor_card_v2(payload)
            digest = _card_digest(validated)
            print(json.dumps({
                "status": "valid",
                "schema": FACTOR_CARD_V2_SCHEMA,
                "card_digest": digest,
                "factor_card_id": validated["factor_card_id"],
            }, ensure_ascii=True, indent=2))
            return 0
        else:
            print(json.dumps({"error": f"unknown command: {args.command}"}))
            return 1
    except (FactorCardError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
