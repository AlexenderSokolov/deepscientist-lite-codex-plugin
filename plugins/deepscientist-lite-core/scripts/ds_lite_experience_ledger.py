#!/usr/bin/env python3
"""Experience Ledger for DS Lite v6.

Records incidents, lessons, guards, and skill change proposals from
execution experience. Experience only forms Incident, Lesson, Guard or
Skill change proposal; may not auto-rewrite authoritative Skill.

Schema: ds-lite.experience-ledger.v1
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

EXPERIENCE_SCHEMA = "ds-lite.experience-ledger.v1"
ENTRY_SCHEMA = "ds-lite.experience-entry.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

EXPERIENCE_TYPES = frozenset({
    "incident", "lesson", "guard", "skill-proposal",
})

ENTRY_STATUSES = frozenset({
    "draft", "pending-review", "approved", "rejected", "applied",
})

INCIDENT_SEVERITIES = frozenset({
    "blocker", "critical", "major", "minor", "info",
})

GUARD_TYPES = frozenset({
    "precondition", "invariant", "postcondition", "stop-condition",
})


class ExperienceError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_experience_entry(entry: Any) -> dict[str, Any]:
    """Validate an experience entry."""
    if not isinstance(entry, dict):
        raise ExperienceError("entry must be an object")

    if entry.get("schema_version") != ENTRY_SCHEMA:
        raise ExperienceError(f"schema_version must be {ENTRY_SCHEMA}")

    required = {
        "schema_version", "entry_id", "experience_type", "title",
        "description", "trigger_conditions", "evidence_refs",
        "status", "created_at", "extensions",
    }
    missing = required - set(entry.keys())
    if missing:
        raise ExperienceError(f"missing required fields: {sorted(missing)}")

    if not ID_RE.fullmatch(entry["entry_id"]):
        raise ExperienceError("entry_id must match identifier pattern")

    if entry["experience_type"] not in EXPERIENCE_TYPES:
        raise ExperienceError(f"experience_type must be one of {sorted(EXPERIENCE_TYPES)}")

    if not isinstance(entry["title"], str) or not entry["title"].strip():
        raise ExperienceError("title must be a non-empty string")

    if not isinstance(entry["description"], str) or not entry["description"].strip():
        raise ExperienceError("description must be a non-empty string")

    if not isinstance(entry["trigger_conditions"], list):
        raise ExperienceError("trigger_conditions must be a list")

    if not isinstance(entry["evidence_refs"], list):
        raise ExperienceError("evidence_refs must be a list")

    if entry["status"] not in ENTRY_STATUSES:
        raise ExperienceError(f"status must be one of {sorted(ENTRY_STATUSES)}")

    # Type-specific validation
    if entry["experience_type"] == "incident":
        ext = entry.get("extensions", {})
        if ext.get("severity") not in INCIDENT_SEVERITIES:
            raise ExperienceError(f"extensions.severity must be one of {sorted(INCIDENT_SEVERITIES)}")

    if entry["experience_type"] == "guard":
        ext = entry.get("extensions", {})
        if ext.get("guard_type") not in GUARD_TYPES:
            raise ExperienceError(f"extensions.guard_type must be one of {sorted(GUARD_TYPES)}")

    return json.loads(json.dumps(entry))


def create_ledger(ledger_id: str, project_id: str, root: str) -> dict[str, Any]:
    """Create a new experience ledger file."""
    if not ID_RE.fullmatch(ledger_id):
        raise ExperienceError("ledger_id must match identifier pattern")
    if not ID_RE.fullmatch(project_id):
        raise ExperienceError("project_id must match identifier pattern")

    ledger_path = Path(root) / "research" / "artifacts" / f"experience-ledger-{ledger_id}.json"
    if ledger_path.exists():
        raise ExperienceError(f"ledger already exists: {ledger_path}")

    ledger = {
        "schema_version": EXPERIENCE_SCHEMA,
        "ledger_id": ledger_id,
        "project_id": project_id,
        "entries": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return ledger


def append_entry(ledger_path: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Append a validated experience entry to the ledger."""
    path = Path(ledger_path)
    if not path.exists():
        raise ExperienceError(f"ledger not found: {path}")

    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != EXPERIENCE_SCHEMA:
        raise ExperienceError("invalid ledger schema")

    validated = validate_experience_entry(entry)

    # Check for duplicate entry_id
    existing_ids = {e["entry_id"] for e in ledger["entries"]}
    if validated["entry_id"] in existing_ids:
        raise ExperienceError(f"entry_id '{validated['entry_id']}' already exists in ledger")

    # Compute and attach digest
    validated["entry_digest"] = _digest({
        "entry_id": validated["entry_id"],
        "experience_type": validated["experience_type"],
        "title": validated["title"],
        "description": validated["description"],
    })

    ledger["entries"].append(validated)
    ledger["updated_at"] = _now_iso()
    path.write_text(json.dumps(ledger, ensure_ascii=True, indent=2), encoding="utf-8")
    return validated


def record_experience(
    experience_type: str,
    title: str,
    description: str,
    trigger_conditions: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an experience entry record.

    Experience only forms Incident, Lesson, Guard or Skill change proposal;
    may not auto-rewrite authoritative Skill.
    """
    if experience_type not in EXPERIENCE_TYPES:
        raise ExperienceError(f"experience_type must be one of {sorted(EXPERIENCE_TYPES)}")

    timestamp = _now_iso().lower().replace(":", "").replace("-", "")
    entry_id = f"exp-{experience_type}-{timestamp}"
    # Truncate to fit ID_RE
    entry_id = entry_id[:80]

    entry = {
        "schema_version": ENTRY_SCHEMA,
        "entry_id": entry_id,
        "experience_type": experience_type,
        "title": title,
        "description": description,
        "trigger_conditions": trigger_conditions or [],
        "evidence_refs": evidence_refs or [],
        "status": "draft",
        "created_at": _now_iso(),
        "extensions": extensions or {},
    }
    return entry


def propose_skill_change(
    lesson_entry: dict[str, Any],
    proposed_change: str,
    rationale: str,
) -> dict[str, Any]:
    """Propose a skill change from a lesson.

    Key rule: Experience does not auto-rewrite authoritative Skill.
    The proposal must be pending_review and auto_apply must be False.
    """
    if not isinstance(lesson_entry, dict):
        raise ExperienceError("lesson_entry must be an object")
    if lesson_entry.get("experience_type") != "lesson":
        raise ExperienceError("lesson_entry must be of experience_type 'lesson'")

    proposal = {
        "schema_version": "ds-lite.skill-change-proposal.v1",
        "proposal_id": f"proposal-{lesson_entry.get('entry_id', 'unknown')}",
        "source_lesson_id": lesson_entry.get("entry_id", ""),
        "proposed_change": proposed_change,
        "rationale": rationale,
        "state": "pending_review",
        "auto_apply": False,
        "created_at": _now_iso(),
        "extensions": {},
    }
    return proposal


def list_entries(ledger_path: str, experience_type: str | None = None) -> list[dict[str, Any]]:
    """List entries in a ledger, optionally filtered by experience_type."""
    path = Path(ledger_path)
    ledger = json.loads(path.read_text(encoding="utf-8"))
    entries = ledger.get("entries", [])
    if experience_type:
        entries = [e for e in entries if e.get("experience_type") == experience_type]
    return entries


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Experience Ledger for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--ledger-id", required=True)
    create_parser.add_argument("--project-id", required=True)
    create_parser.add_argument("--root", required=True)

    append_parser = sub.add_parser("append")
    append_parser.add_argument("--ledger", required=True)
    append_parser.add_argument("--entry", required=True, help="Path to entry JSON")

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--ledger", required=True)
    list_parser.add_argument("--type", choices=sorted(EXPERIENCE_TYPES))

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_ledger(args.ledger_id, args.project_id, args.root)
        elif args.command == "append":
            entry = json.loads(open(args.entry, encoding="utf-8").read())
            result = append_entry(args.ledger, entry)
        elif args.command == "list":
            result = list_entries(args.ledger, getattr(args, "type", None))
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ExperienceError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())