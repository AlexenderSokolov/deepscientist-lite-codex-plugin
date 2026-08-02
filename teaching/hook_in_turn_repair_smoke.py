"""Run one isolated, schema-bound real Hook same-turn repair smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from teaching.app_server_transport import JsonRpcTransport, validate_params
from teaching.canonical_thread_smoke import (
    _terminal_turn_diagnostic,
    _thread_id,
    _turn_id,
    app_server_command,
    client_notification_methods,
)
from teaching.hook_in_turn_repair_acceptance import evaluate_observation
from teaching.pilot_runtime import clone_nonsecret_provider_config
from teaching.trusted_hook_fixture import prepare as prepare_fixture


METHOD_SCHEMAS = {
    "initialize": "v1/InitializeParams.json",
    "plugin/list": "v2/PluginListParams.json",
    "plugin/install": "v2/PluginInstallParams.json",
    "hooks/list": "v2/HooksListParams.json",
    "thread/start": "v2/ThreadStartParams.json",
    "turn/start": "v2/TurnStartParams.json",
    "thread/archive": "v2/ThreadArchiveParams.json",
}


def _schema_digest(schema_root: Path) -> str:
    bundle = schema_root / "codex_app_server_protocol.v2.schemas.json"
    if not bundle.is_file():
        raise RuntimeError("generated-schema-bundle-missing")
    return hashlib.sha256(bundle.read_bytes()).hexdigest()


def _message_class(message: str) -> str:
    lowered = message.casefold()
    categories = (
        ("trust", ("trust", "untrusted")),
        ("model-config", ("model", "catalog")),
        ("authentication", ("auth", "api key", "401", "credential")),
        ("plugin", ("plugin", "hook")),
        ("path", ("path", "file", "directory", "not found")),
    )
    for category, needles in categories:
        if any(needle in lowered for needle in needles):
            return category
    return "other"


def _contract(schema_root: Path) -> dict[str, dict]:
    result = {}
    for method, relative in METHOD_SCHEMAS.items():
        payload = json.loads((schema_root / relative).read_text(encoding="utf-8"))
        result[method] = {
            "required": payload.get("required", []),
            "properties": sorted(payload.get("properties", {})),
        }
    return result


def _request(transport: JsonRpcTransport, contract: dict, method: str, params: dict) -> dict:
    validate_params(method, params, contract)
    response = transport.request(method, params)
    if "result" not in response:
        error = response.get("error") if isinstance(response.get("error"), dict) else {}
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        raise RuntimeError(
            f"{method}-response-gap-{_message_class(message)}-"
            f"{hashlib.sha256(message.encode()).hexdigest()[:12]}"
        )
    return response["result"]


def _hook_app_server_command(codex_bin: Path) -> list[str]:
    binary = codex_bin.resolve()
    if os.name == "nt" and binary.suffix.casefold() == ".cmd":
        return [
            "cmd.exe", "/d", "/s", "/c",
            f'"{binary}" --dangerously-bypass-hook-trust app-server',
        ]
    return [str(binary), "--dangerously-bypass-hook-trust", "app-server"]


def _open_app_server(codex_bin: Path, env: dict[str, str], schema_root: Path) -> tuple[subprocess.Popen, JsonRpcTransport, dict]:
    command = _hook_app_server_command(codex_bin)
    process = subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
    )
    transport = JsonRpcTransport(process, response_timeout=60.0)
    contract = _contract(schema_root)
    _request(transport, contract, "initialize", {"clientInfo": {"name": "ds-lite-hook-smoke", "version": "0.8.1"}})
    transport.notify("initialized", client_notification_methods(schema_root))
    return process, transport, contract


def _stop_app_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _hook_summary(result: dict, plugin_name: str) -> dict:
    entries = result.get("data") if isinstance(result, dict) else None
    hooks = []
    errors = 0
    error_classes = []
    warnings = 0
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_errors = entry.get("errors", []) if isinstance(entry.get("errors"), list) else []
            entry_warnings = entry.get("warnings", []) if isinstance(entry.get("warnings"), list) else []
            errors += len(entry_errors)
            warnings += len(entry_warnings)
            for error in entry_errors:
                message = error.get("message") if isinstance(error, dict) and isinstance(error.get("message"), str) else ""
                error_classes.append({
                    "class": _message_class(message),
                    "message_sha256": hashlib.sha256(message.encode()).hexdigest(),
                })
            for hook in entry.get("hooks", []):
                if isinstance(hook, dict) and plugin_name in str(hook.get("pluginId", "")):
                    hooks.append(hook)
    return {
        "count": len(hooks),
        "enabled_count": sum(hook.get("enabled") is True for hook in hooks),
        "events": sorted({str(hook.get("eventName")) for hook in hooks}),
        "sources": sorted({str(hook.get("source")) for hook in hooks}),
        "trust_counts": {
            status: sum(hook.get("trustStatus") == status for hook in hooks)
            for status in sorted({str(hook.get("trustStatus")) for hook in hooks})
        },
        "error_count": errors,
        "warning_count": warnings,
        "errors": error_classes,
    }


def _plugin_install_target(listing: dict, plugin_name: str) -> tuple[str, dict]:
    marketplaces = listing.get("marketplaces") if isinstance(listing, dict) else None
    if not isinstance(marketplaces, list):
        raise RuntimeError("plugin-list-shape")
    for marketplace in marketplaces:
        if not isinstance(marketplace, dict) or not isinstance(marketplace.get("path"), str):
            continue
        for plugin in marketplace.get("plugins", []):
            if isinstance(plugin, dict) and plugin.get("name") == plugin_name:
                source = plugin.get("source") if isinstance(plugin.get("source"), dict) else {}
                return marketplace["path"], {
                    "found": True,
                    "installed": plugin.get("installed") is True,
                    "enabled": plugin.get("enabled") is True,
                    "source_type": source.get("type"),
                    "marketplace_path_sha256": hashlib.sha256(marketplace["path"].encode()).hexdigest(),
                }
    raise RuntimeError("plugin-not-listed")


def _event_observation(events_dir: Path, notifications: list[dict], thread: str, turn: str) -> dict:
    events = []
    for path in sorted(events_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns):
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            events.append(value)
    hook_turns = []
    for notification in notifications:
        if notification.get("method") != "hook/completed":
            continue
        params = notification.get("params")
        run = params.get("run") if isinstance(params, dict) else None
        if isinstance(params, dict) and isinstance(run, dict) and run.get("eventName") == "stop":
            hook_turns.append((params.get("threadId"), params.get("turnId")))
    stops = [event for event in events if event.get("event_type") == "stop"]
    stop_events = [{
        "turn_id": turn,
        "decision": event.get("decision"),
        "reason": "reason-present" if event.get("reason_present") is True else "",
        "stop_hook_active": event.get("stop_hook_active") is True,
    } for event in stops]
    exact_hook_turns = bool(hook_turns) and all(item == (thread, turn) for item in hook_turns)
    handoff = bool(stops) and stops[-1].get("control_action") == "hook-handoff"
    return {
        "evidence_class": "real-host",
        "controller_turn_start_count": 1,
        "stop_events": stop_events,
        "terminal": {"kind": "hook_handoff" if handoff and exact_hook_turns else "unverified", "turn_id": turn},
        "hook_notification_count": len(hook_turns),
        "exact_hook_turn_identity": exact_hook_turns,
        "event_count": len(events),
    }


def run(*, codex_bin: Path, codex_version: str, home: Path, workspace: Path,
        schema_root: Path, marketplace_root: Path, source_home: Path,
        output: Path) -> dict:
    if output.exists() or home.exists() or workspace.exists():
        raise RuntimeError("fresh-identity-required")
    output.parent.mkdir(parents=True, exist_ok=True)
    version = subprocess.run(
        [str(codex_bin.resolve()), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, check=False,
    ).stdout.strip()
    if version != f"codex-cli {codex_version}":
        raise RuntimeError("pinned-codex-version-mismatch")
    home.mkdir(parents=True)
    workspace.mkdir(parents=True)
    events_dir = output.parent / f"{output.stem}-events"
    events_dir.mkdir()
    fixture = prepare_fixture(workspace, terminal=False)
    provider_route = {}
    env = os.environ.copy()
    env.update({"CODEX_HOME": str(home.resolve()), "DS_LITE_HOOK_ACCEPTANCE_DIR": str(events_dir.resolve()), "PYTHONUTF8": "1"})
    added = subprocess.run(
        [str(codex_bin.resolve()), "plugin", "marketplace", "add", str(marketplace_root.resolve())],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if added.returncode != 0:
        raise RuntimeError("marketplace-add")
    config = home / "config.toml"
    workspace_key = json.dumps(os.path.normcase(os.path.realpath(workspace)))
    with config.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f'\n[projects.{workspace_key}]\ntrust_level = "trusted"\n')
    process, transport, contract = _open_app_server(codex_bin, env, schema_root)
    thread = turn = ""
    terminal = None
    observation = {}
    hooks = {}
    plugin = {}
    plugin_preinstall = {}
    listing_digest = None
    failure = "none"
    try:
        listing = _request(transport, contract, "plugin/list", {"cwds": [str(workspace.resolve())]})
        listing_digest = hashlib.sha256(json.dumps(listing, sort_keys=True).encode()).hexdigest()
        marketplace_path, plugin_preinstall = _plugin_install_target(listing, "deepscientist-lite")
        _request(transport, contract, "plugin/install", {
            "pluginName": "deepscientist-lite", "marketplacePath": marketplace_path
        })
        _stop_app_server(process)
        provider_lines, provider_route = clone_nonsecret_provider_config(source_home.resolve(), home)
        if not provider_route.get("provider_route_copied"):
            raise RuntimeError("nonsecret-provider-route-unavailable")
        provider_lines = [
            line for line in provider_lines
            if not line.startswith(("model = ", "model_reasoning_effort = ", "model_catalog_json = "))
        ]
        provider_route["catalog_used"] = False
        provider_route["model_override_used"] = False
        existing_config = config.read_text(encoding="utf-8")
        config.write_text("\n".join(provider_lines) + "\n" + existing_config, encoding="utf-8", newline="\n")
        process, transport, contract = _open_app_server(codex_bin, env, schema_root)
        _, plugin = _plugin_install_target(
            _request(transport, contract, "plugin/list", {"cwds": [str(workspace.resolve())]}),
            "deepscientist-lite",
        )
        hooks = _hook_summary(_request(transport, contract, "hooks/list", {"cwds": [str(workspace.resolve())]}), "deepscientist-lite")
        thread = _thread_id({"result": _request(transport, contract, "thread/start", {
            "cwd": str(workspace.resolve()),
            "ephemeral": False,
            "developerInstructions": (
                "This is a Hook protocol smoke. Never call tools. After any Hook feedback, "
                "reply with a short acknowledgement and immediately attempt to stop again. "
                "Do not repair or inspect files."
            ),
        })})
        turn = _turn_id({"result": _request(transport, contract, "turn/start", {
            "threadId": thread,
            "input": [{"type": "text", "text": "Do not use tools. State that the bounded check is complete, then stop."}],
        })})
        transport.wait_for_notification(
            "turn/completed",
            lambda item: isinstance(item.get("params"), dict)
            and item["params"].get("threadId") == thread
            and isinstance(item["params"].get("turn"), dict)
            and item["params"]["turn"].get("id") == turn,
            timeout=180.0,
        )
        terminal = _terminal_turn_diagnostic(transport.notifications, thread, turn)
        observation = _event_observation(events_dir, transport.notifications, thread, turn)
        observation["schema_digest"] = _schema_digest(schema_root)
        verified = evaluate_observation(observation, schema_digest=observation["schema_digest"])
        _request(transport, contract, "thread/archive", {"threadId": thread})
        status = verified["status"]
        failure = verified["failure_layer"]
    except Exception as exc:
        status = "blocked"
        failure = str(exc).split(":", 1)[0]
        verified = evaluate_observation({}, schema_digest="unavailable")
    finally:
        if process.poll() is None:
            _stop_app_server(process)
    receipt = {
        "schema_version": "ds-lite.hook-in-turn-repair-smoke.v1",
        "status": status,
        "failure_layer": failure,
        "evidence_class": "real-host" if thread else "host-not-observed",
        "cli_version": codex_version,
        "schema_digest": _schema_digest(schema_root),
        "hook_source_sha256": hashlib.sha256((marketplace_root / "plugins" / "deepscientist-lite-core" / "hooks" / "hooks.json").read_bytes()).hexdigest(),
        "plugin_list_sha256": listing_digest,
        "plugin_preinstall": plugin_preinstall,
        "plugin": plugin,
        "hooks": hooks,
        "fixture": fixture,
        "observation": observation,
        "verifier": verified,
        "turn_terminal": terminal,
        "thread_id_sha256": hashlib.sha256(thread.encode()).hexdigest() if thread else None,
        "turn_id_sha256": hashlib.sha256(turn.encode()).hexdigest() if turn else None,
        "used_last": False,
        "implicit_thread_start_after_failure": False,
        "global_trust_modified": False,
        "credential_value_read_or_copied": False,
        "provider_route": provider_route,
        "isolated_feature_flags": ["hooks"],
        "hook_trust_mode": "isolated-vetted-bypass",
        "persisted_global_hook_trust": False,
        "release_allowed": False,
        "raw_response_persisted": False,
    }
    with output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("codex-bin", "home", "workspace", "schema-root", "marketplace-root", "source-home", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--codex-version", required=True)
    args = parser.parse_args()
    receipt = run(codex_bin=args.codex_bin, codex_version=args.codex_version,
                  home=args.home, workspace=args.workspace,
                  schema_root=args.schema_root, marketplace_root=args.marketplace_root,
                  source_home=args.source_home, output=args.output)
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
