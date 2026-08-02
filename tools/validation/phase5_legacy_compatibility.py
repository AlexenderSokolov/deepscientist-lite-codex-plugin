#!/usr/bin/env python3
"""Build candidate-bound legacy gate receipts from stronger Phase 5 evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


SPECS = {
    "source": ("ds-lite.upstream-audit.v1", {"ds-lite.upstream-audit.v1"}),
    "offline": ("ds-lite.offline-protocol-acceptance.v1", {
        "ds-lite.offline-protocol-acceptance.v1", "ds-lite.phase5-network-disconnect.v1",
    }),
    "cli": ("ds-lite.cli-acceptance.v1", {
        "ds-lite.runtime-compatibility.v1", "ds-lite.phase5-real-codex-action-v2.v1",
        "ds-lite.formal-cache-acceptance.v1",
    }),
    "delegation": ("ds-lite.real-delegation-acceptance.v1", {
        "ds-lite.real-delegation-acceptance.v1", "ds-lite.fresh-desktop-acceptance.v1",
    }),
    "docs": ("ds-lite.docs-acceptance.v1", {"ds-lite.docs-acceptance.v1"}),
    "provider": ("ds-lite.academic-provider-acceptance.v1", {
        "ds-lite.academic-provider-acceptance.v1", "ds-lite.openscience-acceptance.v1",
    }),
    "hook_in_turn_repair": ("ds-lite.hook-in-turn-repair.v1", {
        "ds-lite.trusted-hook-acceptance.v1",
    }),
    "session_control": ("ds-lite.app-server-conversation-control.v1", {
        "ds-lite.phase5-real-host-chaos.v1", "ds-lite.phase5-real-codex-action-v2.v1",
    }),
    "web": ("ds-lite.web-benchmark-acceptance.v1", {
        "ds-lite.web-benchmark-acceptance.v1", "ds-lite.fresh-desktop-acceptance.v1",
    }),
    "wsl": ("ds-lite.wsl-tmux-acceptance.v1", {
        "ds-lite.runtime-compatibility.v1", "ds-lite.phase5-resource.v1",
        "ds-lite.phase5-user-supervisor.v1",
    }),
}
SENSITIVE_KEYS = {
    "api_key", "credentials", "environment", "hidden_reasoning", "model_text",
    "password", "prompt", "raw_response", "raw_stderr", "raw_transcript", "secret", "token",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower().replace("-", "_") in SENSITIVE_KEYS:
                raise ValueError("sensitive evidence is not allowed")
            _reject_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested)


def _write_once(path: Path, value: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def build(
    gate: str, candidate_path: Path, inputs: list[tuple[str, Path]], output: Path,
) -> dict[str, Any]:
    if gate not in SPECS:
        raise ValueError("unsupported legacy gate")
    candidate_file = candidate_path.resolve()
    candidate = _read(candidate_file)
    digest = candidate.get("candidate_digest")
    if candidate.get("schema_version") != "ds-lite.phase5-release-candidate.v1" or not isinstance(digest, str):
        raise ValueError("candidate contract failed")
    output_schema, required_schemas = SPECS[gate]
    artifacts = []
    observed_schemas = set()
    current_candidate_support = gate in {"source", "docs"}
    for name, raw_path in inputs:
        path = raw_path.resolve()
        payload = _read(path)
        _reject_sensitive(payload)
        schema = payload.get("schema_version")
        if payload.get("status") != "passed" or not isinstance(schema, str):
            raise ValueError("nonpassing legacy evidence")
        observed_schemas.add(schema)
        bound = payload.get("candidate_digest") == digest
        current_candidate_support = current_candidate_support or bound
        artifacts.append({
            "name": name, "schema_version": schema, "sha256": _sha256(path),
            "candidate_bound": bound,
        })
    if observed_schemas != required_schemas or not current_candidate_support:
        raise ValueError("legacy evidence set is incomplete")
    result: dict[str, Any] = {
        "schema_version": output_schema,
        "status": "passed",
        "candidate_digest": digest,
        "candidate_bound": True,
        "evidence_class": "phase5-legacy-compatible-deterministic-adapter",
        "source_artifacts": sorted(artifacts, key=lambda item: item["name"]),
        "candidate_receipt_sha256": _sha256(candidate_file),
        "release_allowed": False,
    }
    if gate == "hook_in_turn_repair":
        hook = _read(inputs[0][1].resolve())
        checks = hook.get("checks", {})
        if not all(checks.get(name) is True for name in (
            "same_turn_stop_repair", "single_turn", "real_host_terminal",
        )):
            raise ValueError("Hook repair evidence is incomplete")
        result.update({
            "deterministic_verifier": True,
            "release_evidence": True,
            "verified_turn_id": "redacted:" + artifacts[0]["sha256"],
        })
    _write_once(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", required=True, choices=sorted(SPECS))
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    inputs = []
    try:
        for value in args.input:
            name, raw = value.split("=", 1)
            inputs.append((name, Path(raw)))
        result = build(args.gate, args.candidate, inputs, args.output)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, FileExistsError):
        print(json.dumps({"status": "blocked", "reason": "legacy-compatibility-failed"}))
        return 2
    print(json.dumps({"status": result["status"], "candidate_digest": result["candidate_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
