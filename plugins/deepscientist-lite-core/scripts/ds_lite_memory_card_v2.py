#!/usr/bin/env python3
"""Memory Card v2 for DS Lite v6.

A reviewed project-level memory card. Schema includes schema_version,
card_id, work_unit_id, layer, facts, decisions, uncertainties, lineage,
extensions.

Schema: ds-lite.memory-card-v2.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

MEMORY_CARD_SCHEMA = "ds-lite.memory-card-v2.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

VALID_LAYERS = frozenset({"M0", "M1", "M2", "M3", "M4"})
CARD_STATUSES = frozenset({"draft", "reviewed", "approved", "superseded", "retracted"})


class MemoryCardError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_memory_card_v2(document: Any) -> dict[str, Any]:
    """Validate a Memory Card v2 document."""
    if not isinstance(document, dict):
        raise MemoryCardError("document must be an object")

    if document.get("schema_version") != MEMORY_CARD_SCHEMA:
        raise MemoryCardError(f"schema_version must be {MEMORY_CARD_SCHEMA}")

    required = {
        "schema_version", "card_id", "work_unit_id", "layer",
        "facts", "decisions", "uncertainties", "lineage",
        "status", "created_at", "extensions",
    }
    missing = required - set(document.keys())
    if missing:
        raise MemoryCardError(f"missing required fields: {sorted(missing)}")

    if not ID_RE.fullmatch(document["card_id"]):
        raise MemoryCardError("card_id must match identifier pattern")

    if not ID_RE.fullmatch(document["work_unit_id"]):
        raise MemoryCardError("work_unit_id must match identifier pattern")

    if document["layer"] not in VALID_LAYERS:
        raise MemoryCardError(f"layer must be one of {sorted(VALID_LAYERS)}")

    if not isinstance(document["facts"], list):
        raise MemoryCardError("facts must be a list")

    if not isinstance(document["decisions"], list):
        raise MemoryCardError("decisions must be a list")

    if not isinstance(document["uncertainties"], list):
        raise MemoryCardError("uncertainties must be a list")

    if not isinstance(document["lineage"], dict):
        raise MemoryCardError("lineage must be an object")

    if document["status"] not in CARD_STATUSES:
        raise MemoryCardError(f"status must be one of {sorted(CARD_STATUSES)}")

    # Compute card digest
    card_data = {
        "card_id": document["card_id"],
        "work_unit_id": document["work_unit_id"],
        "layer": document["layer"],
        "facts": document["facts"],
        "decisions": document["decisions"],
    }
    card_digest = _digest(card_data)

    return {
        "verdict": "pass",
        "card_digest": card_digest,
    }


def create_memory_card(
    card_id: str,
    work_unit_id: str,
    layer: str,
    facts: list[str],
    decisions: list[str],
    uncertainties: list[str] | None = None,
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a Memory Card v2 document."""
    if not ID_RE.fullmatch(card_id):
        raise MemoryCardError("card_id must match identifier pattern")
    if not ID_RE.fullmatch(work_unit_id):
        raise MemoryCardError("work_unit_id must match identifier pattern")
    if layer not in VALID_LAYERS:
        raise MemoryCardError(f"layer must be one of {sorted(VALID_LAYERS)}")

    now = _now_iso()
    document = {
        "schema_version": MEMORY_CARD_SCHEMA,
        "card_id": card_id,
        "work_unit_id": work_unit_id,
        "layer": layer,
        "facts": facts,
        "decisions": decisions,
        "uncertainties": uncertainties or [],
        "lineage": lineage or {"source_type": "novel", "parent_refs": []},
        "status": "draft",
        "created_at": now,
        "extensions": {},
    }
    return document


def supersede_memory_card(old_id: str, new_id: str) -> dict[str, Any]:
    """Mark a memory card as superseded by another."""
    if not ID_RE.fullmatch(old_id):
        raise MemoryCardError("old_id must match identifier pattern")
    if not ID_RE.fullmatch(new_id):
        raise MemoryCardError("new_id must match identifier pattern")

    return {
        "old_card_id": old_id,
        "new_card_id": new_id,
        "supersede_status": "superseded",
        "superseded_at": _now_iso(),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Memory Card v2 for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--document", required=True)

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_memory_card_v2(doc)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (MemoryCardError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())