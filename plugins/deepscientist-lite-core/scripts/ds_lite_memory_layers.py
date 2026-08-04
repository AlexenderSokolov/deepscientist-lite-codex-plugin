#!/usr/bin/env python3
"""Memory Layers M0-M4 for DS Lite v6.

Five-layer semantic memory, each with independent write permission and
expiry condition. Experience (M4) cannot auto-promote to project fact (M0).

Schema: ds-lite.memory-layers.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

MEMORY_LAYERS_SCHEMA = "ds-lite.memory-layers.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

LAYERS = {
    "M0": {"name": "project-stable-goals", "write_permission": "human", "expiry": "project_close"},
    "M1": {"name": "current-status", "write_permission": "projection", "expiry": "status_change"},
    "M2": {"name": "work-units", "write_permission": "frozen_receipt", "expiry": "task_complete"},
    "M3": {"name": "evidence-and-claims", "write_permission": "append_revision", "expiry": "refuted"},
    "M4": {"name": "experience-and-lessons", "write_permission": "incident_lesson_guard_skill_proposal", "expiry": "superseded"},
}

ENTRY_STATUSES = frozenset({"active", "superseded", "expired", "retracted"})
ENTRY_TYPES = frozenset({
    "goal", "constraint", "fact", "decision", "hypothesis",
    "evidence", "claim", "lesson", "guard", "incident", "skill-proposal",
})

# Which entry types are allowed in each layer
LAYER_ALLOWED_TYPES = {
    "M0": {"goal", "constraint"},
    "M1": {"fact", "decision"},
    "M2": {"fact", "decision"},
    "M3": {"evidence", "claim", "hypothesis"},
    "M4": {"lesson", "guard", "incident", "skill-proposal"},
}


class MemoryLayerError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_memory_layer(document: Any) -> dict[str, Any]:
    """Validate a memory layer document."""
    if not isinstance(document, dict):
        raise MemoryLayerError("document must be an object")

    if document.get("schema_version") != MEMORY_LAYERS_SCHEMA:
        raise MemoryLayerError(f"schema_version must be {MEMORY_LAYERS_SCHEMA}")

    layer = document.get("layer", "")
    if layer not in LAYERS:
        raise MemoryLayerError(f"layer must be one of {sorted(LAYERS.keys())}")

    entries = document.get("entries", [])
    if not isinstance(entries, list):
        raise MemoryLayerError("entries must be a list")

    rule_ids: list[str] = []
    verdict = "pass"

    for i, entry in enumerate(entries):
        entry_result = validate_memory_entry(entry, layer)
        if entry_result["verdict"] == "blocked":
            rule_ids.append(f"entry_{i}_blocked")
            verdict = "blocked"

    # Compute layer digest
    layer_data = {
        "layer": layer,
        "entry_count": len(entries),
        "entry_ids": sorted([e.get("entry_id", "") for e in entries if isinstance(e, dict)]),
    }
    layer_digest = _digest(layer_data)

    return {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "layer_digest": layer_digest,
    }


def validate_memory_entry(entry: Any, layer: str) -> dict[str, Any]:
    """Validate a single memory entry against its layer's rules."""
    if not isinstance(entry, dict):
        raise MemoryLayerError("entry must be an object")

    if not ID_RE.fullmatch(entry.get("entry_id", "")):
        raise MemoryLayerError("entry_id must match identifier pattern")

    entry_type = entry.get("entry_type", "")
    if entry_type not in ENTRY_TYPES:
        raise MemoryLayerError(f"entry_type must be one of {sorted(ENTRY_TYPES)}")

    allowed_types = LAYER_ALLOWED_TYPES.get(layer, set())
    if entry_type not in allowed_types:
        return {
            "verdict": "blocked",
            "rule_ids": [f"entry_type_{entry_type}_not_allowed_in_{layer}"],
        }

    if not isinstance(entry.get("statement"), str) or not entry["statement"].strip():
        raise MemoryLayerError("statement must be a non-empty string")

    if entry.get("status", "active") not in ENTRY_STATUSES:
        raise MemoryLayerError(f"status must be one of {sorted(ENTRY_STATUSES)}")

    return {"verdict": "pass", "rule_ids": []}


def create_memory_layer(project_root: str, layer: str) -> dict[str, Any]:
    """Create a new memory layer file."""
    if layer not in LAYERS:
        raise MemoryLayerError(f"layer must be one of {sorted(LAYERS.keys())}")

    layer_info = LAYERS[layer]
    layer_path = Path(project_root) / "research" / "memory" / f"{layer}-{layer_info['name']}.json"

    if layer_path.exists():
        raise MemoryLayerError(f"layer already exists: {layer_path}")

    layer_path.parent.mkdir(parents=True, exist_ok=True)

    document = {
        "schema_version": MEMORY_LAYERS_SCHEMA,
        "layer": layer,
        "layer_name": layer_info["name"],
        "write_permission": layer_info["write_permission"],
        "expiry_condition": layer_info["expiry"],
        "entries": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    layer_path.write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding="utf-8")
    return document


def record_memory_entry(layer_path: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Record a memory entry in a layer."""
    path = Path(layer_path)
    if not path.exists():
        raise MemoryLayerError(f"layer not found: {path}")

    document = json.loads(path.read_text(encoding="utf-8"))
    layer = document.get("layer", "")

    # Validate entry
    validation = validate_memory_entry(entry, layer)
    if validation["verdict"] == "blocked":
        raise MemoryLayerError(f"entry validation failed: {validation['rule_ids']}")

    # Check for duplicate entry_id
    existing_ids = {e["entry_id"] for e in document["entries"]}
    if entry["entry_id"] in existing_ids:
        raise MemoryLayerError(f"entry_id '{entry['entry_id']}' already exists in layer")

    # Add timestamp if not present
    if "created_at" not in entry:
        entry["created_at"] = _now_iso()

    document["entries"].append(entry)
    document["updated_at"] = _now_iso()

    path.write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding="utf-8")
    return entry


def promote_memory(
    source_layer: str,
    target_layer: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """Attempt to promote a memory entry from one layer to another.

    Key rule: M4 (experience) cannot auto-promote to M0 (project facts).
    """
    if source_layer not in LAYERS:
        raise MemoryLayerError(f"source_layer must be one of {sorted(LAYERS.keys())}")
    if target_layer not in LAYERS:
        raise MemoryLayerError(f"target_layer must be one of {sorted(LAYERS.keys())}")

    rule_ids: list[str] = []
    verdict = "pass"

    # Rule: M4 experience cannot auto-promote to M0
    if source_layer == "M4" and target_layer == "M0":
        rule_ids.append("m4_experience_cannot_auto_promote_to_m0")
        verdict = "blocked"

    # Rule: cannot promote to M0 without human approval
    if target_layer == "M0":
        rule_ids.append("m0_requires_human_approval")
        verdict = "blocked"

    # Rule: downward promotion (higher to lower layer) is not allowed
    source_num = int(source_layer[1])
    target_num = int(target_layer[1])
    if target_num < source_num:
        rule_ids.append("downward_promotion_not_allowed")
        verdict = "blocked"

    # Rule: entry type must be allowed in target layer
    entry_type = entry.get("entry_type", "")
    allowed_types = LAYER_ALLOWED_TYPES.get(target_layer, set())
    if entry_type not in allowed_types:
        rule_ids.append(f"entry_type_{entry_type}_not_allowed_in_{target_layer}")
        verdict = "blocked"

    return {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "source_layer": source_layer,
        "target_layer": target_layer,
    }


def get_layer_digest(layer_path: str) -> str:
    """Compute a stable digest for a memory layer."""
    path = Path(layer_path)
    document = json.loads(path.read_text(encoding="utf-8"))

    layer_data = {
        "layer": document.get("layer", ""),
        "entry_count": len(document.get("entries", [])),
        "entry_ids": sorted([e.get("entry_id", "") for e in document.get("entries", []) if isinstance(e, dict)]),
    }
    return _digest(layer_data)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Memory Layers M0-M4 for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--root", required=True)
    create_parser.add_argument("--layer", required=True, choices=sorted(LAYERS.keys()))

    record_parser = sub.add_parser("record")
    record_parser.add_argument("--layer-path", required=True)
    record_parser.add_argument("--entry", required=True, help="Path to entry JSON")

    promote_parser = sub.add_parser("promote")
    promote_parser.add_argument("--source", required=True)
    promote_parser.add_argument("--target", required=True)
    promote_parser.add_argument("--entry", required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_memory_layer(args.root, args.layer)
        elif args.command == "record":
            entry = json.loads(open(args.entry, encoding="utf-8").read())
            result = record_memory_entry(args.layer_path, entry)
        elif args.command == "promote":
            entry = json.loads(open(args.entry, encoding="utf-8").read())
            result = promote_memory(args.source, args.target, entry)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (MemoryLayerError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())