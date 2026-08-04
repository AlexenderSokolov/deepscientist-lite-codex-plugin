#!/usr/bin/env python3
"""Discovery Frontier — deterministic projection of candidate routes for DS Lite v6.

The Frontier is a read-only projection derived from the Research Signal Ledger
and Factor Cards. It has no execution authority. Manual edits to the Frontier
cannot activate Graph routes.

Schema: ds-lite.frontier.v1
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

FRONTIER_SCHEMA = "ds-lite.frontier.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
FRONTIER_STATUSES = frozenset({"open", "converging", "exhausted", "superseded"})
CANDIDATE_STATUSES = frozenset({"proposed", "assessed", "selected", "parked", "rejected"})


class FrontierError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _candidate_digest(candidate: dict[str, Any]) -> str:
    """Compute a stable digest of a candidate's core fields."""
    core = json.dumps({
        "candidate_id": candidate["candidate_id"],
        "hypothesis": candidate["hypothesis"],
        "mechanism": candidate["mechanism"],
        "differentiation": candidate["differentiation"],
        "signal_refs": sorted(candidate["signal_refs"]),
        "factor_card_ref": candidate["factor_card_ref"],
    }, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(core.encode("utf-8")).hexdigest()


def validate_candidate(payload: Any) -> dict[str, Any]:
    """Validate a frontier candidate."""
    if not isinstance(payload, dict):
        raise FrontierError("candidate must be an object")
    required = {
        "candidate_id", "hypothesis", "mechanism", "differentiation",
        "signal_refs", "factor_card_ref", "status", "selection_rationale",
        "falsification_prediction", "minimal_test_ref", "extensions",
    }
    if set(payload) != required:
        raise FrontierError(f"candidate must contain exactly {', '.join(sorted(required))}")

    if not isinstance(payload["candidate_id"], str) or not ID_RE.fullmatch(payload["candidate_id"]):
        raise FrontierError("candidate_id must match identifier pattern")

    for field in ("hypothesis", "mechanism", "differentiation"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise FrontierError(f"{field} must be a non-empty string")

    if not isinstance(payload["signal_refs"], list):
        raise FrontierError("signal_refs must be a list")
    if not all(isinstance(ref, str) and ref.strip() for ref in payload["signal_refs"]):
        raise FrontierError("each signal_ref must be a non-empty string")

    if not isinstance(payload["factor_card_ref"], str) or not payload["factor_card_ref"].strip():
        raise FrontierError("factor_card_ref must be a non-empty string")

    if payload["status"] not in CANDIDATE_STATUSES:
        raise FrontierError(f"status must be one of {', '.join(sorted(CANDIDATE_STATUSES))}")

    if not isinstance(payload["selection_rationale"], str):
        raise FrontierError("selection_rationale must be a string")

    if not isinstance(payload["falsification_prediction"], dict):
        raise FrontierError("falsification_prediction must be an object")
    fp = payload["falsification_prediction"]
    if not isinstance(fp.get("prediction"), str) or not fp["prediction"].strip():
        raise FrontierError("falsification_prediction.prediction must be non-empty")
    if not isinstance(fp.get("falsifier"), str) or not fp["falsifier"].strip():
        raise FrontierError("falsification_prediction.falsifier must be non-empty")

    if not isinstance(payload["minimal_test_ref"], str):
        raise FrontierError("minimal_test_ref must be a string")

    if not isinstance(payload["extensions"], dict):
        raise FrontierError("extensions must be an object")

    return json.loads(json.dumps(payload))


def create_frontier(frontier_id: str, work_unit_id: str, root: str) -> dict[str, Any]:
    """Create a new empty frontier file."""
    if not ID_RE.fullmatch(frontier_id):
        raise FrontierError("frontier_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise FrontierError("work_unit_id must match identifier pattern")

    frontier_path = Path(root) / "research" / "artifacts" / f"discovery-frontier-{frontier_id}.json"
    if frontier_path.exists():
        raise FrontierError(f"frontier already exists: {frontier_path}")

    frontier = {
        "schema_version": FRONTIER_SCHEMA,
        "frontier_id": frontier_id,
        "work_unit_id": work_unit_id,
        "status": "open",
        "candidates": [],
        "source_signal_ledger": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    frontier_path.parent.mkdir(parents=True, exist_ok=True)
    frontier_path.write_text(json.dumps(frontier, ensure_ascii=True, indent=2), encoding="utf-8")
    return frontier


def add_candidate(frontier_path: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Add a validated candidate to the frontier."""
    path = Path(frontier_path)
    if not path.exists():
        raise FrontierError(f"frontier not found: {path}")

    frontier = json.loads(path.read_text(encoding="utf-8"))
    if frontier.get("schema_version") != FRONTIER_SCHEMA:
        raise FrontierError("invalid frontier schema")
    if frontier.get("status") == "exhausted":
        raise FrontierError("frontier is exhausted; cannot add candidates")

    validated = validate_candidate(candidate)

    existing_ids = {c["candidate_id"] for c in frontier["candidates"]}
    if validated["candidate_id"] in existing_ids:
        raise FrontierError(f"candidate_id '{validated['candidate_id']}' already exists")

    validated["candidate_digest"] = _candidate_digest(validated)

    frontier["candidates"].append(validated)
    frontier["updated_at"] = _now_iso()
    path.write_text(json.dumps(frontier, ensure_ascii=True, indent=2), encoding="utf-8")
    return validated


def select_candidate(frontier_path: str, candidate_id: str, rationale: str) -> dict[str, Any]:
    """Mark a candidate as selected. Only one candidate can be selected at a time."""
    path = Path(frontier_path)
    frontier = json.loads(path.read_text(encoding="utf-8"))

    # Check if any candidate is already selected
    for c in frontier["candidates"]:
        if c.get("status") == "selected" and c["candidate_id"] != candidate_id:
            raise FrontierError(f"another candidate '{c['candidate_id']}' is already selected")

    for c in frontier["candidates"]:
        if c["candidate_id"] == candidate_id:
            c["status"] = "selected"
            c["selection_rationale"] = rationale
            frontier["status"] = "converging"
            frontier["updated_at"] = _now_iso()
            path.write_text(json.dumps(frontier, ensure_ascii=True, indent=2), encoding="utf-8")
            return c
    raise FrontierError(f"candidate '{candidate_id}' not found")


def project_frontier(frontier_path: str) -> dict[str, Any]:
    """Return a read-only projection of the frontier."""
    path = Path(frontier_path)
    frontier = json.loads(path.read_text(encoding="utf-8"))

    active = [c for c in frontier["candidates"] if c["status"] in ("proposed", "assessed", "selected")]
    parked = [c for c in frontier["candidates"] if c["status"] == "parked"]
    rejected = [c for c in frontier["candidates"] if c["status"] == "rejected"]

    return {
        "schema_version": "ds-lite.frontier-projection.v1",
        "frontier_id": frontier["frontier_id"],
        "work_unit_id": frontier["work_unit_id"],
        "status": frontier["status"],
        "active_count": len(active),
        "parked_count": len(parked),
        "rejected_count": len(rejected),
        "selected_candidate": next((c["candidate_id"] for c in active if c["status"] == "selected"), None),
        "candidates": active,
        "parked": parked,
        "rejected": rejected,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discovery Frontier for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--frontier-id", required=True)
    create_parser.add_argument("--work-unit-id", required=True)
    create_parser.add_argument("--root", required=True)

    add_parser = sub.add_parser("add-candidate")
    add_parser.add_argument("--frontier", required=True)
    add_parser.add_argument("--candidate", required=True, help="Path to candidate JSON")

    select_parser = sub.add_parser("select")
    select_parser.add_argument("--frontier", required=True)
    select_parser.add_argument("--candidate-id", required=True)
    select_parser.add_argument("--rationale", required=True)

    project_parser = sub.add_parser("project")
    project_parser.add_argument("--frontier", required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_frontier(args.frontier_id, args.work_unit_id, args.root)
        elif args.command == "add-candidate":
            candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
            result = add_candidate(args.frontier, candidate)
        elif args.command == "select":
            result = select_candidate(args.frontier, args.candidate_id, args.rationale)
        elif args.command == "project":
            result = project_frontier(args.frontier)
        else:
            print(json.dumps({"error": f"unknown command: {args.command}"}))
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (FrontierError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
