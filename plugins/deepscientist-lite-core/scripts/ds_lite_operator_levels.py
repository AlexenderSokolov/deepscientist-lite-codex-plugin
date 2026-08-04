#!/usr/bin/env python3
"""Operator Levels O0-O7 for DS Lite v6.

Operator grading system from O0 (public read-only) to O7 (irreversible
high-permission action). Each level has independent authorization requirements.

Schema: ds-lite.operator-levels.v1
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

OPERATOR_SCHEMA = "ds-lite.operator-levels.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

OPERATOR_LEVELS = {
    "O0": {"name": "public-read-only", "authorization": "none", "reversible": True},
    "O1": {"name": "authenticated-read-only", "authorization": "login-state", "reversible": True},
    "O2": {"name": "reversible-write", "authorization": "explicit-contract", "reversible": True},
    "O3": {"name": "irreversible-action", "authorization": "human-approval", "reversible": False},
    "O4": {"name": "send-email", "authorization": "human-approval", "reversible": False},
    "O5": {"name": "submit-paper", "authorization": "human-approval", "reversible": False},
    "O6": {"name": "deploy-production", "authorization": "human-approval", "reversible": False},
    "O7": {"name": "irreversible-high-permission", "authorization": "human-approval", "reversible": False},
}


class OperatorError(RuntimeError):
    pass


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_operator_action(document: Any) -> dict[str, Any]:
    """Validate an operator action document."""
    if not isinstance(document, dict):
        raise OperatorError("document must be an object")

    if document.get("schema_version") != OPERATOR_SCHEMA:
        raise OperatorError(f"schema_version must be {OPERATOR_SCHEMA}")

    required = {
        "schema_version", "action_id", "operator_level",
        "action_kind", "target_identity", "authorized_effect_class",
        "payload_digest", "status", "created_at", "extensions",
    }
    missing = required - set(document.keys())
    if missing:
        raise OperatorError(f"missing required fields: {sorted(missing)}")

    if not ID_RE.fullmatch(document["action_id"]):
        raise OperatorError("action_id must match identifier pattern")

    level = document["operator_level"]
    if level not in OPERATOR_LEVELS:
        raise OperatorError(f"operator_level must be one of {sorted(OPERATOR_LEVELS.keys())}")

    return {
        "verdict": "pass",
        "operator_digest": _digest({
            "action_id": document["action_id"],
            "operator_level": level,
            "action_kind": document["action_kind"],
        }),
    }


def check_operator_permission(level: str, action: dict[str, Any]) -> dict[str, Any]:
    """Check if an operator level has permission for an action."""
    if level not in OPERATOR_LEVELS:
        raise OperatorError(f"level must be one of {sorted(OPERATOR_LEVELS.keys())}")

    level_info = OPERATOR_LEVELS[level]
    rule_ids: list[str] = []
    verdict = "pass"

    # Check authorization
    auth_required = level_info["authorization"]
    if auth_required == "human-approval":
        if not action.get("human_approved", False):
            rule_ids.append("human_approval_required")
            verdict = "blocked"

    # Check reversibility for high levels
    if not level_info["reversible"] and action.get("is_reversible", False):
        rule_ids.append("irreversible_action_marked_reversible")
        verdict = "blocked"

    return {
        "verdict": verdict,
        "rule_ids": rule_ids,
        "level": level,
        "level_name": level_info["name"],
        "authorization_required": auth_required,
    }


def create_operator_contract(
    level: str,
    action: dict[str, Any],
    scope: dict[str, Any],
) -> dict[str, Any]:
    """Create an operator contract for a specific action."""
    if level not in OPERATOR_LEVELS:
        raise OperatorError(f"level must be one of {sorted(OPERATOR_LEVELS.keys())}")

    level_info = OPERATOR_LEVELS[level]

    contract = {
        "schema_version": OPERATOR_SCHEMA,
        "operator_level": level,
        "level_name": level_info["name"],
        "authorization_required": level_info["authorization"],
        "is_reversible": level_info["reversible"],
        "action": action,
        "scope": scope,
        "created_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "extensions": {},
    }

    return contract


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Operator Levels O0-O7 for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--document", required=True)

    check_parser = sub.add_parser("check")
    check_parser.add_argument("--level", required=True)
    check_parser.add_argument("--action", required=True, help="Path to action JSON")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            doc = json.loads(open(args.document, encoding="utf-8").read())
            result = validate_operator_action(doc)
        elif args.command == "check":
            action = json.loads(open(args.action, encoding="utf-8").read())
            result = check_operator_permission(args.level, action)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (OperatorError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())