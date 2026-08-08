#!/usr/bin/env python3
"""Build the immutable Phase 5 package projection without mutating source."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

try:
    from package_identity import tree_digest
except ModuleNotFoundError:  # package import from repository root
    from tools.validation.package_identity import tree_digest
try:
    from release_identity import check_identity, load_package_set
except ModuleNotFoundError:  # package import from repository root
    from tools.validation.release_identity import check_identity, load_package_set


PACKAGE_DIRECTORIES = (
    "deepscientist-lite-core",
    "deepscientist-lite-academic",
    "deepscientist-lite-web",
    "deepscientist-lite-knowledge",
    "deepscientist-lite-empirical",
    "deepscientist-lite-engineering",
    "deepscientist-lite-control-plane",
)
EXPECTED_HOOK_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
ACADEMIC_EXAMPLES_RELATIVE = Path("skills/nature-figure/assets/figures4papers")


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _copy_ignore(source: str, names: list[str]) -> set[str]:
    ignored = {
        name for name in names
        if name in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tmp", "tmp"}
        or name.endswith((".pyc", ".pyo"))
        or name in {".env", ".env.local", "credentials.json", "secrets.json"}
    }
    # Core retains a one-beta compatibility projection in source, but the
    # publishable Core candidate must not carry the control-plane runtime.
    if Path(source).name == "deepscientist-lite-core":
        ignored.add("controller")
        ignored.add("schemas")
    source_path = Path(source)
    if source_path.name == "assets" and source_path.parent.name == "nature-figure":
        ignored.add("figures4papers")
    return ignored


def _reject_symlinks(root: Path) -> None:
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("release package source contains a symlink")


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_academic_examples_archive(source_root: Path, destination: Path) -> dict[str, Any]:
    academic_root = source_root / "plugins" / "deepscientist-lite-academic"
    examples = academic_root / ACADEMIC_EXAMPLES_RELATIVE
    if not examples.is_dir():
        return {"included": False, "reason": "source-examples-unavailable"}
    archive = destination / "academic-examples.zip"
    files = sorted(path for path in examples.rglob("*") if path.is_file())
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, Path("plugins") / "deepscientist-lite-academic" / path.relative_to(academic_root))
    return {
        "included": True,
        "path": archive.name,
        "file_count": len(files),
        "uncompressed_bytes": sum(path.stat().st_size for path in files),
        "sha256": _sha256(archive),
        "network_requested": False,
    }


def _write_sbom(destination: Path, package_set: dict[str, Any]) -> dict[str, Any]:
    packages = []
    for key, package in sorted(package_set["packages"].items()):
        package_root = destination / "plugins" / package["directory"]
        packages.append({
            "key": key,
            "name": package["name"],
            "version": package["version"],
            "path": f"plugins/{package['directory']}",
            "sha256": tree_digest(package_root),
        })
    path = destination / "package-sbom.json"
    _write_once(path, {
        "schema_version": "ds-lite.package-sbom.v1",
        "release_version": package_set["release_version"],
        "target_tag": package_set["target_tag"],
        "packages": packages,
    })
    return {"path": path.name, "sha256": _sha256(path), "package_count": len(packages)}


def build_release_packages(repository: Path, output_root: Path) -> dict[str, Any]:
    source_root = Path(repository).resolve()
    destination = Path(output_root).resolve()
    if destination.exists():
        raise FileExistsError("release package output already exists")
    package_sources = [source_root / "plugins" / name for name in PACKAGE_DIRECTORIES]
    marketplace_source = source_root / ".agents" / "plugins" / "marketplace.json"
    if not all(path.is_dir() for path in package_sources):
        raise ValueError("release package source is incomplete")
    if not marketplace_source.is_file():
        raise ValueError("release marketplace manifest is missing")
    package_set = load_package_set(source_root)
    if tuple(package["directory"] for package in package_set["packages"].values()) != PACKAGE_DIRECTORIES:
        raise ValueError("package set directory order is invalid")
    if check_identity(source_root):
        raise ValueError("release identity is inconsistent")
    for path in package_sources:
        _reject_symlinks(path)

    destination.mkdir(parents=True)
    marketplace_destination = destination / ".agents" / "plugins"
    marketplace_destination.mkdir(parents=True)
    shutil.copy2(marketplace_source, marketplace_destination / "marketplace.json")
    for source in package_sources:
        shutil.copytree(source, destination / "plugins" / source.name, ignore=_copy_ignore)

    core = destination / "plugins" / "deepscientist-lite-core"
    manifest_path = core / ".codex-plugin" / "plugin.json"
    hook_path = core / "hooks" / "hooks.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hook_manifest = json.loads(hook_path.read_text(encoding="utf-8"))
    if manifest.get("hooks") != "./hooks/hooks.json":
        raise ValueError("Core source hook manifest pointer is unexpected")
    if set(hook_manifest.get("hooks", {})) != EXPECTED_HOOK_EVENTS:
        raise ValueError("Core Hook event set is incomplete")
    manifest.pop("hooks")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    academic_examples = _build_academic_examples_archive(source_root, destination)
    sbom = _write_sbom(destination, package_set)

    return {
        "schema_version": "ds-lite.phase5-release-package-build.v1",
        "status": "passed",
        "package_digest": tree_digest(destination),
        "package_directories": list(PACKAGE_DIRECTORIES),
        "transforms": [{
            "package": "deepscientist-lite-core",
            "operation": "remove-redundant-hooks-manifest-field",
        }, {
            "package": "deepscientist-lite-core",
            "operation": "exclude-compatibility-control-plane-runtime",
        }, {
            "package": "deepscientist-lite-academic",
            "operation": "archive-high-resolution-examples",
        }],
        "academic_examples": academic_examples,
        "sbom": sbom,
        "source_mutated": False,
        "hook_config_retained": True,
        "release_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_release_packages(args.repository, args.output_root)
        _write_once(args.receipt, result)
    except (OSError, UnicodeError, ValueError, FileExistsError, json.JSONDecodeError):
        print(json.dumps({"status": "blocked", "reason": "release-package-build-failed"}))
        return 2
    print(json.dumps({"status": result["status"], "package_digest": result["package_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
