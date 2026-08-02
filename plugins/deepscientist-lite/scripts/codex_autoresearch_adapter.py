#!/usr/bin/env python3
"""DS Lite adapter for the authorized codex-autoresearch snapshot."""

from __future__ import annotations

import argparse
import importlib.util
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


def run_session(root: Path, job_id: str, prompt_file: Path, goals: list[str], codex_bin: str, state_dir: Path | None, max_attempts: int) -> dict[str, object]:
    runner_path = root / "plugins" / "deepscientist-lite-core" / "scripts" / "ds_lite_autoresearch_runner.py"
    if not runner_path.is_file():
        raise AdapterError("DS Lite autoresearch runner is missing")
    spec = importlib.util.spec_from_file_location("ds_lite_autoresearch_runner", runner_path)
    if spec is None or spec.loader is None:
        raise AdapterError("DS Lite autoresearch runner cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = prompt_file.read_text(encoding="utf-8")
    result = module.run_job(root=root, job_id=job_id, initial_prompt=prompt, frozen_goals=goals, codex_bin=codex_bin, state_dir=state_dir, max_attempts=max_attempts)
    return {
        "status": result.get("status", "failed"),
        "job_id": job_id,
        "session_id_observed": bool(result.get("session_id")),
        "spawn_observed": int(result.get("attempt_count", 0)) > 0,
        "next_action": result.get("next_automatic_action", "inspect-runner-state"),
        "raw_output_persisted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or run the authorized autoresearch adapter.")
    parser.add_argument("command", choices=("inspect", "validate-binary", "run"))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--binary")
    parser.add_argument("--root", default=".")
    parser.add_argument("--job-id")
    parser.add_argument("--prompt-file")
    parser.add_argument("--goal", action="append", default=[])
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--state-dir")
    parser.add_argument("--max-attempts", type=int, default=3)
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
            if not args.job_id or not args.prompt_file or not args.goal:
                raise AdapterError("run requires --job-id, --prompt-file, and at least one --goal")
            result = run_session(Path(args.root).resolve(), args.job_id, Path(args.prompt_file).resolve(), args.goal, args.codex_bin, Path(args.state_dir).resolve() if args.state_dir else None, args.max_attempts)
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result.get("status") == "passed" else 1
    except (AdapterError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "autoresearch-adapter", "message": str(exc), "spawn_observed": False, "raw_output_persisted": False}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
