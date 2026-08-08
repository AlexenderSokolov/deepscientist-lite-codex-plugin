#!/usr/bin/env python3
"""Generate the Academic registry v2 contract and sanitized skill descriptions."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROFILE = "academic-evidence-v1"
FORBIDDEN = re.compile(r"\b(?:license|tags?|related_skills|related skills)\b", re.IGNORECASE)


def _frontmatter(text: str) -> tuple[list[str], int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md has no frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines, index
    raise ValueError("SKILL.md frontmatter is not closed")


def _description(value: str, skill: str) -> str:
    clean = re.split(r"\b(?:license|tags?|related_skills|related skills)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    clean = " ".join(clean.replace("|", " ").split())
    if len(clean) > 680:
        stop = max(clean.rfind(mark, 0, 680) for mark in (". ", "; ", ": "))
        clean = clean[:stop if stop > 120 else 680].rstrip(" ,;:")
    if len(clean) < 80:
        clean = f"Use the complete {skill} workflow with explicit authorization, source-grounded artifacts, review, and Evidence Pack requirements."
    if clean[-1] not in ".!?。！？":
        clean += "."
    if FORBIDDEN.search(clean) or len(clean) > 700:
        raise ValueError(f"cannot produce valid description for {skill}")
    return clean


def apply(repo_root: Path, *, write: bool) -> list[str]:
    academic = repo_root / "plugins" / "deepscientist-lite-academic"
    registry_path = academic / "references" / "nature-skill-registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry.get("skills"), list) or len(registry["skills"]) != 17:
        raise ValueError("registry must contain 17 skills")
    registry["schema_version"] = "ds-lite.nature-skill-registry.v2"
    registry["workflow_profiles"] = {
        PROFILE: {
            "required_artifacts": ["PROJECT.md", "research/work-unit.json"],
            "review_required": True,
            "evidence_pack_required": True,
            "external_write_requires_authorization": True,
        }
    }
    changed: list[str] = []
    for item in registry["skills"]:
        skill = item["skill"]
        item["workflow_profile"] = PROFILE
        item["required_artifacts"] = ["PROJECT.md", "research/work-unit.json"]
        item["review_required"] = True
        item["evidence_pack_required"] = True
        path = academic / "skills" / skill / "SKILL.md"
        lines, end = _frontmatter(path.read_text(encoding="utf-8"))
        description_index = next((index for index in range(1, end) if lines[index].startswith("description:")), None)
        if description_index is None:
            raise ValueError(f"{skill} has no description")
        expected = f"description: {_description(lines[description_index].split(':', 1)[1].strip(), skill)}"
        if lines[description_index] != expected:
            lines[description_index] = expected
            changed.append(path.relative_to(repo_root).as_posix())
            if write:
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rendered = json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
    if registry_path.read_text(encoding="utf-8") != rendered:
        changed.append(registry_path.relative_to(repo_root).as_posix())
        if write:
            registry_path.write_text(rendered, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    changed = apply(Path(args.repo_root).resolve(), write=args.write)
    print(json.dumps({"status": "passed" if not changed or args.write else "failed", "changed": changed}, ensure_ascii=False))
    return 0 if not changed or args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())
