#!/usr/bin/env python3
"""Offline runtime acceptance for the vendored Nature skill integration."""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

try:
    from .toml_compat import tomllib
except ImportError:
    from toml_compat import tomllib


class AcceptanceError(RuntimeError):
    pass


def _load_setup(repo_root: Path):
    scripts = repo_root / "plugins" / "deepscientist-lite" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import ds_lite_nature_setup

    return ds_lite_nature_setup


def _probe_skill(skill_root: Path) -> dict:
    failures: list[str] = []
    python_count = 0
    json_count = 0
    toml_count = 0
    shell_count = 0
    warning_count = 0
    for path in skill_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_root).as_posix()
        try:
            if path.suffix.lower() == ".py":
                with warnings.catch_warnings(record=True) as observed:
                    warnings.simplefilter("always", SyntaxWarning)
                    compile(path.read_text(encoding="utf-8"), relative, "exec")
                warning_count += len(observed)
                python_count += 1
            elif path.suffix.lower() == ".json":
                json.loads(path.read_text(encoding="utf-8"))
                json_count += 1
            elif path.suffix.lower() == ".toml":
                tomllib.loads(path.read_text(encoding="utf-8"))
                toml_count += 1
            elif path.suffix.lower() == ".sh":
                path.read_text(encoding="ascii")
                shell_count += 1
        except (OSError, UnicodeError, SyntaxError, json.JSONDecodeError, tomllib.TOMLDecodeError):
            failures.append(relative)
    if failures:
        status = "blocked"
    elif python_count or json_count or toml_count:
        status = "passed"
    else:
        status = "not-observed"
    return {
        "status": status,
        "python_sources_compiled": python_count,
        "json_documents_parsed": json_count,
        "toml_documents_parsed": toml_count,
        "shell_sources_observed": shell_count,
        "warning_count": warning_count,
        "failures": failures,
    }


def build_report(repo_root: Path) -> dict:
    root = repo_root.resolve()
    setup = _load_setup(root)
    registry = setup.load_registry(root / "plugins" / "deepscientist-lite" / "scripts" / "ds_lite_nature_setup.py")
    matrix = setup.capability_matrix(registry)
    snapshot = setup.verify_snapshot(registry)
    skills = []
    for name in sorted(matrix):
        skill_root = root / "plugins" / "deepscientist-lite" / "skills" / name
        probe = _probe_skill(skill_root)
        skills.append({
            "skill": name,
            "route_status": "passed" if matrix[name]["route_complete"] else "blocked",
            "runtime_probe_status": probe["status"],
            "runtime_probe": probe,
            "dependency_signals": matrix[name]["dependency_signals"],
            "local_fallback": matrix[name]["local_fallback"],
            "external_effects": matrix[name]["external_effects"],
        })
    blocked = snapshot["status"] != "passed" or any(
        item["route_status"] != "passed" or item["runtime_probe_status"] == "blocked"
        for item in skills
    )
    return {
        "schema_version": "ds-lite.nature-runtime-acceptance.v1",
        "status": "blocked" if blocked else "passed",
        "failure_layer": "nature-runtime" if blocked else "none",
        "skill_count": len(skills),
        "shared_layer_discoverable": snapshot["shared_layer_discoverable"],
        "snapshot_status": snapshot["status"],
        "skills": skills,
        "raw_output_persisted": False,
        "secret_values_persisted": False,
        "absolute_root_persisted": False,
        "real_gates_unlocked": False,
        "unverified": ["external APIs", "MCP host", "browser/CDP", "real model behavior"],
        "next_action": "run-real-polishing-smoke-after-provider-gate" if not blocked else "repair-reported-runtime-files",
    }


def write_report(repo_root: Path, output: Path) -> dict:
    if output.exists():
        raise AcceptanceError("refusing to overwrite existing output")
    report = build_report(repo_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline Nature runtime acceptance.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        report = write_report(Path(args.repo_root), Path(args.output))
    except AcceptanceError as exc:
        print(json.dumps({"status": "blocked", "failure_layer": "nature-runtime", "message": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": report["status"], "skill_count": report["skill_count"], "real_gates_unlocked": False}, ensure_ascii=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
