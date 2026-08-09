#!/usr/bin/env python3
"""Run one schema-bound blind review without exposing the arm mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from teaching import matched_effect
    from teaching import pilot_runtime
    from teaching import transport_diagnostics
except ModuleNotFoundError:  # pragma: no cover
    import matched_effect
    import pilot_runtime
    import transport_diagnostics

try:
    from teaching.runtime_identity import default_codex_version
except ModuleNotFoundError:  # pragma: no cover
    from runtime_identity import default_codex_version


MODEL = "gpt-5.6-sol"
REASONING_EFFORT = "low"
CODEX_VERSION = default_codex_version()
ALLOWED_REVIEWER_CODEX_VERSIONS = {
    CODEX_VERSION,
    "0.146.0-alpha.3.1",
    "0.146.0-alpha.9.2",
}


class BlindReviewError(RuntimeError):
    pass


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_once(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def prepare_reviewer_home(*, source_home: Path, target_home: Path) -> dict[str, Any]:
    """Create a fresh reviewer home containing only allow-listed provider routing."""
    source_home = source_home.resolve()
    target_home = target_home.resolve()
    if target_home.exists():
        raise BlindReviewError("reviewer home identity already exists")
    target_home.mkdir(parents=True, exist_ok=False)
    config_lines, provider_status = pilot_runtime.clone_nonsecret_provider_config(
        source_home, target_home
    )
    config_bytes = ("\n".join(config_lines) + "\n").encode("utf-8")
    config_path = target_home / "config.toml"
    with config_path.open("xb") as handle:
        handle.write(config_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    route = provider_status.get("route_fidelity", {})
    passed = (
        provider_status.get("status") == "copied"
        and provider_status.get("catalog_copied") is True
        and provider_status.get("provider_route_copied") is True
        and route.get("required_fields_match") is True
        and route.get("request_max_retries") == 0
        and route.get("stream_max_retries") == 0
    )
    receipt = {
        "schema_version": "ds-lite.blind-review-home-preparation.v1",
        "status": "passed" if passed else "blocked",
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "credential_files_copied": False,
        "provider_config": provider_status,
    }
    _write_once(target_home / "reviewer-home-preparation.json", receipt)
    if not passed:
        raise BlindReviewError("reviewer provider route is incomplete")
    return receipt


def codex_environment(codex_home: Path, *, ambient_home: bool) -> dict[str, str]:
    environment = os.environ.copy()
    if ambient_home:
        environment.pop("CODEX_HOME", None)
    else:
        environment["CODEX_HOME"] = str(codex_home.resolve())
    return environment


def parse_codex_version(output: str) -> str:
    prefix = "codex-cli "
    value = output.strip()
    if not value.startswith(prefix):
        raise BlindReviewError("Codex version output is invalid")
    version = value[len(prefix):]
    if version not in ALLOWED_REVIEWER_CODEX_VERSIONS:
        raise BlindReviewError("Codex reviewer version is not registered")
    return version


def import_desktop_review(
    *, pilot_root: Path, scores_path: Path, output_root: Path,
    thread_id: str, turn_id: str,
) -> dict[str, Any]:
    """Import one projectless Desktop review without persisting its transcript."""
    root = pilot_root.resolve()
    destination = output_root.resolve()
    if destination.exists():
        raise BlindReviewError("blind reviewer output identity already exists")
    if not thread_id or not turn_id:
        raise BlindReviewError("Desktop task identity is required")
    items = json.loads((root / "blind-review" / "blind-items.json").read_text(encoding="utf-8"))["items"]
    aliases = {item["alias"] for item in items if isinstance(item, dict) and isinstance(item.get("alias"), str)}
    scores = json.loads(scores_path.resolve().read_text(encoding="utf-8"))
    validated = matched_effect._validated_reviews(scores)
    if len(aliases) != 12 or set(validated) != aliases:
        raise BlindReviewError("Desktop review did not score the exact blind alias set")
    destination.mkdir(parents=True, exist_ok=False)
    _write_once(destination / "blind-scores.json", scores)
    output_ref = (destination / "blind-scores.json").relative_to(root).as_posix()
    execution = {
        "schema_version": "ds-lite.blind-review-execution.v1",
        "status": "completed",
        "call_count": 1,
        "input_refs": ["blind-review/blind-items.json", "blind-review/review-schema.json"],
        "output_ref": output_ref,
        "mapping_available_to_reviewer": False,
        "usage": {
            "total_tokens": None,
            "observation": "not-exposed-by-desktop-task-api",
        },
    }
    _write_once(destination / "blind-review-execution.json", execution)
    observation = {
        "schema_version": "ds-lite.blind-review-observation.v1",
        "status": "passed",
        "host_class": "desktop-app-projectless",
        "model": MODEL,
        "thread_id_sha256": _hash_text(thread_id),
        "turn_id_sha256": _hash_text(turn_id),
        "mapping_available_to_reviewer": False,
        "repository_available_to_reviewer": False,
        "artifact_access": "none-prompt-only",
        "raw_transcript_persisted_in_evidence": False,
        "raw_model_output_persisted_in_evidence": False,
    }
    _write_once(destination / "blind-review-observation.json", observation)
    return observation


def output_schema(aliases: list[str]) -> dict[str, Any]:
    score_properties = {
        metric: {"type": "integer", "minimum": 0, "maximum": 4}
        for metric in matched_effect.EXPRESSION_METRICS
    }
    score_properties["unsupported_completion_count"] = {"type": "integer", "minimum": 0}
    score_properties["alias"] = {"type": "string", "enum": sorted(aliases)}
    required = ["alias", *matched_effect.EXPRESSION_METRICS, "unsupported_completion_count"]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "scores"],
        "properties": {
            "schema_version": {"const": "ds-lite.blind-expression-score.v1"},
            "scores": {
                "type": "array", "minItems": len(aliases), "maxItems": len(aliases),
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": required, "properties": score_properties,
                },
            },
        },
    }


def reduce_events(lines: list[str]) -> dict[str, Any]:
    thread_ids: set[str] = set()
    terminal = False
    final_message = ""
    usage: dict[str, Any] = {}
    invalid = 0
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_ids.add(event["thread_id"])
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            final_message = str(item.get("text", ""))
        if event.get("type") == "turn.completed":
            terminal = True
            usage = event.get("usage", {}) if isinstance(event.get("usage"), dict) else {}
    total = usage.get("total_tokens")
    if not isinstance(total, int):
        inputs = usage.get("input_tokens", 0)
        outputs = usage.get("output_tokens", 0)
        total = inputs + outputs if isinstance(inputs, int) and isinstance(outputs, int) else 0
    if len(thread_ids) != 1 or not terminal or invalid or not final_message or total <= 0:
        raise BlindReviewError("blind reviewer did not produce one clean terminal turn")
    try:
        scores = json.loads(final_message)
    except json.JSONDecodeError as exc:
        raise BlindReviewError("blind reviewer output is not JSON") from exc
    validated = matched_effect._validated_reviews(scores)
    if len(validated) != 12:
        raise BlindReviewError("blind reviewer did not score all aliases")
    return {
        "scores": scores,
        "thread_id_sha256": _hash_text(next(iter(thread_ids))),
        "final_message_sha256": _hash_text(final_message),
        "usage_total_tokens": total,
    }


def redact_failure(
    *,
    stdout_lines: list[str],
    stderr: str,
    returncode: int,
    reason: str,
) -> dict[str, Any]:
    reducer = transport_diagnostics.TransportDiagnosticReducer()
    for line in stderr.splitlines(keepends=True):
        reducer.consume(line)
    thread_hashes: set[str] = set()
    terminal_completed = False
    terminal_failed = False
    invalid_lines = 0
    for line in stdout_lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type", ""))
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_hashes.add(_hash_text(event["thread_id"]))
        if event_type == "turn.completed":
            terminal_completed = True
        if event_type in {"turn.failed", "error", "response.failed"}:
            terminal_failed = True
            error = event.get("error") if isinstance(event.get("error"), dict) else {}
            reducer.consume_structured_error(
                str(error.get("message", "")),
                event_type,
                provider_code=error.get("code") if isinstance(error.get("code"), str) else None,
                provider_type=error.get("type") if isinstance(error.get("type"), str) else None,
                http_status=event.get("status") if isinstance(event.get("status"), int) else None,
            )
    diagnostic = reducer.finalize(
        exit_code=returncode,
        timed_out=False,
        turn_completed=terminal_completed,
        turn_failed=terminal_failed,
        child_process_state="exited",
        stdout_pipe_state="closed",
        stderr_pipe_state="closed",
    )
    return {
        "schema_version": "ds-lite.blind-review-failure.v1",
        "status": "blocked",
        "reason": reason,
        "failure_class": diagnostic["failure_class"],
        "http_status_category": diagnostic["http_status_category"],
        "provider_error_code": diagnostic["provider_error_code"],
        "provider_error_type": diagnostic["provider_error_type"],
        "thread_count": len(thread_hashes),
        "thread_id_sha256": sorted(thread_hashes),
        "terminal_completed": terminal_completed,
        "terminal_failed": terminal_failed,
        "invalid_stdout_line_count": invalid_lines,
        "stdout_sha256": _hash_text("\n".join(stdout_lines)),
        "stderr_line_count": diagnostic["stderr_line_count"],
        "stderr_sha256": diagnostic["stderr_sha256"],
        "raw_jsonl_persisted": False,
        "raw_model_output_persisted": False,
    }


def run(*, pilot_root: Path, codex_bin: Path, codex_home: Path, output_root: Path,
        source_codex_home: Path | None = None,
        ambient_home: bool = False,
        timeout_seconds: float = 600.0) -> dict[str, Any]:
    blind = pilot_root.resolve() / "blind-review"
    mapping = pilot_root.resolve() / "results" / "blind-map.json"
    if mapping.parent == blind or not (blind / "blind-items.json").is_file():
        raise BlindReviewError("blind package is incomplete")
    if output_root.exists():
        raise BlindReviewError("blind reviewer output identity already exists")
    if ambient_home and source_codex_home is not None:
        raise BlindReviewError("ambient and isolated reviewer homes are mutually exclusive")
    if source_codex_home is not None:
        prepare_reviewer_home(source_home=source_codex_home, target_home=codex_home)
    output_root.mkdir(parents=True, exist_ok=False)
    items = json.loads((blind / "blind-items.json").read_text(encoding="utf-8"))["items"]
    aliases = [item["alias"] for item in items]
    schema_path = output_root / "output-schema.json"
    _write_once(schema_path, output_schema(aliases))
    prompt = (
        "Read blind-items.json and REVIEW.md. Score every alias exactly once using the supplied "
        "rubric. Do not infer treatment labels or access parent/sibling directories. Return only "
        "the JSON object required by the output schema."
    )
    env = codex_environment(codex_home, ambient_home=ambient_home)
    version_probe = subprocess.run(
        [str(codex_bin.resolve()), "--version"], cwd=blind, env=env,
        text=True, encoding="utf-8", errors="replace", capture_output=True,
        timeout=30, check=False,
    )
    if version_probe.returncode != 0:
        raise BlindReviewError("Codex reviewer version probe failed")
    observed_codex_version = parse_codex_version(version_probe.stdout)
    command = [
        str(codex_bin.resolve()), "exec", "--json", "--ephemeral", "--model", MODEL,
        "-c", f'model_reasoning_effort="{REASONING_EFFORT}"', "-s", "read-only",
        "--skip-git-repo-check", "--ignore-rules", "-C", str(blind),
        "--output-schema", str(schema_path.resolve()), prompt,
    ]
    completed = subprocess.run(
        command, cwd=blind, env=env, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=timeout_seconds, check=False,
    )
    stdout_lines = completed.stdout.splitlines()
    if completed.returncode != 0:
        _write_once(
            output_root / "blind-review-failure.json",
            redact_failure(
                stdout_lines=stdout_lines,
                stderr=completed.stderr,
                returncode=completed.returncode,
                reason="process-failed",
            ),
        )
        raise BlindReviewError("blind reviewer process failed")
    try:
        reduced = reduce_events(stdout_lines)
    except BlindReviewError:
        _write_once(
            output_root / "blind-review-failure.json",
            redact_failure(
                stdout_lines=stdout_lines,
                stderr=completed.stderr,
                returncode=completed.returncode,
                reason="review-output-invalid",
            ),
        )
        raise
    scores_path = output_root / "blind-scores.json"
    _write_once(scores_path, reduced["scores"])
    execution = {
        "schema_version": "ds-lite.blind-review-execution.v1", "status": "completed",
        "call_count": 1,
        "input_refs": [
            "blind-review/blind-items.json",
            "blind-review/review-schema.json",
        ] + ([] if ambient_home else [
            f"homes/{codex_home.name}/reviewer-home-preparation.json",
        ]),
        "output_ref": f"{output_root.name}/blind-scores.json",
        "mapping_available_to_reviewer": False,
        "usage": {"total_tokens": reduced["usage_total_tokens"]},
    }
    _write_once(output_root / "blind-review-execution.json", execution)
    observation = {
        "schema_version": "ds-lite.blind-review-observation.v1", "status": "passed",
        "codex_version": observed_codex_version, "model": MODEL,
        "thread_id_sha256": reduced["thread_id_sha256"],
        "final_message_sha256": reduced["final_message_sha256"],
        "mapping_available_to_reviewer": False, "sandbox": "read-only",
        "approval_policy": "never", "raw_jsonl_persisted": False,
        "raw_model_output_persisted": False,
        "codex_home_mode": "ambient-home" if ambient_home else "isolated-home",
        "reviewer_home_preparation_sha256": hashlib.sha256(
            (codex_home / "reviewer-home-preparation.json").read_bytes()
        ).hexdigest() if (codex_home / "reviewer-home-preparation.json").is_file() else "not-observed",
        "credential_files_copied": False,
    }
    _write_once(output_root / "blind-review-observation.json", observation)
    return observation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", required=True, type=Path)
    parser.add_argument("--codex-bin", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--source-codex-home", type=Path)
    parser.add_argument("--ambient-home", action="store_true")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()
    try:
        result = run(
            pilot_root=args.pilot_root, codex_bin=args.codex_bin,
            codex_home=args.codex_home, output_root=args.output_root,
            source_codex_home=args.source_codex_home,
            ambient_home=args.ambient_home,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, BlindReviewError) as exc:
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__}))
        return 2
    print(json.dumps({"status": result["status"], "thread_id_sha256": result["thread_id_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
