#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from package_identity import package_digest
except ModuleNotFoundError:  # package import from repository root
    from tools.validation.package_identity import package_digest


PACKAGES: dict[str, dict[str, Any]] = {
   "core": {
       "directory": "deepscientist-lite-core",
       "name": "deepscientist-lite",
       "version": "0.10.0-beta.2",
       "skills": {
           "ds-lite",
           "ds-lite-analysis-write",
           "ds-lite-coordinate",
           "ds-lite-experiment",
           "ds-lite-idea",
           "ds-lite-intake",
           "ds-lite-iterate",
           "ds-lite-review",
           "ds-lite-scout",
       },
   },
   "academic": {
       "directory": "deepscientist-lite-academic",
       "name": "deepscientist-lite-academic",
       "version": "0.10.0-beta.2",
       "skill_count": 17,
       "skill_prefix": "nature-",
   },
    "web": {
        "directory": "deepscientist-lite-web",
        "name": "deepscientist-lite-web",
        "version": "0.3.0-alpha.1",
        "skills": {"ds-lite-web"},
    },
    "knowledge": {
        "directory": "deepscientist-lite-knowledge",
        "name": "deepscientist-lite-knowledge",
        "version": "0.3.0-alpha.1",
        "skills": {"ds-lite-knowledge"},
    },
    "empirical": {
        "directory": "deepscientist-lite-empirical",
        "name": "deepscientist-lite-empirical",
        "version": "0.3.0-alpha.1",
        "skills": {"ds-lite-empirical"},
        "max_files": 150,
        "max_bytes": 5 * 1024 * 1024,
    },
    "engineering": {
        "directory": "deepscientist-lite-engineering",
        "name": "deepscientist-lite-engineering",
        "version": "0.3.0-alpha.1",
        "skills": {"ds-lite-engineering"},
        "max_files": 150,
        "max_bytes": 5 * 1024 * 1024,
    },
    "control-plane": {
        "directory": "deepscientist-lite-control-plane",
        "name": "deepscientist-lite-control-plane",
        "version": "0.10.0-beta.2",
        "skills": {"ds-lite-control-plane"},
        "max_files": 80,
        "max_bytes": 2 * 1024 * 1024,
    },
}

MATRICES = {
    "core-only": ("core",),
    "core+academic": ("core", "academic"),
    "core+empirical": ("core", "empirical"),
    "core+engineering": ("core", "engineering"),
    "core+web": ("core", "web"),
    "core+knowledge": ("core", "knowledge"),
    "core+web+knowledge": ("core", "web", "knowledge"),
    "all-six": ("core", "academic", "web", "knowledge", "empirical", "engineering"),
    "all-seven": ("core", "academic", "web", "knowledge", "empirical", "engineering", "control-plane"),
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def discover_skills(package_root: Path) -> set[str]:
    skills_root = package_root / "skills"
    if not skills_root.is_dir():
        return set()
    return {
        path.name
        for path in skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


def validate_package(repo_root: Path, key: str) -> dict[str, Any]:
    expected = PACKAGES[key]
    package_root = repo_root / "plugins" / expected["directory"]
    issues: list[str] = []
    try:
        manifest = load_json(package_root / ".codex-plugin" / "plugin.json")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        manifest = {}
        issues.append(f"manifest-unavailable:{exc}")

    if manifest.get("name") != expected["name"]:
        issues.append("manifest-name-mismatch")
    if manifest.get("version") != expected["version"]:
        issues.append("manifest-version-mismatch")
    if manifest.get("skills") != "./skills/":
        issues.append("manifest-skills-path-mismatch")

    skills = discover_skills(package_root)
    if "skills" in expected and skills != expected["skills"]:
        issues.append("discoverable-skills-mismatch")
    if "skill_count" in expected:
        if len(skills) != expected["skill_count"]:
            issues.append("discoverable-skill-count-mismatch")
        if not all(name.startswith(expected["skill_prefix"]) for name in skills):
            issues.append("discoverable-skill-prefix-mismatch")

    file_count, total_bytes, digest = package_digest(package_root)
    if key == "core":
        # A complete generated app-server schema is deliberately shipped as a
        # protocol witness. Keep a bounded Core while allowing that evidence.
        if file_count > 600:
            issues.append("core-file-budget-exceeded")
        if total_bytes > 10 * 1024 * 1024:
            issues.append("core-byte-budget-exceeded")
        if (package_root / "vendor").exists():
            issues.append("core-vendor-directory-present")
        hook_path = package_root / "hooks" / "hooks.json"
        try:
            hook_manifest = load_json(hook_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            hook_manifest = {}
            issues.append(f"core-hook-config-unavailable:{exc}")
        if set(hook_manifest.get("hooks", {})) != {
            "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
        }:
            issues.append("core-hook-event-set-mismatch")
    else:
        try:
            compatibility = load_json(package_root / "compatibility.json")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            compatibility = {}
            issues.append(f"compatibility-unavailable:{exc}")
        required = compatibility.get("requires", {})
        if compatibility.get("schema_version") != "ds-lite.pack-compatibility.v1":
            issues.append("compatibility-schema-mismatch")
        if required.get("plugin") != "deepscientist-lite":
            issues.append("core-requirement-mismatch")
        required_version = required.get("version", "")
        if not (required_version == "0.9.0-beta.1" or required_version.startswith(">=")):
            issues.append("core-requirement-mismatch")
            issues.append("core-requirement-mismatch")
        if compatibility.get("missing_core") != "blocked":
            issues.append("missing-core-must-block")
        if "hooks" in manifest:
            issues.append("optional-pack-must-not-own-hooks")
        if expected.get("max_files") is not None and file_count > expected["max_files"]:
            issues.append("optional-pack-file-budget-exceeded")
        if expected.get("max_bytes") is not None and total_bytes > expected["max_bytes"]:
            issues.append("optional-pack-byte-budget-exceeded")

    return {
        "package": expected["name"],
        "version": expected["version"],
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "skill_count": len(skills),
        "skills": sorted(skills),
        "file_count": file_count,
        "bytes": total_bytes,
        "sha256": digest,
    }


def validate_marketplace(repo_root: Path) -> list[str]:
    issues: list[str] = []
    marketplace = load_json(repo_root / ".agents" / "plugins" / "marketplace.json")
    entries = {item.get("name"): item for item in marketplace.get("plugins", [])}
    expected_names = {value["name"] for value in PACKAGES.values()}
    if set(entries) != expected_names:
        issues.append("marketplace-package-set-mismatch")
    for expected in PACKAGES.values():
        entry = entries.get(expected["name"], {})
        source = entry.get("source", {})
        if source.get("source") != "local":
            issues.append(f"{expected['name']}:marketplace-source-not-local")
        if source.get("path") != f"./plugins/{expected['directory']}":
            issues.append(f"{expected['name']}:marketplace-path-mismatch")
    return issues


def validate_matrices(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    matrix_results: list[dict[str, Any]] = []
    for matrix_name, package_keys in MATRICES.items():
        skills: list[str] = []
        package_statuses: list[str] = []
        for key in package_keys:
            skills.extend(results[key]["skills"])
            package_statuses.append(results[key]["status"])
        collisions = sorted({skill for skill in skills if skills.count(skill) > 1})
        status = "passed" if not collisions and all(item == "passed" for item in package_statuses) else "failed"
        matrix_results.append(
            {
                "matrix": matrix_name,
                "packages": [PACKAGES[key]["name"] for key in package_keys],
                "status": status,
                "skill_count": len(set(skills)),
                "route_collisions": collisions,
            }
        )
    return matrix_results


def validate(repo_root: Path, package: str) -> tuple[dict[str, Any], int]:
    selected = list(PACKAGES) if package == "all" else [package]
    results = {key: validate_package(repo_root, key) for key in selected}
    marketplace_issues = validate_marketplace(repo_root) if package == "all" else []
    matrices = validate_matrices({key: validate_package(repo_root, key) for key in PACKAGES}) if package == "all" else []
    failed = any(item["status"] != "passed" for item in results.values())
    failed = failed or bool(marketplace_issues) or any(item["status"] != "passed" for item in matrices)
    receipt = {
        "schema_version": "ds-lite.package-validation.v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": package,
        "status": "failed" if failed else "passed",
        "packages": list(results.values()),
        "marketplace_issues": marketplace_issues,
        "installation_matrices": matrices,
        "real_host_gates": {
            "hook": "not-verified",
            "delegation": "not-verified",
            "matched_effect": "not-verified",
            "formal_cache": "not-verified",
            "fresh_desktop": "not-verified",
            "release": "not-verified",
        },
    }
    return receipt, 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate split DeepScientist Lite packages.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--package", choices=[*PACKAGES, "all"], default="all")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        receipt, returncode = validate(Path(args.repo_root).resolve(), args.package)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        receipt = {
            "schema_version": "ds-lite.package-validation.v1",
            "status": "failed",
            "failure_layer": "package-validation",
            "error": str(exc),
        }
        returncode = 1
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
