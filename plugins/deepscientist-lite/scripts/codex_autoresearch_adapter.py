#!/usr/bin/env python3
"""Compatibility adapter for the authorized codex-autoresearch snapshot.

The upstream runner writes raw event and runner logs. Until a caller provides a
sanitized child contract, this adapter only performs compatibility inspection and
refuses to spawn the external process.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

VERSION = "0.1.5-beta.0"
VENDOR_RELATIVE = "plugins/deepscientist-lite/vendor/codex-autoresearch/f2389bffbb4cd7789deb6796bc4ba35bf31f2a90"


class AdapterError(RuntimeError):
    pass


def vendor_root(repo_root: Path) -> Path:
    root = repo_root / Path(*VENDOR_RELATIVE.split("/"))
    if not root.is_dir() or not (root / "package.json").is_file():
        raise AdapterError("authorized codex-autoresearch vendor snapshot is missing")
    return root


def inspect(repo_root: Path) -> dict[str, object]:
    root = vendor_root(repo_root)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    return {
        "status": "passed" if package.get("version") == VERSION and package.get("license") == "MIT" else "blocked",
        "version": package.get("version"),
        "license": package.get("license"),
        "source_present": (root / "src").is_dir(),
        "tests_present": (root / "test").is_dir(),
        "spawn_observed": False,
        "raw_output_persisted": False,
    }


def validate_binary(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise AdapterError("autoresearch binary must be an existing file")
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdapterError("autoresearch version probe failed") from exc
    observed = (result.stdout or "") + "\n" + (result.stderr or "")
    matched = bool(re.search(r"(?<![0-9.])" + re.escape(VERSION) + r"(?![0-9.])", observed))
    return {"binary_present": True, "version_match": matched, "spawn_observed": True, "raw_output_persisted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the authorized autoresearch adapter without spawning it.")
    parser.add_argument("command", choices=("inspect", "validate-binary", "run"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--binary")
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo_root).resolve()
        if args.command == "inspect":
            result = inspect(root)
        elif args.command == "validate-binary":
            if not args.binary:
                raise AdapterError("validate-binary requires --binary")
            result = validate_binary(Path(args.binary).resolve())
        else:
            result = {"status": "blocked", "failure_layer": "external-policy-unverified", "spawn_observed": False, "raw_output_persisted": False, "next_action": "provide-a-sanitized-child-output-contract"}
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result.get("status") == "passed" else 1
    except (AdapterError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "autoresearch-adapter", "message": str(exc), "spawn_observed": False, "raw_output_persisted": False}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
