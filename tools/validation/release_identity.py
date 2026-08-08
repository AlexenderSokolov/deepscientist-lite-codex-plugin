#!/usr/bin/env python3
"""Validate and synchronize the seven active DS Lite package identities."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PACKAGE_SET_SCHEMA = "ds-lite.package-set.v1"
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$" )


class ReleaseIdentityError(ValueError):
    pass


def parse_semver(value: Any) -> tuple[int, int, int, tuple[tuple[int, int | str], ...]]:
    if not isinstance(value, str):
        raise ReleaseIdentityError("version must be a SemVer string")
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise ReleaseIdentityError(f"invalid SemVer: {value!r}")
    prerelease = match.group(4)
    identifiers: list[tuple[int, int | str]] = []
    if prerelease:
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ReleaseIdentityError(f"invalid numeric prerelease identifier: {value!r}")
                identifiers.append((0, int(identifier)))
            else:
                identifiers.append((1, identifier))
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), tuple(identifiers)


def compare_semver(left: str, right: str) -> int:
    a = parse_semver(left)
    b = parse_semver(right)
    if a[:3] != b[:3]:
        return -1 if a[:3] < b[:3] else 1
    if not a[3] or not b[3]:
        if a[3] == b[3]:
            return 0
        return -1 if a[3] else 1
    for a_part, b_part in zip(a[3], b[3]):
        if a_part == b_part:
            continue
        if a_part[0] != b_part[0]:
            return -1 if a_part[0] == 0 else 1
        return -1 if a_part[1] < b_part[1] else 1
    if len(a[3]) == len(b[3]):
        return 0
    return -1 if len(a[3]) < len(b[3]) else 1


def satisfies_semver(version: str, expression: str) -> bool:
    parse_semver(version)
    terms = expression.split()
    if not terms:
        raise ReleaseIdentityError("compatibility expression is empty")
    for term in terms:
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", term)
        if not match:
            raise ReleaseIdentityError(f"invalid compatibility term: {term!r}")
        operator, bound = match.groups()
        relation = compare_semver(version, bound)
        if not {
            None: relation == 0,
            "=": relation == 0,
            ">=": relation >= 0,
            "<=": relation <= 0,
            ">": relation > 0,
            "<": relation < 0,
        }[operator]:
            return False
    return True


def load_package_set(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "release" / "package-set.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseIdentityError(f"package set is unreadable: {exc}") from exc
    required = {"schema_version", "release_version", "target_tag", "core_compatibility", "packages", "installation_matrices"}
    if not isinstance(value, dict) or set(value) != required or value["schema_version"] != PACKAGE_SET_SCHEMA:
        raise ReleaseIdentityError("package set fields are invalid")
    if value["target_tag"] != f"v{value['release_version']}":
        raise ReleaseIdentityError("target_tag must bind release_version")
    parse_semver(value["release_version"])
    packages = value["packages"]
    expected = {"core", "academic", "web", "knowledge", "empirical", "engineering", "control-plane"}
    if not isinstance(packages, dict) or set(packages) != expected:
        raise ReleaseIdentityError("package set must declare exactly seven active packages")
    names: set[str] = set()
    for key, package in packages.items():
        if not isinstance(package, dict) or not {"directory", "name", "version"}.issubset(package):
            raise ReleaseIdentityError(f"package {key} fields are invalid")
        if not isinstance(package["directory"], str) or not package["directory"] or not isinstance(package["name"], str):
            raise ReleaseIdentityError(f"package {key} identity is invalid")
        if package["version"] != value["release_version"]:
            raise ReleaseIdentityError(f"package {key} does not match release_version")
        parse_semver(package["version"])
        names.add(package["name"])
    if len(names) != len(packages):
        raise ReleaseIdentityError("package names must be unique")
    core_version = packages["core"]["version"]
    if not satisfies_semver(core_version, value["core_compatibility"]):
        raise ReleaseIdentityError("core compatibility excludes the current Core version")
    matrices = value["installation_matrices"]
    if not isinstance(matrices, dict) or set(matrices) != {
        "core-only", "core+academic", "core+empirical", "core+engineering", "core+web",
        "core+knowledge", "core+web+knowledge", "all-six", "all-seven",
    }:
        raise ReleaseIdentityError("installation matrix set is invalid")
    for matrix, keys in matrices.items():
        if not isinstance(keys, list) or not keys or any(key not in packages for key in keys):
            raise ReleaseIdentityError(f"installation matrix {matrix} is invalid")
    return value


def package_records(repo_root: Path) -> dict[str, dict[str, Any]]:
    return load_package_set(repo_root)["packages"]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleaseIdentityError(f"{path} must contain an object")
    return value


def _expected_compatibility(package: dict[str, Any], core_expression: str) -> dict[str, Any]:
    return {
        "schema_version": "ds-lite.pack-compatibility.v1",
        "pack": {"plugin": package["name"], "version": package["version"]},
        "requires": {"plugin": "deepscientist-lite", "version": core_expression},
        "missing_core": "blocked",
    }


def check_identity(repo_root: Path) -> list[str]:
    package_set = load_package_set(repo_root)
    issues: list[str] = []
    for key, package in package_set["packages"].items():
        root = repo_root / "plugins" / package["directory"]
        manifest_path = root / ".codex-plugin" / "plugin.json"
        try:
            manifest = _load_json(manifest_path)
        except ReleaseIdentityError as exc:
            issues.append(f"{key}:manifest-unavailable:{exc}")
            continue
        if manifest.get("name") != package["name"]:
            issues.append(f"{key}:manifest-name-mismatch")
        if manifest.get("version") != package["version"]:
            issues.append(f"{key}:manifest-version-mismatch")
        if key == "core":
            continue
        compatibility_path = root / "compatibility.json"
        try:
            compatibility = _load_json(compatibility_path)
        except ReleaseIdentityError as exc:
            issues.append(f"{key}:compatibility-unavailable:{exc}")
            continue
        if compatibility != _expected_compatibility(package, package_set["core_compatibility"]):
            issues.append(f"{key}:compatibility-mismatch")
    return issues


def write_identity(repo_root: Path) -> list[Path]:
    package_set = load_package_set(repo_root)
    changed: list[Path] = []
    for key, package in package_set["packages"].items():
        root = repo_root / "plugins" / package["directory"]
        manifest_path = root / ".codex-plugin" / "plugin.json"
        manifest = _load_json(manifest_path)
        if manifest.get("name") != package["name"]:
            raise ReleaseIdentityError(f"{key} manifest name does not match package set")
        if manifest.get("version") != package["version"]:
            manifest["version"] = package["version"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed.append(manifest_path)
        if key == "core":
            continue
        compatibility_path = root / "compatibility.json"
        expected = _expected_compatibility(package, package_set["core_compatibility"])
        if not compatibility_path.is_file() or _load_json(compatibility_path) != expected:
            compatibility_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed.append(compatibility_path)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize DS Lite active package identities.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo_root).resolve()
        if args.write:
            changed = [path.relative_to(root).as_posix() for path in write_identity(root)]
            issues = check_identity(root)
            result = {"status": "passed" if not issues else "failed", "changed": changed, "issues": issues}
        else:
            issues = check_identity(root)
            result = {"status": "passed" if not issues else "failed", "issues": issues}
    except ReleaseIdentityError as exc:
        result = {"status": "failed", "failure_layer": "release-identity", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
