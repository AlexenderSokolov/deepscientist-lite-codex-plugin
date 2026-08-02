"""Create project-volume temporary directories with inherited workspace ACLs."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def default_temp_root(repo_root: Path) -> Path:
    fixed_root = (repo_root / "research" / ".validation-tmp").resolve()
    configured = os.environ.get("TEMP_ROOT", "").strip()
    if not configured:
        return fixed_root
    candidate = Path(configured).expanduser().resolve()
    try:
        candidate.relative_to(fixed_root)
    except ValueError as exc:
        raise ValueError(
            "TEMP_ROOT must be research/.validation-tmp or one of its project-volume children"
        ) from exc
    return candidate


def project_temp_dir(repo_root: Path, prefix: str = "run-") -> Path:
    parent = default_temp_root(repo_root)
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = parent / f"{prefix}{uuid.uuid4().hex[:12]}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate


def install_tempfile_policy(repo_root: Path) -> Path:
    """Route Python tempfile calls to project-owned inherited-ACL directories."""
    root = default_temp_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)

    def mkdtemp(suffix: str | None = None, prefix: str | None = None, dir: str | os.PathLike[str] | None = None) -> str:
        parent = Path(dir).expanduser().resolve() if dir else root
        parent.mkdir(parents=True, exist_ok=True)
        stem = prefix or "tmp"
        tail = suffix or ""
        while True:
            candidate = parent / f"{stem}{uuid.uuid4().hex[:12]}{tail}"
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            return str(candidate)

    tempfile.tempdir = str(root)
    tempfile.mkdtemp = mkdtemp
    return root
