#!/usr/bin/env python3
"""Catalog and Context Compiler for DS Lite v6.

The Catalog is a rebuildable index of project files. The Context Compiler
produces a Context Receipt that records what was included/excluded and why,
within a token budget.

Schema: ds-lite.catalog.v1
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

CATALOG_SCHEMA = "ds-lite.catalog.v1"
CONTEXT_RECEIPT_SCHEMA = "ds-lite.context-receipt.v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")

# File types that are cataloged
CATALOGED_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".rs", ".go", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash",
    ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".csv", ".tsv", ".html", ".css", ".scss", ".sql",
})

# Directories to skip
SKIP_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv", ".env",
    ".mypy_cache", ".pytest_cache", ".tox", ".eggs", "*.egg-info",
    "dist", "build", ".cache", ".idea", ".vscode",
})

# Token estimation: ~4 chars per token
CHARS_PER_TOKEN = 4


class CatalogError(RuntimeError):
    pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    """Estimate token count for text."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped."""
    if dirname in SKIP_DIRS:
        return True
    for pattern in SKIP_DIRS:
        if "*" in pattern:
            import fnmatch
            if fnmatch.fnmatch(dirname, pattern):
                return True
    return False


def build_catalog(project_root: str) -> dict[str, Any]:
    """Build a catalog of project files.

    The catalog is rebuildable: the same project root will produce the same
    catalog digest.
    """
    root = Path(project_root)
    if not root.exists():
        raise CatalogError(f"project root does not exist: {root}")

    entries: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip directories in-place
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            ext = filepath.suffix.lower()
            if ext not in CATALOGED_EXTENSIONS:
                continue

            try:
                stat = filepath.stat()
                rel_path = str(filepath.relative_to(root)).replace("\\", "/")
                entry = {
                    "path": rel_path,
                    "extension": ext,
                    "size_bytes": stat.st_size,
                    "modified_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)
                    ),
                }
                entries.append(entry)
            except (OSError, ValueError):
                continue

    # Sort entries by path for deterministic digest
    entries.sort(key=lambda e: e["path"])

    catalog = {
        "schema_version": CATALOG_SCHEMA,
        "project_root": str(root),
        "entries": entries,
        "total_files": len(entries),
        "total_bytes": sum(e["size_bytes"] for e in entries),
        "built_at": _now_iso(),
        "catalog_digest": _digest({
            "entries": entries,
            "total_files": len(entries),
        }),
    }
    return catalog


def compile_context(
    catalog: dict[str, Any],
    task_scope: dict[str, Any],
    token_budget: int = 4096,
) -> dict[str, Any]:
    """Compile a context from a catalog within a token budget.

    Returns a Context Receipt that records:
    - What was included and why
    - What was excluded and why
    - Estimated token count
    - Inclusion/exclusion explanations
    """
    if not isinstance(catalog, dict):
        raise CatalogError("catalog must be an object")
    if catalog.get("schema_version") != CATALOG_SCHEMA:
        raise CatalogError(f"catalog schema_version must be {CATALOG_SCHEMA}")

    entries = catalog.get("entries", [])
    if not isinstance(entries, list):
        raise CatalogError("catalog entries must be a list")

    # Extract task scope parameters
    included_patterns = task_scope.get("include_patterns", ["**/*"])
    excluded_patterns = task_scope.get("exclude_patterns", [])
    priority_files = task_scope.get("priority_files", [])
    max_file_tokens = task_scope.get("max_file_tokens", 512)

    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    estimated_tokens = 0
    remaining_budget = token_budget

    # First, include priority files
    for priority in priority_files:
        if remaining_budget <= 0:
            break
        matching = [e for e in entries if priority in e.get("path", "")]
        for entry in matching:
            file_tokens = min(max_file_tokens, _estimate_tokens(entry.get("path", "")))
            if file_tokens <= remaining_budget:
                included.append({
                    "path": entry["path"],
                    "reason": "priority file",
                    "estimated_tokens": file_tokens,
                })
                estimated_tokens += file_tokens
                remaining_budget -= file_tokens
            else:
                excluded.append({
                    "path": entry["path"],
                    "reason": "exceeds remaining token budget",
                })

    # Then, include other matching files
    for entry in entries:
        if remaining_budget <= 0:
            break
        path = entry.get("path", "")
        if path in [i["path"] for i in included]:
            continue

        # Check include patterns
        included_match = any(pattern in path for pattern in included_patterns)
        if not included_match:
            excluded.append({"path": path, "reason": "does not match include patterns"})
            continue

        # Check exclude patterns
        excluded_match = any(pattern in path for pattern in excluded_patterns)
        if excluded_match:
            excluded.append({"path": path, "reason": "matches exclude pattern"})
            continue

        file_tokens = min(max_file_tokens, _estimate_tokens(path))
        if file_tokens <= remaining_budget:
            included.append({
                "path": path,
                "reason": "matches include patterns",
                "estimated_tokens": file_tokens,
            })
            estimated_tokens += file_tokens
            remaining_budget -= file_tokens
        else:
            excluded.append({
                "path": path,
                "reason": "exceeds remaining token budget",
            })

    # Add remaining entries as excluded
    included_paths = {i["path"] for i in included}
    excluded_paths = {e["path"] for e in excluded}
    for entry in entries:
        path = entry.get("path", "")
        if path not in included_paths and path not in excluded_paths:
            excluded.append({"path": path, "reason": "token budget exhausted"})

    receipt = {
        "schema_version": CONTEXT_RECEIPT_SCHEMA,
        "catalog_digest": catalog.get("catalog_digest", ""),
        "task_scope": task_scope,
        "token_budget": token_budget,
        "estimated_tokens": estimated_tokens,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "included": included,
        "excluded": excluded,
        "compiled_at": _now_iso(),
    }
    return receipt


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Catalog and Context Compiler for DS Lite v6")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build")
    build_parser.add_argument("--root", required=True, help="Project root directory")

    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--catalog", required=True, help="Path to catalog JSON")
    compile_parser.add_argument("--scope", required=True, help="Path to task scope JSON")
    compile_parser.add_argument("--budget", type=int, default=4096)

    args = parser.parse_args()
    try:
        if args.command == "build":
            result = build_catalog(args.root)
        elif args.command == "compile":
            catalog = json.loads(open(args.catalog, encoding="utf-8").read())
            scope = json.loads(open(args.scope, encoding="utf-8").read())
            result = compile_context(catalog, scope, args.budget)
        else:
            return 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (CatalogError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())