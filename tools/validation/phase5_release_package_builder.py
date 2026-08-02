#!/usr/bin/env python3
"""Build the immutable Phase 5 package projection without mutating source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


PACKAGE_DIRECTORIES = (
    "deepscientist-lite-core",
    "deepscientist-lite-academic",
    "deepscientist-lite-web",
    "deepscientist-lite-knowledge",
    "deepscientist-lite-empirical",
    "deepscientist-lite-engineering",
)
EXPECTED_HOOK_EVENTS = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative + b"\0" + hashlib.sha256(content).digest())
    return digest.hexdigest()


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


def _copy_ignore(_: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _reject_symlinks(root: Path) -> None:
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("release package source contains a symlink")


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

    return {
        "schema_version": "ds-lite.phase5-release-package-build.v1",
        "status": "passed",
        "package_digest": _tree_digest(destination),
        "package_directories": list(PACKAGE_DIRECTORIES),
        "transforms": [{
            "package": "deepscientist-lite-core",
            "operation": "remove-redundant-hooks-manifest-field",
        }],
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
