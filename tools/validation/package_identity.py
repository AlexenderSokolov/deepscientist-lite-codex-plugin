"""Shared package file selection and digest rules for validation and release."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

IGNORED_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tmp", "tmp", "research", "System.Management.Automation.Internal.Host.InternalHost",
}
IGNORED_DIR_PREFIXES = (".tmp-", "ds-lite-autoresearch-runner-")
IGNORED_SUFFIXES = {".pyc", ".pyo"}
SENSITIVE_NAMES = {".env", ".env.local", "credentials.json", "secrets.json"}


def iter_package_files(root: Path) -> Iterable[Path]:
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if (
            any(part in IGNORED_DIRS for part in relative.parts)
            or any(part.startswith(IGNORED_DIR_PREFIXES) for part in relative.parts)
        ):
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES or path.name in SENSITIVE_NAMES:
            continue
        yield path


def package_digest(root: Path) -> tuple[int, int, str]:
    root = root.resolve()
    total_bytes = 0
    files = list(iter_package_files(root))
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        total_bytes += len(content)
    return len(files), total_bytes, tree_digest(root)


def tree_digest(root: Path) -> str:
    """Digest used by candidate, cache, and host identity receipts."""
    root = root.resolve()
    digest = hashlib.sha256()
    for path in iter_package_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
