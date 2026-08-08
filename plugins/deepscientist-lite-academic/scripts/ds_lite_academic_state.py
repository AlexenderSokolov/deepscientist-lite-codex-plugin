#!/usr/bin/env python3
"""Shared, side-effect-free Academic workflow preflight and state contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any


REGISTRY_SCHEMA = "ds-lite.nature-skill-registry.v2"
STATE_SCHEMA = "ds-lite.academic-preflight.v1"


class AcademicStateError(ValueError):
    pass


def _relative(value: str, label: str) -> Path:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or "\\" in value or ".." in path.parts:
        raise AcademicStateError(f"{label} must be a project-relative POSIX path")
    return Path(*path.parts)


def load_registry() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "references" / "nature-skill-registry.json"
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcademicStateError(f"Academic registry is unavailable: {exc}") from exc
    if registry.get("schema_version") != REGISTRY_SCHEMA or not isinstance(registry.get("workflow_profiles"), dict):
        raise AcademicStateError("Academic registry contract is unsupported")
    skills = registry.get("skills")
    if not isinstance(skills, list) or len(skills) != 17:
        raise AcademicStateError("Academic registry must declare exactly 17 skills")
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("skill"), str):
            raise AcademicStateError("Academic registry skill entry is invalid")
        profile = item.get("workflow_profile")
        if profile not in registry["workflow_profiles"]:
            raise AcademicStateError(f"Academic skill {item['skill']} has no workflow profile")
        if item.get("required_artifacts") != ["PROJECT.md", "research/work-unit.json"]:
            raise AcademicStateError(f"Academic skill {item['skill']} artifacts are invalid")
        if item.get("review_required") is not True or item.get("evidence_pack_required") is not True:
            raise AcademicStateError(f"Academic skill {item['skill']} review boundary is invalid")
    return registry


def preflight(project_root: Path, skill: str, work_unit_ref: str, expected_revision: int, authorization_ref: str, output_boundary: str) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    if not root.is_dir() or not (root / "PROJECT.md").is_file():
        raise AcademicStateError("project root must contain PROJECT.md")
    if not isinstance(expected_revision, int) or expected_revision < 0:
        raise AcademicStateError("expected revision must be a non-negative integer")
    registry = load_registry()
    entry = next((item for item in registry["skills"] if item["skill"] == skill), None)
    if entry is None:
        raise AcademicStateError("skill is not registered in the Academic contract")
    work_unit = _relative(work_unit_ref, "work unit")
    authorization = _relative(authorization_ref, "authorization")
    boundary = _relative(output_boundary, "output boundary")
    if not (root / work_unit).is_file() or not (root / authorization).is_file():
        raise AcademicStateError("work unit and authorization artifacts must exist")
    return {
        "schema_version": STATE_SCHEMA,
        "status": "ready",
        "skill": skill,
        "workflow_profile": entry["workflow_profile"],
        "required_artifacts": entry["required_artifacts"],
        "review_required": True,
        "evidence_pack_required": True,
        "work_unit_ref": work_unit.as_posix(),
        "expected_revision": expected_revision,
        "authorization_ref": authorization.as_posix(),
        "output_boundary": boundary.as_posix(),
        "external_write_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate shared DS Lite Academic preflight state.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--work-unit-ref", default="research/work-unit.json")
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--output-boundary", required=True)
    args = parser.parse_args(argv)
    try:
        result = preflight(args.project_root, args.skill, args.work_unit_ref, args.expected_revision, args.authorization_ref, args.output_boundary)
    except AcademicStateError as exc:
        print(json.dumps({"schema_version": STATE_SCHEMA, "status": "blocked", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
