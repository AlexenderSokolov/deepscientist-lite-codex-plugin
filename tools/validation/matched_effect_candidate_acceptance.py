#!/usr/bin/env python3
"""Bind a completed matched-effect pilot to the exact Phase 5 candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


SCHEMA = "ds-lite.matched-effect-acceptance.v1"
CORE_PREFIX = "plugins/deepscientist-lite-core/"
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SENSITIVE_KEYS = {
    "api_key", "credentials", "environment", "hidden_reasoning", "model_text",
    "password", "prompt", "raw_output", "raw_response", "raw_stderr",
    "raw_transcript", "secret", "token", "transcript",
}


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _included(path: Path) -> bool:
    return not any(part in IGNORED_NAMES for part in path.parts) and path.suffix not in {".pyc", ".pyo"}


def tree_digest(root: Path) -> str:
    base = Path(root).resolve()
    value = hashlib.sha256()
    for path in sorted(item for item in base.rglob("*") if item.is_file() and _included(item.relative_to(base))):
        relative = path.relative_to(base).as_posix()
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(hashlib.sha256(path.read_bytes()).digest())
    return value.hexdigest()


def _read(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain an object")
    _reject_sensitive(payload, label)
    return payload, hashlib.sha256(content).hexdigest()


def _reject_sensitive(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower().replace("-", "_") in SENSITIVE_KEYS:
                raise ValueError(f"{label} contains sensitive evidence")
            _reject_sensitive(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested, label)


def _core_inventory(root: Path) -> list[dict[str, Any]]:
    base = Path(root).resolve()
    result = []
    for path in sorted(item for item in base.rglob("*") if item.is_file() and _included(item.relative_to(base))):
        result.append({
            "path": CORE_PREFIX + path.relative_to(base).as_posix(),
            "sha256": _digest(path),
            "size": path.stat().st_size,
        })
    return sorted(result, key=lambda item: item["path"])


def _candidate_core_inventory(root: Path) -> list[dict[str, Any]]:
    """Inventory of the Core publish projection, excluding compatibility runtime."""
    return [item for item in _core_inventory(root) if not item["path"].startswith(CORE_PREFIX + "controller/")]


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def build_acceptance(
    candidate_path: Path, repository: Path, pilot_root: Path,
    effect_report_path: Path, review_execution_path: Path, output: Path,
) -> dict[str, Any]:
    candidate, candidate_hash = _read(Path(candidate_path).resolve(), "candidate")
    report, report_hash = _read(Path(effect_report_path).resolve(), "effect report")
    review, review_hash = _read(Path(review_execution_path).resolve(), "review execution")
    pilot = Path(pilot_root).resolve()
    source, source_hash = _read(
        pilot / "source-snapshot" / "SOURCE_IDENTITY.json", "pilot source identity",
    )
    snapshot_core = pilot / "source-snapshot" / "plugins" / "deepscientist-lite-core"
    current_core = Path(repository).resolve() / "plugins" / "deepscientist-lite-core"
    candidate_digest = candidate.get("candidate_digest")
    source_manifest = candidate.get("source_manifest")
    candidate_core = []
    if isinstance(source_manifest, dict) and isinstance(source_manifest.get("files"), list):
        candidate_core = sorted([
            item for item in source_manifest["files"]
            if isinstance(item, dict) and str(item.get("path", "")).startswith(CORE_PREFIX)
        ], key=lambda item: str(item.get("path", "")))
    expected_tree = source.get("tree_digest")
    effect_checks = report.get("decision_checks")
    thresholds = (
        isinstance(effect_checks, dict)
        and effect_checks.get("expression_dimensions_favorable_in_both_comparisons", 0) >= 4
        and effect_checks.get("unsupported_completion_not_increased") is True
        and effect_checks.get("task_correctness_not_materially_worse") is True
    )
    checks = {
        "candidate_schema_match": candidate.get("schema_version") == "ds-lite.phase5-release-candidate.v1",
        "candidate_digest_valid": _valid_digest(candidate_digest),
        "candidate_core_inventory_match": candidate_core == _candidate_core_inventory(current_core),
        "pilot_snapshot_unchanged": _valid_digest(expected_tree) and tree_digest(snapshot_core) == expected_tree,
        "pilot_matches_current_core": _valid_digest(expected_tree) and tree_digest(current_core) == expected_tree,
        "effect_schema_match": report.get("schema_version") == "ds-lite.matched-effect.v1",
        "effect_thresholds_passed": report.get("status") == "descriptive-improvement-supported" and thresholds,
        "fixed_matrix_complete": (
            report.get("case_count") == 4 and report.get("arm_count") == 3
            and report.get("experimental_call_count") == 18
        ),
        "blind_review_independent": (
            report.get("blind_review_complete") is True
            and report.get("blind_review_call_count") == 1
            and report.get("mapping_available_to_reviewer") is False
            and review.get("schema_version") == "ds-lite.blind-review-execution.v1"
            and review.get("status") == "completed" and review.get("call_count") == 1
            and review.get("mapping_available_to_reviewer") is False
        ),
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": SCHEMA,
        "status": "passed" if passed else "blocked",
        "candidate_digest": candidate_digest if _valid_digest(candidate_digest) else None,
        "candidate_bound": True,
        "checks": checks,
        "inputs": {
            "candidate_sha256": candidate_hash,
            "effect_report_sha256": report_hash,
            "review_execution_sha256": review_hash,
            "pilot_source_identity_sha256": source_hash,
            "pilot_core_tree_digest": expected_tree,
        },
        "release_allowed": False,
    }
    _write_once(output, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--pilot-root", required=True, type=Path)
    parser.add_argument("--effect-report", required=True, type=Path)
    parser.add_argument("--review-execution", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_acceptance(
            args.candidate, args.repository, args.pilot_root,
            args.effect_report, args.review_execution, args.output,
        )
    except (OSError, UnicodeError, ValueError, FileExistsError):
        print(json.dumps({"schema_version": SCHEMA, "status": "blocked", "reason": "input-rejected"}))
        return 2
    print(json.dumps({"schema_version": SCHEMA, "status": receipt["status"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
