#!/usr/bin/env python3
"""Fail-closed binding of observed Phase 5 receipts to one frozen candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


SCHEMAS = {
    "runtime-windows": "ds-lite.runtime-compatibility.v1",
    "runtime-linux": "ds-lite.runtime-compatibility.v1",
    "resource-windows": "ds-lite.phase5-resource.v1",
    "resource-linux": "ds-lite.phase5-resource.v1",
    "stable-v2-action": "ds-lite.phase5-real-codex-action-v2.v1",
    "dbos-upgrade": "ds-lite.phase5-dbos-upgrade.v1",
    "supervisor-windows": "ds-lite.phase5-user-supervisor.v1",
    "supervisor-wsl": "ds-lite.phase5-user-supervisor.v1",
    "real-host-chaos": "ds-lite.phase5-real-host-chaos.v1",
    "network-matrix": "ds-lite.phase5-network-disconnect.v1",
    "synthetic-provider": "ds-lite.phase5-synthetic-provider.v1",
    "backup-restore": "ds-lite.phase4-backup-recovery.v1",
}
PLATFORMS = {
    "runtime-windows": "windows-x86_64", "runtime-linux": "linux-x86_64",
    "resource-windows": "windows-x86_64", "resource-linux": "linux-x86_64",
}
SENSITIVE_KEYS = {
    "api_key", "credential", "credentials", "environment", "hidden_reasoning",
    "model_text", "password", "prompt", "raw_response", "raw_stderr",
    "raw_transcript", "secret", "token", "transcript",
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
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower().replace("-", "_") in SENSITIVE_KEYS:
                raise ValueError("preliminary receipt contains sensitive evidence")
            _reject_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_sensitive(nested)


def _all_checks(value: Any, required: set[str]) -> bool:
    return (
        isinstance(value, dict) and required.issubset(value)
        and all(value.get(name) is True for name in required)
    )


def _runtime(name: str, value: dict[str, Any]) -> bool:
    expected_python = "3.13.5" if name.endswith("windows") else "3.12.3"
    return (
        value.get("platform") == PLATFORMS[name]
        and value.get("codex_version") == "0.146.0"
        and value.get("dbos_version") == "2.29.0"
        and value.get("python_version") == expected_python
        and _all_checks(value.get("checks"), {
            "dbos", "dependency_lock", "dependency_root", "python", "runtime_pin",
        })
    )


def _resource(name: str, value: dict[str, Any]) -> bool:
    thresholds = value.get("thresholds")
    observed = {
        "action-growth": value.get("action_growth_bytes"),
        "controller-schema": value.get("controller_schema_bytes"),
        "empty-databases": value.get("empty_databases_bytes"),
        "install-delta": value.get("install_delta_bytes"),
        "rss-p95": value.get("rss_p95_bytes"),
    }
    return (
        value.get("platform") == PLATFORMS[name]
        and value.get("sample_count", 0) >= 30
        and value.get("raw_samples_persisted") is True
        and value.get("failed_thresholds") == []
        and isinstance(thresholds, dict)
        and all(
            isinstance(observed[key], (int, float))
            and isinstance(thresholds.get(key), (int, float))
            and observed[key] <= thresholds[key]
            for key in observed
        )
    )


def _v2_action(_: str, value: dict[str, Any]) -> bool:
    return (
        value.get("codex_version") == "0.146.0"
        and value.get("evidence_class") == "real-codex-ambient-provider"
        and value.get("controller_inspected_copied_or_modified_credentials") is False
        and value.get("raw_model_text_in_receipt") is False
        and _all_checks(value.get("checks"), {
            "bootstrap_terminal", "domain_integrity", "runtime_pin_valid",
            "single_action_workflow_identity", "single_canonical_thread",
            "single_terminal_host_event", "single_turn_start", "terminal_completed",
        })
    )


def _upgrade(_: str, value: dict[str, Any]) -> bool:
    return (
        value.get("old_dbos_version") == "2.28.0"
        and value.get("new_dbos_version") == "2.29.0"
        and value.get("workflow_rows") == 1
        and value.get("terminal_status") == "completed"
        and _all_checks(value.get("checks"), {
            "external_process_kill", "new_runtime", "old_runtime",
            "single_workflow_identity", "terminal_recovery",
        })
    )


def _supervisor(name: str, value: dict[str, Any]) -> bool:
    expected = "windows-task" if name.endswith("windows") else "systemd-user"
    return (
        value.get("supervisor_kind") == expected
        and value.get("generation_count") == 2
        and value.get("fence_epochs") == [1, 2]
        and _all_checks(value.get("checks"), {
            "cleanup_observed", "cross_process_restart", "fence_epoch_advanced",
            "heartbeat_each_generation", "old_fence_rejected", "two_generations",
            "user_level_supervisor",
        })
    )


def _chaos(_: str, value: dict[str, Any]) -> bool:
    counts = value.get("sample_counts")
    failures = value.get("preserved_failure_receipts")
    return (
        value.get("evidence_class") == "real-codex-ambient-provider"
        and isinstance(counts, dict)
        and all(counts.get(name, 0) >= 10 for name in (
            "controller", "app-server", "controller-and-app-server"
        ))
        and isinstance(failures, list) and bool(failures)
        and _all_checks(value.get("checks"), {
            "app_server_no_redispatch", "app_server_ten_passed", "both_no_redispatch",
            "both_ten_passed", "controller_response_loss_reconciled",
            "controller_ten_passed", "negative_run_preserved", "unique_identities",
        })
    )


def _network(_: str, value: dict[str, Any]) -> bool:
    samples = value.get("samples")
    return (
        value.get("evidence_class") == "real-codex-ambient-provider-loopback-connect-fault"
        and value.get("proxy_decrypted_content") is False
        and isinstance(samples, list) and len(samples) >= 10
        and all(
            isinstance(sample, dict) and sample.get("status") == "passed"
            and isinstance(sample.get("proxy"), dict)
            and sample["proxy"].get("drop_triggered") is True
            and sample["proxy"].get("content_persisted") is False
            for sample in samples
        )
    )


def _synthetic(_: str, value: dict[str, Any]) -> bool:
    samples = value.get("samples")
    by_status = {
        sample.get("status_code"): sample
        for sample in samples if isinstance(sample, dict)
    } if isinstance(samples, list) else {}
    return (
        value.get("evidence_class") == "real-codex/synthetic-provider"
        and value.get("real_openai_rate_limit_claimed") is False
        and value.get("raw_request_or_response_persisted") is False
        and set(by_status) == {429, 503}
        and all(sample.get("status") == "passed" and sample.get("request_count") == 1
                for sample in by_status.values())
        and by_status[429].get("retry_after_seconds") == 17
    )


def _backup(_: str, value: dict[str, Any]) -> bool:
    return (
        value.get("backup_schema") == "ds-lite.control-backup.v5"
        and value.get("restore_valid") is True
        and value.get("runtime_evidence_class") == "sqlite-backup-contract"
    )


VALIDATORS: dict[str, Callable[[str, dict[str, Any]], bool]] = {
    "runtime-windows": _runtime, "runtime-linux": _runtime,
    "resource-windows": _resource, "resource-linux": _resource,
    "stable-v2-action": _v2_action, "dbos-upgrade": _upgrade,
    "supervisor-windows": _supervisor, "supervisor-wsl": _supervisor,
    "real-host-chaos": _chaos, "network-matrix": _network,
    "synthetic-provider": _synthetic, "backup-restore": _backup,
}


def _write_once(path: Path, value: dict[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def revalidate(name: str, candidate_path: Path, preliminary_path: Path, output: Path) -> dict[str, Any]:
    if name not in SCHEMAS:
        raise ValueError("unsupported Phase 5 input")
    candidate_file = Path(candidate_path).resolve()
    preliminary_file = Path(preliminary_path).resolve()
    candidate = _read(candidate_file, "candidate")
    preliminary = _read(preliminary_file, "preliminary receipt")
    digest = candidate.get("candidate_digest")
    if (
        candidate.get("schema_version") != "ds-lite.phase5-release-candidate.v1"
        or not isinstance(digest, str) or len(digest) != 64
    ):
        raise ValueError("candidate contract failed")
    _reject_sensitive(preliminary)
    if (
        preliminary.get("schema_version") != SCHEMAS[name]
        or preliminary.get("status") != "passed"
        or preliminary.get("release_allowed") is not False
        or preliminary.get("candidate_digest") not in (None, digest)
        or not VALIDATORS[name](name, preliminary)
    ):
        raise ValueError("preliminary receipt contract failed")
    result = dict(preliminary)
    result.update({
        "candidate_digest": digest,
        "candidate_bound": True,
        "candidate_revalidation": {
            "input_name": name,
            "candidate_receipt_sha256": _sha256(candidate_file),
            "preliminary_receipt_sha256": _sha256(preliminary_file),
            "deterministic_contract": True,
            "historical_status_copied_without_verification": False,
        },
    })
    if _sha256(candidate_file) != result["candidate_revalidation"]["candidate_receipt_sha256"]:
        raise ValueError("candidate changed during revalidation")
    if _sha256(preliminary_file) != result["candidate_revalidation"]["preliminary_receipt_sha256"]:
        raise ValueError("preliminary receipt changed during revalidation")
    _write_once(Path(output), result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-name", required=True, choices=sorted(SCHEMAS))
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--preliminary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = revalidate(args.input_name, args.candidate, args.preliminary, args.output)
    except (OSError, UnicodeError, ValueError, FileExistsError):
        print(json.dumps({"status": "blocked", "reason": "candidate-revalidation-failed"}))
        return 2
    print(json.dumps({"status": result["status"], "candidate_digest": result["candidate_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
