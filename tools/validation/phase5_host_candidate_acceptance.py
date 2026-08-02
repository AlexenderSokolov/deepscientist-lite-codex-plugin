#!/usr/bin/env python3
"""Candidate-bound stable Hook and fresh Desktop acceptance producers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teaching.trusted_host_prepare import _candidate_identity  # noqa: E402


EXPECTED_PACKAGES = {
    "deepscientist-lite": "0.8.1-beta.1",
    "deepscientist-lite-academic": "0.8.1-beta.1",
    "deepscientist-lite-web": "0.2.0-alpha.1",
    "deepscientist-lite-knowledge": "0.2.0-alpha.1",
    "deepscientist-lite-empirical": "0.2.0-alpha.1",
    "deepscientist-lite-engineering": "0.2.0-alpha.1",
}
HOOK_CHECKS = {
    "runtime_pin_enforced", "one_cli_turn", "one_terminal_turn", "terminal_observed",
    "stop_block_then_allow", "nonempty_stop_reasons", "repair_budget_transition",
    "same_cli_turn_repair",
}
DESKTOP_CHECKS = {
    "candidate_artifact_read", "evidence_pack_sanitized", "fresh_desktop_observed",
    "openscience_task_observed", "provider_receipt_bound", "terminal_observed",
}
OPENSCIENCE_HOST_SCHEMA = "ds-lite.openscience-host-observation.v1"
SENSITIVE_KEYS = {
    "api_key", "credentials", "environment", "hidden_reasoning", "model_text",
    "password", "prompt", "raw_response", "raw_stderr", "raw_transcript",
    "secret", "token", "transcript",
}


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _read(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain an object")
    _reject_sensitive(value)
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower().replace("-", "_") in SENSITIVE_KEYS:
                raise ValueError("formal evidence contains sensitive content")
            _reject_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested)


def _candidate(path: Path) -> tuple[dict[str, Any], str]:
    value = _read(path, "candidate")
    digest = value.get("candidate_digest")
    if (
        value.get("schema_version") != "ds-lite.phase5-release-candidate.v1"
        or not isinstance(digest, str) or len(digest) != 64
    ):
        raise ValueError("candidate contract failed")
    return value, digest


def _checks(value: Any, required: set[str]) -> bool:
    return (
        isinstance(value, dict) and required.issubset(value)
        and all(value.get(name) is True for name in required)
    )


def _write_once(path: Path, value: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def build_hook_acceptance(
    candidate_path: Path, preparation_path: Path, host_path: Path, verifier_path: Path,
    current_core_identity: dict[str, Any], output: Path,
) -> dict[str, Any]:
    _, digest = _candidate(Path(candidate_path).resolve())
    preparation = _read(Path(preparation_path).resolve(), "Hook preparation")
    host = _read(Path(host_path).resolve(), "Hook host")
    verifier = _read(Path(verifier_path).resolve(), "Hook verifier")
    prepared_identity = preparation.get("candidate")
    sequence = host.get("hook_event_sequence")
    stops = [item for item in sequence if isinstance(item, dict) and item.get("event_type") == "stop"] \
        if isinstance(sequence, list) else []
    event_counts = host.get("event_type_counts")
    identity = host.get("cli_identity")
    checks = {
        "candidate_core_identity_match": prepared_identity == current_core_identity,
        "current_core_has_nine_skills": current_core_identity.get("skill_count") == 9,
        "current_core_has_four_hooks": current_core_identity.get("hook_events") == [
            "PostToolUse", "PreToolUse", "Stop", "UserPromptSubmit",
        ],
        "preparation_isolated_and_sanitized": (
            preparation.get("schema_version") == "ds-lite.trusted-host-preparation.v1"
            and preparation.get("status") == "prepared"
            and preparation.get("codex_version") == "0.146.0"
            and preparation.get("config_validated") is True
            and preparation.get("workspace_trust_configured") is True
            and preparation.get("secret_material_persisted") is False
        ),
        "real_host_terminal": (
            host.get("schema_version") == "ds-lite.fresh-host-probe.v1"
            and host.get("status") == "passed" and host.get("failure_layer") == "none"
            and host.get("terminal_event_observed") is True
            and host.get("raw_output_persisted") is False
        ),
        "single_turn": (
            isinstance(event_counts, dict) and event_counts.get("thread.started") == 1
            and event_counts.get("turn.started") == 1 and event_counts.get("turn.completed") == 1
        ),
        "stable_runtime_pin": (
            isinstance(identity, dict) and identity.get("enforced") is True
            and identity.get("expected_version") == "0.146.0" and identity.get("sha256_match") is True
        ),
        "same_turn_stop_repair": (
            len(stops) == 2 and [item.get("decision") for item in stops] == ["block", "allow"]
            and all(item.get("reason_present") is True for item in stops)
            and stops[0].get("stop_hook_active") is False
            and stops[1].get("stop_hook_active") is True
        ),
        "independent_verifier_passed": (
            verifier.get("schema_version") == "ds-lite.phase5-hook-continuation-verifier.v1"
            and verifier.get("status") == "passed" and verifier.get("release_allowed") is False
            and _checks(verifier.get("checks"), HOOK_CHECKS)
        ),
    }
    if not all(checks.values()):
        raise ValueError("stable Hook candidate contract failed")
    result = {
        "schema_version": "ds-lite.trusted-hook-acceptance.v1",
        "status": "passed", "candidate_digest": digest, "candidate_bound": True,
        "codex_version": "0.146.0", "evidence_class": "real-codex-cli",
        "checks": checks,
        "input_sha256": {
            "preparation": _sha256(Path(preparation_path).resolve()),
            "host": _sha256(Path(host_path).resolve()),
            "verifier": _sha256(Path(verifier_path).resolve()),
        },
        "core_source_sha256": current_core_identity["source_sha256"],
        "global_trust_modified": False, "credential_value_read_or_copied": False,
        "raw_output_persisted": False, "release_allowed": False,
    }
    _write_once(Path(output), result)
    return result


def write_desktop_witness(
    candidate_path: Path, provider_path: Path, thread_id: str, turn_id: str,
    observed_checks: set[str], output: Path,
) -> dict[str, Any]:
    _, digest = _candidate(Path(candidate_path).resolve())
    provider = Path(provider_path).resolve()
    if not provider.is_file() or observed_checks != DESKTOP_CHECKS:
        raise ValueError("fresh Desktop observations are incomplete")
    if not thread_id.strip() or not turn_id.strip():
        raise ValueError("fresh Desktop identity is incomplete")
    result = {
        "schema_version": OPENSCIENCE_HOST_SCHEMA,
        "status": "passed", "candidate_digest": digest, "fresh_identity": True,
        "terminal_status": "completed", "host_surface": "fresh-desktop-openscience",
        "provider_receipt_sha256": _sha256(provider), "sanitized": True,
        "checks": {name: True for name in sorted(observed_checks)},
        "thread_id_sha256": hashlib.sha256(thread_id.encode()).hexdigest(),
        "turn_id_sha256": hashlib.sha256(turn_id.encode()).hexdigest(),
        "raw_transcript_persisted": False, "credential_value_read_or_copied": False,
        "release_allowed": False,
    }
    _write_once(Path(output), result)
    return result


def build_fresh_desktop_acceptance(
    candidate_path: Path, cache_path: Path, hook_path: Path, witness_path: Path, output: Path,
) -> dict[str, Any]:
    _, digest = _candidate(Path(candidate_path).resolve())
    cache = _read(Path(cache_path).resolve(), "formal cache")
    hook = _read(Path(hook_path).resolve(), "Hook acceptance")
    witness = _read(Path(witness_path).resolve(), "Desktop witness")
    checks = {
        "exact_candidate_cache": (
            cache.get("schema_version") == "ds-lite.formal-cache-acceptance.v1"
            and cache.get("status") == "passed" and cache.get("candidate_digest") == digest
            and cache.get("expected_packages") == EXPECTED_PACKAGES
            and cache.get("observed_packages") == EXPECTED_PACKAGES
            and cache.get("model_request_made") is False
            and cache.get("raw_output_persisted") is False
        ),
        "candidate_hook_passed": (
            hook.get("schema_version") == "ds-lite.trusted-hook-acceptance.v1"
            and hook.get("status") == "passed" and hook.get("candidate_digest") == digest
            and hook.get("release_allowed") is False
        ),
        "fresh_desktop_terminal": (
            witness.get("schema_version") == OPENSCIENCE_HOST_SCHEMA
            and witness.get("status") == "passed" and witness.get("candidate_digest") == digest
            and witness.get("fresh_identity") is True
            and witness.get("terminal_status") == "completed"
            and witness.get("host_surface") == "fresh-desktop-openscience"
            and witness.get("sanitized") is True
            and _checks(witness.get("checks"), DESKTOP_CHECKS)
        ),
    }
    if not all(checks.values()):
        raise ValueError("fresh Desktop candidate contract failed")
    result = {
        "schema_version": "ds-lite.fresh-desktop-acceptance.v1",
        "status": "passed", "candidate_digest": digest, "candidate_bound": True,
        "evidence_class": "fresh-desktop-plus-isolated-candidate-cache",
        "checks": checks,
        "input_sha256": {
            "formal_cache": _sha256(Path(cache_path).resolve()),
            "hook": _sha256(Path(hook_path).resolve()),
            "desktop_witness": _sha256(Path(witness_path).resolve()),
        },
        "release_allowed": False,
    }
    _write_once(Path(output), result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    hook = sub.add_parser("hook")
    for name in ("candidate", "preparation", "host", "verifier", "repo-root", "output"):
        hook.add_argument("--" + name, required=True, type=Path)
    witness = sub.add_parser("witness")
    for name in ("candidate", "provider-receipt", "output"):
        witness.add_argument("--" + name, required=True, type=Path)
    witness.add_argument("--thread-id", required=True)
    witness.add_argument("--turn-id", required=True)
    witness.add_argument("--observed-check", action="append", default=[])
    fresh = sub.add_parser("fresh-desktop")
    for name in ("candidate", "formal-cache", "hook", "witness", "output"):
        fresh.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "hook":
            result = build_hook_acceptance(
                args.candidate, args.preparation, args.host, args.verifier,
                _candidate_identity(args.repo_root.resolve()), args.output,
            )
        elif args.command == "witness":
            result = write_desktop_witness(
                args.candidate, args.provider_receipt, args.thread_id, args.turn_id,
                set(args.observed_check), args.output,
            )
        else:
            result = build_fresh_desktop_acceptance(
                args.candidate, args.formal_cache, args.hook, args.witness, args.output,
            )
    except (OSError, UnicodeError, ValueError, FileExistsError):
        print(json.dumps({"status": "blocked", "reason": "host-candidate-acceptance-failed"}))
        return 2
    print(json.dumps({"status": result["status"], "candidate_digest": result["candidate_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
