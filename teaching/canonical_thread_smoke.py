"""Schema-bound canonical thread lifecycle smoke; never uses --last."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from teaching.app_server_transport import AppServerClosed, JsonRpcTransport, validate_params


METHODS = {
    "thread/start": "ThreadStartParams",
    "thread/resume": "ThreadResumeParams",
    "thread/list": "ThreadListParams",
    "thread/read": "ThreadReadParams",
    "thread/archive": "ThreadArchiveParams",
    "thread/unarchive": "ThreadUnarchiveParams",
    "turn/start": "TurnStartParams",
    "turn/interrupt": "TurnInterruptParams",
}
PARAM_SCHEMAS = {"initialize": "v1/InitializeParams.json"} | {
    method: f"v2/{name}.json" for method, name in METHODS.items()
}


def app_server_command(codex_bin: Path) -> list[str]:
    if os.name == "nt" and codex_bin.suffix.casefold() == ".cmd":
        return ["cmd.exe", "/d", "/s", "/c", f'"{codex_bin}" app-server']
    return [str(codex_bin), "app-server"]


def schema_contract(schema_root: Path) -> dict[str, dict]:
    root = schema_root / "v2"
    contract: dict[str, dict] = {}
    for filename in METHODS.values():
        payload = json.loads((root / f"{filename}.json").read_text(encoding="utf-8"))
        contract[filename] = {
            "required": payload.get("required", []),
            "properties": sorted(payload.get("properties", {})),
        }
    return contract


def rpc_contract(schema_root: Path) -> dict[str, dict]:
    contract: dict[str, dict] = {}
    for method, relative in PARAM_SCHEMAS.items():
        payload = json.loads((schema_root / relative).read_text(encoding="utf-8"))
        contract[method] = {
            "required": payload.get("required", []),
            "properties": sorted(payload.get("properties", {})),
        }
    return contract


def client_notification_methods(schema_root: Path) -> set[str]:
    payload = json.loads((schema_root / "ClientNotification.json").read_text(encoding="utf-8"))
    methods: set[str] = set()
    for variant in payload.get("oneOf", []):
        values = variant.get("properties", {}).get("method", {}).get("enum", [])
        methods.update(value for value in values if isinstance(value, str))
    return methods


def _thread_id(response: dict) -> str:
    thread = response.get("result", {}).get("thread") if isinstance(response.get("result"), dict) else None
    identifier = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise RuntimeError("thread-id-missing")
    return identifier


def _turn_id(response: dict) -> str:
    turn = response.get("result", {}).get("turn") if isinstance(response.get("result"), dict) else None
    identifier = turn.get("id") if isinstance(turn, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise RuntimeError("turn-id-missing")
    return identifier


def _terminal_turn_diagnostic(notifications: list[dict], thread_id: str, turn_id: str) -> dict | None:
    for notification in reversed(notifications):
        if notification.get("method") != "turn/completed":
            continue
        params = notification.get("params")
        turn = params.get("turn") if isinstance(params, dict) else None
        if not isinstance(params, dict) or params.get("threadId") != thread_id or not isinstance(turn, dict):
            continue
        if turn.get("id") != turn_id:
            continue
        error = turn.get("error")
        info = error.get("codexErrorInfo") if isinstance(error, dict) else None
        if isinstance(info, str):
            error_class = info
        elif isinstance(info, dict) and info:
            error_class = sorted(info)[0]
        else:
            error_class = None
        message = error.get("message") if isinstance(error, dict) else ""
        message = message if isinstance(message, str) else ""
        lowered = message.casefold()
        message_class = "other"
        for category, needles in (
            ("authentication", ("auth", "api key", "401", "credential")),
            ("model-config", ("model", "catalog", "404")),
            ("rate-limit", ("429", "rate limit")),
            ("network", ("network", "connect", "dns", "timeout", "stream")),
        ):
            if any(needle in lowered for needle in needles):
                message_class = category
                break
        return {
            "status": turn.get("status"),
            "error_class": error_class,
            "error_message_class": message_class,
            "error_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest() if message else None,
        }
    return None


def _response_observation(method: str, response: dict, thread_id: str) -> tuple[str, dict | None]:
    if "result" not in response:
        error = response.get("error")
        if not isinstance(error, dict):
            return "response-gap", {"error_shape": "missing"}
        message = error.get("message")
        message = message if isinstance(message, str) else ""
        return "response-gap", {
            "error_code": error.get("code") if isinstance(error.get("code"), int) else None,
            "error_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            "error_data_keys": sorted(error.get("data", {})) if isinstance(error.get("data"), dict) else [],
        }
    if method == "thread/list":
        data = response.get("result", {}).get("data") if isinstance(response.get("result"), dict) else None
        found = isinstance(data, list) and any(
            isinstance(item, dict) and item.get("id") == thread_id for item in data
        )
        return ("observed", None) if found else ("identity-gap", None)
    if method in {"thread/read", "thread/resume"}:
        try:
            found = _thread_id(response) == thread_id
        except RuntimeError:
            found = False
        return ("observed", None) if found else ("identity-gap", None)
    return "observed", None


def run(codex_bin: Path, home: Path, workspace: Path, schema_root: Path, output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise RuntimeError("refusing to overwrite smoke receipt")
    home = home.resolve()
    home.mkdir(parents=True, exist_ok=False)
    contract = schema_contract(schema_root)
    transport_contract = rpc_contract(schema_root)
    notification_methods = client_notification_methods(schema_root)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    process = subprocess.Popen(
        app_server_command(codex_bin.resolve()),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", env=env,
    )
    observed: dict[str, str] = {}
    method_diagnostics: dict[str, dict] = {}
    thread = ""
    turn = ""
    terminal_diagnostic: dict | None = None
    transport: JsonRpcTransport | None = None
    try:
        transport = JsonRpcTransport(process)
        initialize_params = {"clientInfo": {"name": "ds-lite-control-plane", "version": "0.8.1"}}
        validate_params("initialize", initialize_params, transport_contract)
        initialize = transport.request("initialize", initialize_params)
        if "result" not in initialize:
            raise RuntimeError("initialize")
        transport.notify("initialized", notification_methods)
        start_params = {"cwd": str(workspace.resolve()), "ephemeral": False}
        validate_params("thread/start", start_params, transport_contract)
        start = transport.request("thread/start", start_params)
        thread = _thread_id(start)
        observed["thread/start"] = "observed"
        turn_params = {
            "threadId": thread,
            "input": [{
                "type": "text",
                "text": "DS Lite Phase 0.5 lifecycle persistence probe. Return OK without tools.",
            }],
        }
        validate_params("turn/start", turn_params, transport_contract)
        turn_start = transport.request("turn/start", turn_params)
        turn = _turn_id(turn_start)
        observed["turn/start"] = "observed"
        transport.wait_for_notification(
            "turn/completed",
            lambda notification: (
                isinstance(notification.get("params"), dict)
                and notification["params"].get("threadId") == thread
                and isinstance(notification["params"].get("turn"), dict)
                and notification["params"]["turn"].get("id") == turn
            ),
            timeout=120.0,
        )
        interrupt_params = {"threadId": thread, "turnId": turn}
        validate_params("turn/interrupt", interrupt_params, transport_contract)
        interrupt = transport.request("turn/interrupt", interrupt_params)
        interrupt_status, diagnostic = _response_observation("turn/interrupt", interrupt, thread)
        observed["turn/interrupt"] = interrupt_status
        if diagnostic is not None:
            method_diagnostics["turn/interrupt"] = diagnostic
        sequence = (
            ("thread/list", {"limit": 5}),
            ("thread/read", {"threadId": thread, "includeTurns": True}),
            ("thread/archive", {"threadId": thread}),
            ("thread/unarchive", {"threadId": thread}),
            ("thread/resume", {"threadId": thread, "cwd": str(workspace.resolve()), "excludeTurns": True}),
        )
        for method, params in sequence:
            validate_params(method, params, transport_contract)
            response = transport.request(method, params)
            status_value, diagnostic = _response_observation(method, response, thread)
            observed[method] = status_value
            if diagnostic is not None:
                method_diagnostics[method] = diagnostic
        terminal_diagnostic = _terminal_turn_diagnostic(transport.notifications, thread, turn)
        if observed.get("turn/interrupt") != "observed" and terminal_diagnostic is not None:
            observed["turn/interrupt"] = "observed"
            method_diagnostics.setdefault("turn/interrupt", {})["disposition"] = "terminal-before-interrupt"
        cleanup_params = {"threadId": thread}
        validate_params("thread/archive", cleanup_params, transport_contract)
        cleanup = transport.request("thread/archive", cleanup_params)
        cleanup_status, cleanup_diagnostic = _response_observation("thread/archive", cleanup, thread)
        observed["thread/final-archive"] = cleanup_status
        if cleanup_diagnostic is not None:
            method_diagnostics["thread/final-archive"] = cleanup_diagnostic
        status = "passed" if all(value == "observed" for value in observed.values()) else "blocked"
        failure = "none" if status == "passed" else "app-server-response-gap"
    except (AppServerClosed, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        status = "blocked"
        failure = str(exc).split(":", 1)[0]
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    receipt = {
        "schema_version": "ds-lite.canonical-thread-smoke.v1",
        "status": status,
        "failure_layer": failure,
        "evidence_class": "real-app-server" if thread else "app-server-not-observed",
        "schema_sha256": hashlib.sha256((schema_root / "SHA256SUMS").read_bytes()).hexdigest(),
        "schema_contract": contract,
        "client_notification_methods": sorted(notification_methods),
        "initialized_notification_sent": "initialized" in notification_methods,
        "methods": observed,
        "method_diagnostics": method_diagnostics,
        "thread_id_sha256": hashlib.sha256(thread.encode("utf-8")).hexdigest() if thread else None,
        "turn_id_sha256": hashlib.sha256(turn.encode("utf-8")).hexdigest() if turn else None,
        "controller_turn_start_count": 1 if turn else 0,
        "turn_terminal": terminal_diagnostic,
        "used_last": False,
        "implicit_thread_start_after_resume_failure": False,
        "raw_response_persisted": False,
        "notification_count": len(transport.notifications) if transport is not None else 0,
        "malformed_message_count": transport.malformed_message_count if transport is not None else 0,
        "unmatched_response_count": transport.unmatched_response_count if transport is not None else 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--schema-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    receipt = run(args.codex_bin, args.home, args.workspace, args.schema_root, args.output)
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
