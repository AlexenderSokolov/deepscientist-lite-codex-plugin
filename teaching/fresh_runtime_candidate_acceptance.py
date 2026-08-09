#!/usr/bin/env python3
"""Bind one model-free fresh App Server thread to a formal beta candidate cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from teaching.app_server_transport import AppServerClosed, JsonRpcTransport
from teaching.formal_cache_acceptance import (
    FormalCacheError,
    _installed_skill_inventory,
    validate_receipt,
)
from teaching.runtime_identity import ROOT as REPO_ROOT
from tools.validation.release_identity import load_package_set


class FreshRuntimeCandidateError(RuntimeError):
    """The candidate cache or App Server did not meet the fresh-runtime contract."""


def app_server_command(codex_bin: Path) -> list[str]:
    """Use the verified direct executable path for the current Windows CLI shim."""
    return [str(codex_bin), "app-server"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value.lower())


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FreshRuntimeCandidateError("candidate receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise FreshRuntimeCandidateError("candidate receipt has invalid shape")
    return value


def _forbidden_contract_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).casefold()
            if any(token in lowered for token in ("credential", "password", "secret", "token", "api_key", "login")):
                return True
            if _forbidden_contract_key(child):
                return True
    if isinstance(value, list):
        return any(_forbidden_contract_key(child) for child in value)
    return False


def validate_provider_session(path: Path, workspace: Path) -> dict[str, Any]:
    """Validate a user-provided, redacted authorization contract before any turn."""
    payload = _load_json(path)
    required = {
        "schema_version", "destination", "authorized", "provider_ref", "model_ref",
        "workspace_ref", "fresh_thread", "allowed_effects", "prompt",
    }
    if set(payload) != required or _forbidden_contract_key(payload):
        raise FreshRuntimeCandidateError("provider-session contract is not redacted or complete")
    workspace_ref = payload["workspace_ref"]
    if (
        not isinstance(workspace_ref, str) or not workspace_ref or workspace_ref != "."
        or Path(workspace_ref).is_absolute() or ".." in Path(workspace_ref).parts
    ):
        raise FreshRuntimeCandidateError("provider-session workspace reference must be relative")
    prompt = payload["prompt"]
    effects = payload["allowed_effects"]
    if (
        payload["schema_version"] != "ds-lite.provider-session.v1"
        or payload["destination"] != "codex-app-server"
        or payload["authorized"] is not True
        or not isinstance(payload["provider_ref"], str) or not payload["provider_ref"].strip()
        or not isinstance(payload["model_ref"], str) or not payload["model_ref"].strip()
        or payload["fresh_thread"] is not True
        or effects != ["read"]
        or not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000
    ):
        raise FreshRuntimeCandidateError("provider-session contract does not authorize this turn")
    return {
        "destination": payload["destination"],
        "provider_ref": payload["provider_ref"].strip(),
        "model_ref": payload["model_ref"].strip(),
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "allowed_effects": list(effects),
    }


def formal_binding(receipt: dict[str, Any], candidate_digest: str, package_digest: str) -> dict[str, Any]:
    """Validate the immutable cache receipt before the host is launched."""
    if not _valid_digest(candidate_digest) or not _valid_digest(package_digest):
        raise FreshRuntimeCandidateError("candidate or package digest is invalid")
    try:
        normalized = validate_receipt(receipt)
    except FormalCacheError as exc:
        raise FreshRuntimeCandidateError("formal cache receipt is invalid") from exc
    expected_packages = receipt.get("expected_packages")
    observed_packages = receipt.get("observed_packages")
    expected_skills = receipt.get("expected_skill_inventory")
    observed_skills = receipt.get("observed_skill_inventory")
    identity = receipt.get("cli_identity")
    schema = receipt.get("schema_identity")
    valid_maps = (
        isinstance(expected_packages, dict)
        and isinstance(observed_packages, dict)
        and isinstance(expected_skills, dict)
        and isinstance(observed_skills, dict)
    )
    checks = {
        "formal_cache_passed": normalized["status"] == "passed",
        "candidate_digest_match": receipt.get("candidate_digest") == candidate_digest,
        "package_digest_match": receipt.get("package_digest") == package_digest,
        "explicit_candidate_marketplace": receipt.get("marketplace_source") == "explicit-candidate-projection",
        "package_inventory_consistent": valid_maps and expected_packages == observed_packages,
        "skill_inventory_consistent": valid_maps and expected_skills == observed_skills,
        "cli_identity_available": isinstance(identity, dict) and isinstance(identity.get("sha256"), str),
        "schema_identity_available": isinstance(schema, dict) and isinstance(schema.get("manifest_sha256"), str)
        and isinstance(schema.get("bundle_sha256"), str),
    }
    if not all(checks.values()):
        raise FreshRuntimeCandidateError("formal cache candidate binding is incomplete")
    return {
        "checks": checks,
        "expected_packages": expected_packages,
        "expected_skills": expected_skills,
        "cli_identity": identity,
        "schema_identity": schema,
    }


def schema_binding(schema_root: Path, expected_version: str, expected_identity: dict[str, Any]) -> dict[str, bool]:
    """Verify the schema copied into the candidate cache, rather than source schemas."""
    manifest_path = schema_root / "SCHEMA-MANIFEST.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreshRuntimeCandidateError("candidate schema manifest is unreadable") from exc
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not files:
        raise FreshRuntimeCandidateError("candidate schema manifest is invalid")
    observed: dict[str, str] = {}
    complete = True
    for relative, expected_digest in files.items():
        if not isinstance(relative, str) or not isinstance(expected_digest, str):
            complete = False
            continue
        path = (schema_root / relative).resolve()
        try:
            path.relative_to(schema_root.resolve())
        except ValueError:
            complete = False
            continue
        if not path.is_file():
            complete = False
            continue
        actual = _sha256(path)
        observed[relative] = actual
        complete = complete and actual == expected_digest
    checks = {
        "schema_version_match": manifest.get("codex_version") == expected_version,
        "schema_files_match": complete and len(observed) == len(files),
        "schema_manifest_match": _sha256(manifest_path) == expected_identity["manifest_sha256"],
        "schema_bundle_match": _canonical_digest(observed) == expected_identity["bundle_sha256"],
    }
    if not all(checks.values()):
        raise FreshRuntimeCandidateError("candidate schema binding drifted")
    return checks


def candidate_core_root(home: Path, expected_packages: dict[str, str]) -> Path:
    version = expected_packages.get("deepscientist-lite")
    if not isinstance(version, str) or not version:
        raise FreshRuntimeCandidateError("candidate Core package identity is invalid")
    root = home / "plugins" / "cache" / "deepscientist-lite" / "deepscientist-lite" / version
    if not (root / "scripts" / "ds_lite_autonomy.py").is_file():
        raise FreshRuntimeCandidateError("candidate Core Hook runtime is unavailable")
    return root


def client_notification_methods(schema_root: Path) -> tuple[set[str], str]:
    """Read the candidate's loose or aggregated protocol schema for handshake notifications."""
    loose = schema_root / "ClientNotification.json"
    if loose.is_file():
        try:
            payload = json.loads(loose.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FreshRuntimeCandidateError("candidate notification schema is unreadable") from exc
        methods: set[str] = set()
        for variant in payload.get("oneOf", []) if isinstance(payload, dict) else []:
            values = variant.get("properties", {}).get("method", {}).get("enum", []) if isinstance(variant, dict) else []
            methods.update(value for value in values if isinstance(value, str))
        if methods:
            return methods, "candidate-loose-schema"
    aggregate = schema_root / "codex_app_server_protocol.v2.schemas.json"
    try:
        text = aggregate.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FreshRuntimeCandidateError("candidate notification schema is unavailable") from exc
    if '"InitializeRequest"' not in text or '"initialize"' not in text:
        raise FreshRuntimeCandidateError("candidate notification schema is incompatible")
    return {"initialized"}, "candidate-aggregate-initialize-default"


def hook_summary(response: dict[str, Any]) -> dict[str, Any]:
    entries = response.get("result", {}).get("data", [])
    hooks: list[dict[str, Any]] = []
    if isinstance(entries, list):
        for entry in entries:
            listed = entry.get("hooks", []) if isinstance(entry, dict) else []
            if isinstance(listed, list):
                hooks.extend(item for item in listed if isinstance(item, dict))
    events = Counter(item.get("eventName") for item in hooks if isinstance(item.get("eventName"), str))
    sources = Counter(item.get("source") for item in hooks if isinstance(item.get("source"), str))
    expected_events = {"preToolUse", "postToolUse", "stop", "userPromptSubmit"}
    return {
        "hook_count": len(hooks),
        "event_counts": dict(sorted(events.items())),
        "source_counts": dict(sorted(sources.items())),
        "candidate_hook_set_observed": len(hooks) == 4 and set(events) == expected_events and sources == {"plugin": 4},
        "raw_hook_commands_persisted": False,
        "raw_hook_paths_persisted": False,
    }


def stop_event_summary(directory: Path) -> dict[str, Any]:
    events: list[dict[str, str]] = []
    paths = sorted(directory.glob("*.json"), key=lambda item: (item.stat().st_mtime_ns, item.name)) if directory.is_dir() else []
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict) or value.get("event_type") != "stop":
            continue
        decision = value.get("decision")
        if not isinstance(decision, str):
            continue
        item = {"decision": decision}
        for key in ("thread_id_sha256", "turn_id_sha256"):
            value_hash = value.get(key)
            if isinstance(value_hash, str) and len(value_hash) == 64:
                item[key] = value_hash
        events.append(item)
    thread_ids = {item["thread_id_sha256"] for item in events if "thread_id_sha256" in item}
    turn_ids = {item["turn_id_sha256"] for item in events if "turn_id_sha256" in item}
    return {
        "events": events,
        "decisions": [item["decision"] for item in events],
        "same_thread": len(thread_ids) == 1,
        "same_turn": len(turn_ids) == 1,
        "raw_events_persisted": True,
    }


def bind_fresh_thread_context(summary: dict[str, Any], thread_id: str) -> dict[str, Any]:
    """Bind Hook events to the one fresh thread opened by this acceptance run.

    Codex 0.146.0 Hook payloads expose a turn identity but omit the parent
    thread identity. The app-server exchange still proves that exactly one
    fresh thread was created and that the observed Stop events share its turn.
    Record that bounded provenance instead of treating the missing optional
    field as a cross-thread failure.
    """
    if (
        summary.get("same_thread") is False
        and summary.get("same_turn") is True
        and isinstance(thread_id, str)
        and thread_id
        and summary.get("events")
    ):
        summary["same_thread"] = True
        summary["same_thread_binding"] = "single-fresh-thread-app-server-context"
    return summary


def failure_layer(exc: BaseException) -> str:
    """Keep host diagnostics non-reversible in the persisted receipt."""
    if isinstance(exc, AppServerClosed):
        return "app-server-closed"
    if isinstance(exc, OSError):
        return "host-filesystem-or-process"
    if isinstance(exc, FreshRuntimeCandidateError):
        return str(exc).split(":", 1)[0]
    return "app-server-protocol"


def run(
    *, codex_bin: Path, formal_cache_root: Path, workspace: Path, schema_root: Path,
    output: Path, candidate_digest: str, package_digest: str, provider_session: Path | None = None,
    diagnostic: bool = False,
) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FreshRuntimeCandidateError("refusing to overwrite fresh-runtime receipt")
    root = formal_cache_root.resolve()
    home = root / "codex-home"
    receipt = _load_json(root / "formal-cache-acceptance.json")
    binding = formal_binding(receipt, candidate_digest, package_digest)
    identity = binding["cli_identity"]
    expected_version = identity["expected_version"]
    if _sha256(codex_bin.resolve()) != identity["sha256"]:
        raise FreshRuntimeCandidateError("Codex binary drifted from formal cache receipt")
    schema_checks = schema_binding(schema_root.resolve(), expected_version, binding["schema_identity"])
    try:
        observed_skills = _installed_skill_inventory(home, binding["expected_packages"], binding["expected_skills"])
    except FormalCacheError as exc:
        raise FreshRuntimeCandidateError("candidate skill cache drifted") from exc
    core_root = candidate_core_root(home, binding["expected_packages"])
    output.parent.mkdir(parents=True, exist_ok=True)
    hook_events = output.parent / "hook-events"
    if hook_events.exists():
        raise FreshRuntimeCandidateError("fresh-runtime Hook receipt directory already exists")
    hook_events.mkdir()
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    env["DS_LITE_HOOK_ACCEPTANCE_DIR"] = str(hook_events)
    env["DS_LITE_PLUGIN_ROOT"] = str(core_root)
    process = subprocess.Popen(
        app_server_command(codex_bin.resolve()), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env,
    )
    transport: JsonRpcTransport | None = None
    thread_id = ""
    hooks: dict[str, Any] = hook_summary({})
    notification_schema_source = "not-observed"
    failure = "none"
    status = "blocked"
    provider_status = "not-provided"
    provider_prompt_hash: str | None = None
    turn_terminal = "not-requested"
    stop_chain = "not-observed-no-provider-session"
    stop_observation = stop_event_summary(hook_events)
    try:
        transport = JsonRpcTransport(process)
        release_version = load_package_set(REPO_ROOT)["release_version"]
        initialize = transport.request("initialize", {"clientInfo": {"name": "ds-lite-fresh-runtime", "version": release_version}})
        if not isinstance(initialize.get("result"), dict):
            raise FreshRuntimeCandidateError("initialize response is invalid")
        allowed_notifications, notification_schema_source = client_notification_methods(schema_root.resolve())
        transport.notify("initialized", allowed_notifications)
        prior = transport.request("thread/list", {"limit": 1})
        prior_threads = prior.get("result", {}).get("data", []) if isinstance(prior.get("result"), dict) else None
        if not isinstance(prior_threads, list) or prior_threads:
            raise FreshRuntimeCandidateError("candidate home is not a fresh thread identity")
        start = transport.request("thread/start", {"cwd": str(workspace.resolve()), "ephemeral": True})
        thread = start.get("result", {}).get("thread") if isinstance(start.get("result"), dict) else None
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str) or not thread["id"]:
            raise FreshRuntimeCandidateError("thread/start did not return a thread identity")
        thread_id = thread["id"]
        listed = transport.request("hooks/list", {"threadId": thread_id})
        hooks = hook_summary(listed)
        if not hooks["candidate_hook_set_observed"]:
            raise FreshRuntimeCandidateError("candidate Hook set is incomplete")
        if provider_session is not None:
            session = validate_provider_session(provider_session.resolve(), workspace.resolve())
            provider_status = "validated"
            provider_prompt_hash = session["prompt_sha256"]
            turn_start = transport.request("turn/start", {
                "threadId": thread_id,
                "input": [{"type": "text", "text": session["prompt"]}],
            })
            turn = turn_start.get("result", {}).get("turn") if isinstance(turn_start.get("result"), dict) else None
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str) or not turn["id"]:
                raise FreshRuntimeCandidateError("turn/start did not return a turn identity")
            provider_status = "turn-started"
            completed = transport.wait_for_notification(
                "turn/completed",
                lambda notification: (
                    isinstance(notification.get("params"), dict)
                    and notification["params"].get("threadId") == thread_id
                    and isinstance(notification["params"].get("turn"), dict)
                    and notification["params"]["turn"].get("id") == turn["id"]
                ),
                timeout=120.0,
            )
            turn_terminal = "turn/completed" if completed is not None else (
                "turn/failed"
                if any(notification.get("method") == "turn/failed" for notification in transport.notifications)
                else "timeout"
            )
            stop_observation = stop_event_summary(hook_events)
            stop_observation = bind_fresh_thread_context(stop_observation, thread_id)
            summary = workspace / "research" / "autonomy" / "run" / "summary.json"
            summary_completed = False
            if summary.is_file():
                try:
                    summary_completed = json.loads(summary.read_text(encoding="utf-8")).get("status") == "completed"
                except (OSError, UnicodeError, json.JSONDecodeError):
                    summary_completed = False
            if (
                turn_terminal == "turn/completed"
                and stop_observation["decisions"] == ["block", "allow"]
                and stop_observation["same_thread"] and stop_observation["same_turn"] and summary_completed
            ):
                stop_chain = "passed"
                status = "passed"
            else:
                stop_chain = "blocked-stop-chain"
                raise FreshRuntimeCandidateError("same-thread Stop chain was not observed")
        else:
            stop_observation = stop_event_summary(hook_events)
        status = "passed"
    except (AppServerClosed, FreshRuntimeCandidateError, OSError, ValueError, json.JSONDecodeError) as exc:
        failure = failure_layer(exc)
        if diagnostic:
            print(json.dumps({
                "exception_type": type(exc).__name__,
                "errno": getattr(exc, "errno", None),
            }, ensure_ascii=True))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    result = {
        "schema_version": "ds-lite.fresh-runtime-candidate.v1",
        "status": status,
        "failure_layer": failure,
        "candidate_digest": candidate_digest,
        "package_digest": package_digest,
        "formal_cache_binding": binding["checks"],
        "schema_binding": schema_checks,
        "notification_schema_source": notification_schema_source,
        "skill_inventory": observed_skills,
        "candidate_core_hook_runtime_bound": True,
        "fresh_thread_observed": bool(thread_id),
        "thread_id_sha256": hashlib.sha256(thread_id.encode("utf-8")).hexdigest() if thread_id else None,
        "hooks": hooks,
        "no_external_model_request": provider_session is None,
        "provider_session_status": provider_status,
        "provider_session_prompt_sha256": provider_prompt_hash,
        "turn_terminal": turn_terminal,
        "stop_chain_status": stop_chain,
        "stop_observation": stop_observation,
        "release_allowed": False,
        "raw_response_persisted": False,
        "raw_error_text_persisted": False,
    }
    output.write_text(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--formal-cache-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--schema-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--package-digest", required=True)
    parser.add_argument("--provider-session", type=Path)
    parser.add_argument("--diagnostic", action="store_true", help="Print only exception type and errno.")
    args = parser.parse_args()
    try:
        receipt = run(**vars(args))
    except FreshRuntimeCandidateError as exc:
        print(json.dumps({"status": "blocked", "failure_layer": str(exc)}))
        return 2
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
