"""Shared runtime identity resolution for teaching and acceptance probes."""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_CONTROLLER = ROOT.joinpath("plugins", "deepscientist-lite-core", "controller")
if str(CORE_CONTROLLER) not in sys.path:
    sys.path.insert(0, str(CORE_CONTROLLER))

from ds_lite_control.runtime_pin import (  # noqa: E402
    resolve_codex_version,
    schema_manifest_version,
)


def _schema_root() -> Path:
    return CORE_CONTROLLER.parent / "schemas" / "codex"


def default_codex_version() -> str:
    """Return the highest stable version represented by a bundled manifest."""
    override = os.environ.get("DS_LITE_CODEX_VERSION", "").strip()
    if override:
        return resolve_codex_version(explicit=override)
    candidates: list[tuple[tuple[int, int, int], str]] = []
    root = _schema_root()
    for child in root.iterdir() if root.is_dir() else ():
        version = schema_manifest_version(child) if child.is_dir() else None
        if version and "-" not in version:
            parts = tuple(int(item) for item in version.split("."))
            candidates.append((parts, version))
    if not candidates:
        raise RuntimeError("no stable Codex schema manifest is bundled")
    return max(candidates)[1]


def version_for_schema(schema_root: Path) -> str:
    return resolve_codex_version(schema_root)


__all__ = ["default_codex_version", "version_for_schema"]
