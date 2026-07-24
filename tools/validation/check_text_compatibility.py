#!/usr/bin/env python3
"""Byte-level and parser checks for cross-shell text compatibility.

The checker intentionally reports observations rather than rewriting files.  It
is safe to run against a worktree containing user changes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:  # pragma: no cover - optional on local Python 3.10
        tomllib = None


EXECUTABLE_SUFFIXES = {".ps1", ".sh", ".cmd"}
UTF8_SUFFIXES = {".py", ".json", ".toml", ".md"}
TEXT_SUFFIXES = EXECUTABLE_SUFFIXES | UTF8_SUFFIXES | {
    ".txt", ".rst", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".xml",
    ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".sql",
}
DEFAULT_IGNORED_DIRS = {
    ".git",
    ".validation-tmp",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "vendor",
    "System.Management.Automation.Internal.Host.InternalHost",
}


def _configure_stdio() -> None:
    """Keep JSON diagnostics printable on legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _line_facts(raw: bytes) -> dict[str, object]:
    crlf = raw.count(b"\r\n")
    without_crlf = raw.replace(b"\r\n", b"")
    bare_cr = without_crlf.count(b"\r")
    bare_lf = without_crlf.count(b"\n")
    styles = sum(bool(count) for count in (crlf, bare_lf, bare_cr))
    return {
        "line_ending": "mixed" if styles > 1 else ("crlf" if crlf else "lf" if bare_lf else "none"),
        "crlf_count": crlf,
        "lf_count": bare_lf,
        "bare_cr_count": bare_cr,
    }


def check_file(path: str | Path, *, parse_structured: bool = True) -> dict[str, object]:
    """Inspect one file without writing it; ``path`` is returned as supplied."""
    file_path = Path(path)
    raw = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    executable = suffix in EXECUTABLE_SUFFIXES
    text_candidate = suffix in TEXT_SUFFIXES
    result: dict[str, object] = {
        "path": str(file_path),
        "suffix": suffix,
        "exists": True,
        "byte_count": len(raw),
        "ascii_required": executable,
        "ascii_valid": all(byte < 128 for byte in raw) if executable else None,
        "utf8_required": suffix in UTF8_SUFFIXES,
        "utf8_valid": None,
        "bom": raw.startswith(b"\xef\xbb\xbf"),
        "nul_observed": b"\x00" in raw,
        "replacement_character_observed": False,
        **_line_facts(raw),
        "parse_status": "not-applicable",
        "parse_error": None,
        "status": "passed",
    }
    try:
        text = raw.decode("utf-8")
        result["utf8_valid"] = True
        result["replacement_character_observed"] = "\ufffd" in text
    except UnicodeDecodeError as exc:
        result["utf8_valid"] = False
        result["parse_error"] = f"utf8:{exc.reason}"
        text = None

    if parse_structured and text is not None and suffix in {".json", ".toml"}:
        try:
            if suffix == ".json":
                json.loads(text.lstrip("\ufeff"))
            elif tomllib is not None:
                tomllib.loads(text.lstrip("\ufeff"))
            else:
                result["parse_status"] = "not-observed"
            if result["parse_status"] == "not-applicable":
                result["parse_status"] = "passed"
        except (ValueError, TypeError) as exc:
            result["parse_status"] = "failed"
            result["parse_error"] = f"{type(exc).__name__}: {exc}"
    if executable:
        result["line_ending_policy"] = "lf" if suffix == ".sh" else "any"
    else:
        result["line_ending_policy"] = "any"
    violations: list[str] = []
    if executable and not result["ascii_valid"]:
        violations.append("non-ascii-executable")
    if executable and result["bom"]:
        violations.append("bom-on-executable")
    if suffix in UTF8_SUFFIXES and not result["utf8_valid"]:
        violations.append("invalid-utf8")
    if text_candidate and result["nul_observed"]:
        violations.append("nul-byte")
    if text_candidate and result["replacement_character_observed"]:
        violations.append("replacement-character")
    if text_candidate and result["line_ending"] == "mixed":
        violations.append("mixed-line-endings")
    if suffix == ".sh" and result["line_ending"] == "crlf":
        violations.append("crlf-shell")
    if result["parse_status"] == "failed":
        violations.append("structured-parse")
    result["violations"] = violations
    result["status"] = "failed" if violations else "passed"
    return result


def iter_files(root: str | Path, *, ignored_dirs: Iterable[str] = DEFAULT_IGNORED_DIRS):
    root_path = Path(root)
    ignored = set(ignored_dirs)
    if root_path.is_file():
        yield root_path
        return
    for current, dirnames, filenames in os.walk(root_path, topdown=True, onerror=lambda _error: None):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored)
        for name in sorted(filenames):
            path = Path(current) / name
            if not any(part in ignored for part in path.parts):
                yield path


def scan_tree(root: str | Path) -> dict[str, object]:
    root_path = Path(root)
    candidates = [root_path] if root_path.is_file() else list(iter_files(root_path))
    files = []
    for path in candidates:
        is_template = "assets" in path.parts and "templates" in path.parts
        item = check_file(path, parse_structured=not is_template)
        if "vendor" in path.parts:
            # Vendor snapshots are immutable provenance, not DS Lite entrypoints.
            # Keep their byte-level observations without failing the owned tree.
            item["provenance_only"] = True
            item["status"] = "not-observed"
            item["violations"] = []
        if is_template and path.suffix.lower() in {".json", ".toml"}:
            item["parse_status"] = "template-not-applicable"
            item["violations"] = [v for v in item["violations"] if v != "structured-parse"]
            item["status"] = "failed" if item["violations"] else "passed"
        files.append(item)
    return {
        "schema_version": "ds-lite.text-compatibility.v1",
        "root": str(Path(root)),
        "file_count": len(files),
        "failed_count": sum(item["status"] == "failed" for item in files),
        "files": files,
    }


def tool_observation() -> dict[str, dict[str, object]]:
    """Return availability only; no tool output is retained."""
    tools = {"powershell": ("powershell", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"),
             "pwsh": ("pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"),
             "bash": ("bash", "-n", "-"), "shellcheck": ("shellcheck", "--version")}
    result = {}
    for name, command in tools.items():
        executable = shutil.which(command[0])
        result[name] = {"available": executable is not None, "status": "not-observed" if executable is None else "available"}
    return result


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Check text encoding and format compatibility.")
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    report = scan_tree(args.root)
    report["external_tools"] = tool_observation()
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"checked={report['file_count']} failed={report['failed_count']}")
    return 1 if report["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
