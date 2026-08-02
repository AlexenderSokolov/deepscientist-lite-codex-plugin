#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA = "ds-lite.openscience-acceptance.v1"
PROVIDER_SCHEMA = "ds-lite.academic-provider-acceptance.v1"
HOST_SCHEMA = "ds-lite.openscience-host-observation.v1"
PROVIDERS = ("crossref", "openalex", "semantic-scholar", "arxiv")
AVAILABLE_PROVIDER_STATUSES = {"matched", "not-found", "not-applicable"}
REQUIRED_HOST_CHECKS = {
    "fresh_desktop_observed", "openscience_task_observed", "terminal_observed",
}
SENSITIVE_KEYS = {
    "api_key", "access_token", "auth_token", "authorization", "cookie",
    "credential", "credentials", "env", "environment", "environment_dump",
    "headers", "hidden_reasoning", "model_text", "password", "prompt",
    "raw_model_text", "raw_output", "raw_prompt", "raw_response",
    "raw_stderr", "raw_transcript", "secret", "stderr", "token", "transcript",
}


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_sensitive(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS:
                raise ValueError(f"{label} contains sensitive evidence")
            _reject_sensitive(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested, label)
    elif isinstance(value, str):
        if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
            raise ValueError(f"{label} contains sensitive private path")


def _read_snapshot(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        content = path.read_bytes()
        payload = json.loads(content.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is not a readable JSON object")
    _reject_sensitive(payload, label)
    return payload, hashlib.sha256(content).hexdigest()


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _artifact(path: Path, payload: dict[str, Any], digest: str) -> dict[str, str]:
    return {
        "file": path.name,
        "schema_version": str(payload.get("schema_version", "")),
        "sha256": digest,
    }


def build_acceptance(
    candidate_digest: str,
    preliminary_provider_receipt: Path,
    fresh_host_receipt: Path,
    output: Path,
) -> dict[str, Any]:
    if not _valid_digest(candidate_digest):
        raise ValueError("candidate digest must be a SHA-256 value")
    provider_path = Path(preliminary_provider_receipt).resolve()
    host_path = Path(fresh_host_receipt).resolve()
    provider, provider_hash = _read_snapshot(provider_path, "preliminary provider receipt")
    host, host_hash = _read_snapshot(host_path, "fresh OpenScience host receipt")

    provider_names = provider.get("providers")
    provider_statuses = provider.get("provider_statuses")
    all_providers_present = (
        isinstance(provider_names, list)
        and len(provider_names) == len(PROVIDERS)
        and all(isinstance(name, str) for name in provider_names)
        and set(provider_names) == set(PROVIDERS)
        and isinstance(provider_statuses, dict)
        and set(provider_statuses) == set(PROVIDERS)
    )
    all_providers_available = bool(
        all_providers_present
        and all(
            isinstance(status, str) and status in AVAILABLE_PROVIDER_STATUSES
            for status in provider_statuses.values()
        )
    )
    host_checks = host.get("checks")
    deterministic_host_checks = bool(
        isinstance(host_checks, dict)
        and REQUIRED_HOST_CHECKS.issubset(host_checks)
        and all(host_checks.get(name) is True for name in REQUIRED_HOST_CHECKS)
    )

    checks = {
        "provider_schema_match": provider.get("schema_version") == PROVIDER_SCHEMA,
        "preliminary_provider_receipt": (
            provider.get("evidence_stage") == "preliminary"
            and provider.get("candidate_bound") is False
            and provider.get("candidate_digest") is None
            and provider.get("sanitized") is True
            and provider.get("host_acceptance_substitute") is False
        ),
        "provider_probe_passed": (
            provider.get("status") == "passed"
            and provider.get("reason") == "authorized-live-providers-observed"
            and provider.get("authorized_external_provider") is True
            and provider.get("network_attempted") is True
            and provider.get("unverified_items") == []
        ),
        "all_providers_present": all_providers_present,
        "all_providers_available": all_providers_available,
        "independent_fresh_host_receipt": (
            host_path != provider_path and host.get("schema_version") == HOST_SCHEMA
        ),
        "fresh_host_passed": host.get("status") == "passed",
        "fresh_host_candidate_match": host.get("candidate_digest") == candidate_digest,
        "fresh_host_identity": host.get("fresh_identity") is True,
        "fresh_host_terminal": host.get("terminal_status") == "completed",
        "fresh_host_surface": host.get("host_surface") == "fresh-desktop-openscience",
        "fresh_host_provider_evidence_bound": host.get("provider_receipt_sha256") == provider_hash,
        "fresh_host_sanitized": host.get("sanitized") is True,
        "fresh_host_checks_passed": deterministic_host_checks,
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": SCHEMA,
        "status": "passed" if passed else "blocked",
        "reason": (
            "candidate-bound-openscience-observed"
            if passed else "candidate-bound-openscience-incomplete"
        ),
        "candidate_digest": candidate_digest,
        "candidate_bound": True,
        "sanitized": True,
        "provider_probe_substituted_for_host": False,
        "checks": checks,
        "inputs": {
            "preliminary_provider": _artifact(provider_path, provider, provider_hash),
            "fresh_openscience_host": _artifact(host_path, host, host_hash),
        },
        "release_allowed": False,
    }
    if _sha256(provider_path) != provider_hash or _sha256(host_path) != host_hash:
        raise ValueError("input changed during acceptance")
    _write_once(Path(output), receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build one candidate-bound OpenScience acceptance receipt.",
    )
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--preliminary-provider", required=True, type=Path)
    parser.add_argument("--fresh-host", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_acceptance(
            args.candidate_digest, args.preliminary_provider, args.fresh_host, args.output,
        )
    except FileExistsError:
        print(json.dumps({"schema_version": SCHEMA, "status": "blocked", "reason": "output-exists"}))
        return 2
    except ValueError:
        print(json.dumps({"schema_version": SCHEMA, "status": "blocked", "reason": "input-rejected"}))
        return 2
    print(json.dumps({"schema_version": SCHEMA, "status": receipt["status"], "reason": receipt["reason"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
