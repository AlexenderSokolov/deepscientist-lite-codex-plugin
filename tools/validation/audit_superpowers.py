#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED_SKILLS = {
    "brainstorming",
    "systematic-debugging",
    "test-driven-development",
    "verification-before-completion",
}
PROTECTED_OWNERSHIP = {"research_state", "approval", "evidence", "stop_gate"}


def audit(skills_root: str | None, policy_path: str | None) -> tuple[dict, int]:
    observed: list[str] = []
    if skills_root:
        root = Path(skills_root).expanduser().resolve()
        if root.is_dir():
            observed = sorted(
                name for name in EXPECTED_SKILLS if (root / name / "SKILL.md").is_file()
            )
    state = "absent" if not observed else "present"
    conflicts: list[str] = []
    if policy_path:
        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        owners = policy.get("owners", {}) if isinstance(policy, dict) else {}
        if not isinstance(owners, dict):
            raise ValueError("owners must be an object")
        for boundary in PROTECTED_OWNERSHIP:
            owner = owners.get(boundary, "deepscientist-lite")
            if owner != "deepscientist-lite":
                conflicts.append(f"{boundary}:{owner}")
    if conflicts:
        state = "conflict"
    result = {
        "schema_version": "ds-lite.superpowers-compatibility.v1",
        "status": "blocked" if conflicts else "passed",
        "state": state,
        "observed_process_skills": observed,
        "delegated_process_roles": [
            "brainstorming", "test-driven-development", "systematic-debugging", "verification"
        ] if observed and not conflicts else [],
        "ds_lite_ownership": sorted(PROTECTED_OWNERSHIP),
        "conflicts": conflicts,
        "second_state_machine": False,
    }
    return result, 2 if conflicts else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit selective Superpowers interoperability.")
    parser.add_argument("--skills-root")
    parser.add_argument("--policy")
    args = parser.parse_args(argv)
    try:
        result, returncode = audit(args.skills_root, args.policy)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "state": "invalid", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
