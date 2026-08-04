#!/usr/bin/env python3
"""Task Router for DS Lite v6.

Selects the minimal sufficient Skill combination based on task kind.
Task kinds: diagnostic, exploratory, pilot, confirmatory,
systematic-review, engineering, replication.

Schema: ds-lite.task-router.v1
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

TASK_ROUTER_SCHEMA = "ds-lite.task-router.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

TASK_KINDS = frozenset({
    "diagnostic", "exploratory", "pilot", "confirmatory",
    "systematic-review", "engineering", "replication",
})

# Core skill mapping by task kind
TASK_SKILL_MAP = {
    "diagnostic": ["ds-lite-intake", "ds-lite-scout", "ds-lite-experiment", "ds-lite-review"],
    "exploratory": ["ds-lite-intake", "ds-lite-scout", "ds-lite-idea", "ds-lite-experiment"],
    "pilot": ["ds-lite-intake", "ds-lite-scout", "ds-lite-idea", "ds-lite-experiment", "ds-lite-review"],
    "confirmatory": ["ds-lite-intake", "ds-lite-scout", "ds-lite-idea", "ds-lite-experiment", "ds-lite-review", "ds-lite-analysis-write"],
    "systematic-review": ["ds-lite-intake", "ds-lite-scout", "ds-lite-review", "ds-lite-analysis-write"],
    "engineering": ["ds-lite-intake", "ds-lite-experiment", "ds-lite-review", "ds-lite-analysis-write"],
    "replication": ["ds-lite-intake", "ds-lite-scout", "ds-lite-experiment", "ds-lite-review"],
}


class TaskRouterError(RuntimeError):
    pass


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def route_task(task_kind: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route a task to the appropriate Skill combination.

    Returns a TaskRoute with:
    - task_kind: str
    - skills: list of skill names
    - routing_reason: str
    - task_digest: str
    """
    if task_kind not in TASK_KINDS:
        raise TaskRouterError(f"task_kind must be one of {sorted(TASK_KINDS)}")

    skills = TASK_SKILL_MAP.get(task_kind, [])

    # Context-based adjustments
    ctx = context or {}
    if ctx.get("needs_writing", False) and "ds-lite-analysis-write" not in skills:
        skills.append("ds-lite-analysis-write")

    if ctx.get("needs_iteration", False) and "ds-lite-iterate" not in skills:
        skills.append("ds-lite-iterate")

    if ctx.get("needs_coordination", False) and "ds-lite-coordinate" not in skills:
        skills.append("ds-lite-coordinate")

    reason = f"Task kind '{task_kind}' requires skills: {', '.join(skills)}"

    task_data = {
        "task_kind": task_kind,
        "skills": skills,
        "context": ctx,
    }

    return {
        "schema_version": TASK_ROUTER_SCHEMA,
        "task_kind": task_kind,
        "skills": skills,
        "routing_reason": reason,
        "task_digest": _digest(task_data),
        "context": ctx,
    }


def select_minimal_sufficient_combination(
    route: dict[str, Any],
    available_skills: list[str],
) -> dict[str, Any]:
    """Select the minimal sufficient Skill combination from available skills.

    Returns a SkillCombination with:
    - selected_skills: list of skill names
    - missing_skills: list of required but unavailable skills
    - is_sufficient: bool
    """
    required_skills = route.get("skills", [])

    selected = [s for s in required_skills if s in available_skills]
    missing = [s for s in required_skills if s not in available_skills]

    is_sufficient = len(missing) == 0

    return {
        "selected_skills": selected,
        "missing_skills": missing,
        "is_sufficient": is_sufficient,
        "total_required": len(required_skills),
        "total_selected": len(selected),
    }


def validate_task_route(document: Any) -> dict[str, Any]:
    """Validate a task route document."""
    if not isinstance(document, dict):
        raise TaskRouterError("document must be an object")

    if document.get("schema_version") != TASK_ROUTER_SCHEMA:
        raise TaskRouterError(f"schema_version must be {TASK_ROUTER_SCHEMA}")

    task_kind = document.get("task_kind", "")
    if task_kind not in TASK_KINDS:
        raise TaskRouterError(f"task_kind must be one of {sorted(TASK_KINDS)}")

    skills = document.get("skills", [])
    if not isinstance(skills, list) or len(skills) == 0:
        raise TaskRouterError("skills must be a non-empty list")

    return {
        "verdict": "pass",
        "task_digest": document.get("task_digest", ""),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Task Router for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    route_parser = sub.add_parser("route")
    route_parser.add_argument("--task-kind", required=True)
    route_parser.add_argument("--context", help="Path to context JSON")

    args = parser.parse_args()
    try:
        if args.command == "route":
            ctx = json.loads(open(args.context, encoding="utf-8").read()) if args.context else {}
            result = route_task(args.task_kind, ctx)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (TaskRouterError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())