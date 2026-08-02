"""Unified, redacted cross-system validation for the Lite execution surface."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parents[2]
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from teaching.cli_compatibility import argv_projection
from tools.validation.check_text_compatibility import iter_files, scan_tree


SCHEMA_VERSION = "ds-lite.cross-system-validation.v1"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<outside-root>"


def _run_shell_check(root: Path, path: Path, shell: str) -> dict[str, Any]:
    resolved_shell = shutil.which(shell)
    if not resolved_shell:
        return {"tool": shell, "status": "not-observed", "failure_class": "unknown"}
    normalized_shell = resolved_shell.replace("\\", "/").lower()
    if shell == "bash" and os.name == "nt" and normalized_shell.endswith("/windows/system32/bash.exe"):
        return {"tool": shell, "status": "not-observed", "failure_class": "environment"}
    if shell == "bash":
        try:
            capability = subprocess.run(
                [shell, "-n"],
                cwd=str(root),
                input=":\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"tool": shell, "status": "not-observed", "failure_class": "environment"}
        if capability.returncode != 0:
            return {"tool": shell, "status": "not-observed", "failure_class": "environment"}
    command = [shell, "-n", str(path)] if shell == "bash" else [shell, "-NoProfile", "-NonInteractive", "-File",
                                                                   str(root / "tools/validation/check_powershell_syntax.ps1"),
                                                                   "-Path", str(path)]
    try:
        completed = subprocess.run(command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"tool": shell, "status": "not-observed", "failure_class": "environment"}
    if completed.returncode == 0:
        output = completed.stdout.lower()
        status = "not-observed" if "not-observed" in output else "passed"
        return {"tool": shell, "status": status, "failure_class": "none" if status == "passed" else "environment"}
    # Windows' WSL launcher can emit UTF-16LE text through a byte stream that
    # subprocess decodes as UTF-8. Removing interleaved NULs keeps fixed error
    # signatures classifiable without retaining the raw diagnostic.
    diagnostic = (completed.stderr + "\n" + completed.stdout).replace("\x00", "").lower()
    if any(token in diagnostic for token in ("createinstance", "e_accessdenied", "service", "not found", "cannot start")):
        return {"tool": shell, "status": "not-observed", "failure_class": "environment"}
    return {"tool": shell, "status": "failed", "failure_class": "syntax"}


def _is_template_source(path: Path) -> bool:
    parts = path.parts
    return any(parts[index:index + 2] == ("assets", "templates") for index in range(len(parts) - 1))


def run(root: Path) -> dict[str, Any]:
    text_report = scan_tree(root)
    syntax: list[dict[str, Any]] = []
    for path in iter_files(root):
        if path.suffix.lower() == ".ps1":
            item = (
                {"tool": "powershell.exe", "status": "not-observed", "failure_class": "template-source"}
                if _is_template_source(path)
                else _run_shell_check(root, path, "powershell.exe")
            )
            item["path"] = _relative(path, root)
            syntax.append(item)
        elif path.suffix.lower() == ".sh":
            item = (
                {"tool": "bash", "status": "not-observed", "failure_class": "template-source"}
                if _is_template_source(path)
                else _run_shell_check(root, path, "bash")
            )
            item["path"] = _relative(path, root)
            syntax.append(item)
    fixtures = [r"C:\work dir\中文(1)\a&b.txt", "/mnt/c/work dir/中文(1)/a&b.txt", "/tmp/work dir/中文(1)/a&b.txt"]
    argv = {"fixture_count": len(fixtures), "projections": [argv_projection(["runner", value]) for value in fixtures]}
    failed_syntax = [item for item in syntax if item["status"] == "failed"]
    failed_text = text_report["failed_count"]
    status = "passed" if not failed_syntax and not failed_text else "blocked"
    unverified = ["PowerShell 7" if not shutil.which("pwsh") else "", "shellcheck" if not shutil.which("shellcheck") else ""]
    unverified = [item for item in unverified if item]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "failure_layer": "encoding-format" if failed_text else ("shell-syntax" if failed_syntax else "none"),
        "text_compatibility": {"file_count": text_report["file_count"], "failed_count": failed_text},
        "syntax": syntax,
        "argv_fixtures": argv,
        "external_unobserved": unverified,
        "raw_output_persisted": False,
        "absolute_root_persisted": False,
        "next_action": "repair-reported-files" if status == "blocked" else "run-targeted-tests",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = run(root)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        if output.exists():
            raise SystemExit("refusing to overwrite validation receipt")
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8", newline="\n")
        except OSError:
            print(json.dumps({"status": "not-observed", "failure_layer": "environment-write",
                              "next_action": "set-authorized-temp-root"}))
            return 2
    print(json.dumps({"status": report["status"], "failure_layer": report["failure_layer"],
                      "next_action": report["next_action"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
