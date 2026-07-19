#!/usr/bin/env python3
"""Audit an isolated Codex acceptance package without changing host state."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "ds-lite.codex-acceptance-audit.v1"
EXPECTED_SKILLS = {
    "ds-lite-intake",
    "ds-lite-scout",
    "ds-lite-idea",
    "ds-lite-experiment",
    "ds-lite-review",
    "ds-lite-analysis-write",
    "ds-lite-iterate",
}
EXPECTED_COMMUNICATION_REFERENCES = {
    "core.md",
    "profiles.md",
    "humanizer-zh.md",
    "humanizer-en.md",
    "academic-writing.md",
    "self-audit.md",
}
EXPECTED_COMMUNICATION_SOURCES = (
    "ai-zixun/humanizer-zh@f75f1ac9",
    "blader/humanizer@1b485648",
    "AIScientists-Dev/academic-humanizer@94b88b23",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_fresh(path: Path, value: Any) -> None:
    if path.exists():
        raise ValueError(f"record path already exists; choose a fresh path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def probe(command: list[str], timeout: float = 15.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"command": command, "status": "unavailable", "returncode": None, "output": "executable not found"}
    except subprocess.TimeoutExpired:
        return {"command": command, "status": "timeout", "returncode": None, "output": f"timed out after {timeout:g}s"}
    except OSError as exc:
        return {"command": command, "status": "unavailable", "returncode": None, "output": str(exc)}
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return {
        "command": command,
        "status": "supported" if completed.returncode == 0 else "unsupported",
        "returncode": completed.returncode,
        "output": output[-4000:],
    }


def audit(root: Path, codex_bin: str | None) -> tuple[dict[str, Any], bool, bool]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    record_path = root / "acceptance.json"
    if not record_path.is_file():
        return ({"schema_version": SCHEMA_VERSION, "errors": ["acceptance.json is missing"], "warnings": []}, False, False)

    source = read_json(record_path)
    if source.get("schema_version") != "ds-lite.codex-acceptance.v1":
        errors.append("acceptance.json has an unsupported schema_version")
    plugin_info = source.get("plugin", {})
    plugin_root = root / str(plugin_info.get("path", ""))
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        errors.append("copied plugin manifest is missing")
        manifest: dict[str, Any] = {}
    else:
        manifest = read_json(manifest_path)
        if manifest.get("name") != plugin_info.get("name"):
            errors.append("plugin name differs between acceptance.json and plugin.json")
        if manifest.get("version") != plugin_info.get("version"):
            errors.append("plugin version differs between acceptance.json and plugin.json")

    communication_root = plugin_root / "references" / "communication"
    actual_communication = {path.name for path in communication_root.glob("*.md")} if communication_root.is_dir() else set()
    style_template = plugin_root / "assets" / "templates" / "STYLE.md"
    notice_path = plugin_root / "THIRD_PARTY_NOTICES.md"
    source_manifest_path = communication_root / "upstream" / "_manifests" / "source-files.json"
    adoption_path = communication_root / "upstream-adoption.json"
    audit_script = plugin_root / "scripts" / "ds_lite_communication_audit.py"
    hook_script = plugin_root / "scripts" / "ds_lite_hook.py"
    hook_config_path = plugin_root / "hooks" / "hooks.json"
    notice_text = notice_path.read_text(encoding="utf-8") if notice_path.is_file() else ""
    communication_assets_ok = (
        actual_communication == EXPECTED_COMMUNICATION_REFERENCES
        and style_template.is_file()
        and notice_path.is_file()
        and all(source in notice_text for source in EXPECTED_COMMUNICATION_SOURCES)
        and notice_text.count("MIT License") >= 3
        and source_manifest_path.is_file()
        and adoption_path.is_file()
        and audit_script.is_file()
        and hook_script.is_file()
        and hook_config_path.is_file()
    )
    if not communication_assets_ok:
        errors.append("communication runtime assets are incomplete")
    elif "hooks" in manifest:
        errors.append("plugin manifest must not register an unconfirmed host hooks field")
    else:
        source_manifest = read_json(source_manifest_path)
        adoption = read_json(adoption_path)
        source_entries = source_manifest.get("entries", [])
        adoption_entries = adoption.get("entries", [])
        source_keys = {(item.get("repository"), item.get("commit"), item.get("source_path")) for item in source_entries}
        adoption_keys = {(item.get("repository"), item.get("commit"), item.get("source_path")) for item in adoption_entries}
        public_fields = {
            "repository", "commit", "source_path", "source_sha256", "decision",
            "local_refs", "rule_ids", "reason", "test_refs",
        }
        if len(source_entries) != 39 or len(adoption_entries) != 39 or source_keys != adoption_keys or len(source_keys) != 39:
            errors.append("upstream snapshot or adoption matrix does not contain exactly 39 unique files")
        if any(set(item) != public_fields for item in adoption_entries):
            errors.append("upstream adoption entry fields differ from the public nine-field contract")
        for item in source_entries:
            snapshot = root / str(item.get("local_snapshot", "")).replace("\\", "/")
            if not snapshot.is_file() or sha256(snapshot) != item.get("source_sha256"):
                errors.append(f"upstream snapshot hash mismatch: {item.get('source_path')}")
        hook_config = read_json(hook_config_path)
        if set(hook_config.get("hooks", {})) != {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}:
            errors.append("hook adapter must declare exactly the four audited lifecycle events")
        for skill_file in (plugin_root / "skills").glob("*/SKILL.md"):
            if "references/communication/upstream/" in skill_file.read_text(encoding="utf-8"):
                errors.append(f"runtime skill directly loads upstream snapshot: {skill_file.name}")

    marketplace_path = root / str(source.get("marketplace", {}).get("manifest", ""))
    if not marketplace_path.is_file():
        errors.append("marketplace manifest is missing")
    else:
        marketplace = read_json(marketplace_path)
        if marketplace.get("name") != source.get("marketplace", {}).get("name"):
            errors.append("marketplace name differs between acceptance.json and marketplace.json")
        entries = [item for item in marketplace.get("plugins", []) if item.get("name") == plugin_info.get("name")]
        if len(entries) != 1:
            errors.append("marketplace must contain exactly one matching plugin entry")
        elif entries[0].get("source", {}).get("path") != f"./{plugin_info.get('path')}":
            errors.append("marketplace plugin path does not match the copied plugin path")

    skills_root = plugin_root / "skills"
    actual_skills = {item.name for item in skills_root.iterdir() if item.is_dir() and (item / "SKILL.md").is_file()} if skills_root.is_dir() else set()
    missing_skills = sorted(EXPECTED_SKILLS - actual_skills)
    unexpected_skills = sorted(actual_skills - EXPECTED_SKILLS)
    if missing_skills:
        errors.append(f"missing skills: {', '.join(missing_skills)}")
    if unexpected_skills:
        warnings.append(f"unexpected skills: {', '.join(unexpected_skills)}")

    fixtures = source.get("fixtures", [])
    for relative in fixtures:
        fixture = root / str(relative)
        if not fixture.is_dir():
            errors.append(f"fixture is missing: {relative}")
            continue
        forbidden = [fixture / "REFERENCE_ANSWER.md"]
        forbidden.extend(fixture.glob("project/research/artifacts/review-*.md"))
        forbidden.extend(fixture.glob("project/research/artifacts/analysis-*.md"))
        if any(path.exists() for path in forbidden):
            errors.append(f"student fixture contains a prewritten review, analysis, or reference answer: {relative}")

    communication = source.get("communication_fixture", {})
    communication_root = root / str(communication.get("path", "communication"))
    cases_path = communication_root / "cases.json"
    scorecard_path = root / str(communication.get("scorecard", ""))
    if communication.get("runtime_loaded") is not False:
        errors.append("communication fixture must be marked runtime_loaded=false")
    if not cases_path.is_file() or not scorecard_path.is_file():
        errors.append("communication A/B fixture or anonymous scorecard is missing")
    else:
        try:
            cases = read_json(cases_path).get("cases", [])
        except (OSError, ValueError, KeyError):
            cases = []
        if len(cases) != 12 or len(communication.get("case_ids", [])) != 12:
            errors.append("communication fixture must contain exactly twelve fixed cases")
        expected_case_fields = {
            "id", "task_class", "profile", "detail_mode", "language", "prompt",
            "expected_protected", "expected_semantic_fields",
        }
        for case in cases:
            if set(case) != expected_case_fields or len(str(case.get("prompt", ""))) < 120:
                errors.append(f"communication fixture is not a complete fixed input: {case.get('id')}")
                continue
            if not case.get("expected_semantic_fields"):
                errors.append(f"communication fixture lacks semantic expectations: {case.get('id')}")
            for protected in case.get("expected_protected", []):
                if protected not in case.get("prompt", ""):
                    errors.append(f"communication fixture protection item is absent from prompt: {case.get('id')}")

    host_probes: list[dict[str, Any]] = []
    host_supported = False
    if codex_bin:
        host_probes.append(probe([codex_bin, "--version"]))
        host_probes.append(probe([codex_bin, "plugin", "marketplace", "list"]))
        host_supported = all(item["status"] == "supported" for item in host_probes)
        if not host_supported:
            warnings.append("Codex host does not expose the expected marketplace preflight commands; installation remains unverified")
    else:
        warnings.append("Codex host was not probed; installation and seven-skill discovery remain manual gates")

    result = {
        "schema_version": SCHEMA_VERSION,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_root": str(root),
        "package_valid": not errors,
        "host_supported": host_supported,
        "installation_verified": False,
        "skill_discovery_verified": False,
        "errors": errors,
        "warnings": warnings,
        "host_probes": host_probes,
        "observations_required": [
            "plugin version and source shown in a new Codex session",
            "all seven skills are discoverable",
            "manual workflow, communication A/B fixture, and failure-case file evidence",
        ],
    }
    return result, not errors, host_supported


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a prepared DeepScientist Lite Codex acceptance package.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--codex-bin", help="Optional Codex executable path for read-only capability probes.")
    parser.add_argument("--require-host", action="store_true", help="Fail when Codex capability probes are unavailable or unsupported.")
    parser.add_argument("--record", type=Path, help="Write the audit JSON to a fresh path; existing files are refused.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result, package_valid, host_supported = audit(args.root, args.codex_bin)
        if args.record:
            write_json_fresh(args.record.resolve(), result)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not package_valid:
        return 1
    if args.require_host and not host_supported:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
