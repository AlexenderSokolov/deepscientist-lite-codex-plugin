#!/usr/bin/env python3
"""Historical Stop-first diagnostic; it cannot prove Hook in-turn repair."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "deepscientist-lite-core" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from ds_lite_recovery import classify_failure

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback is not used by the pinned runner
    tomllib = None


class AppServerProtocolError(RuntimeError):
    """A response-shape failure that must become a redacted terminal receipt."""

    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def _send(process: subprocess.Popen[str], request_id: int, method: str, params: dict) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
    process.stdin.flush()


def _response(process: subprocess.Popen[str], request_id: int) -> dict:
    assert process.stdout is not None
    while line := process.stdout.readline():
        value = json.loads(line)
        if value.get("id") == request_id:
            return value
    raise RuntimeError("app-server closed before the expected response")


def _start_stdout_reader(process: subprocess.Popen[str]) -> queue.Queue[str | None]:
    """Move blocking pipe reads off the protocol deadline path."""
    events: queue.Queue[str | None] = queue.Queue()

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            events.put(line)
        events.put(None)

    threading.Thread(target=read_stdout, name="ds-lite-app-server-reader", daemon=True).start()
    return events


def _next_stdout_event(events: queue.Queue[str | None], deadline: float) -> str | None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return ""
    try:
        return events.get(timeout=min(remaining, 1.0))
    except queue.Empty:
        return ""


def _thread_id(response: dict) -> str:
    result = response.get("result")
    thread = result.get("thread") if isinstance(result, dict) else None
    identifier = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise AppServerProtocolError("thread-start")
    return identifier


def _hook_counts(directory: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            key = f"{value['event_type']}:{value['decision']}"
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _count(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        label = value if isinstance(value, str) and value else "unknown"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _hooks_list_summary(response: dict) -> dict:
    entries = response.get("result", {}).get("data", [])
    if not isinstance(entries, list):
        entries = []
    hooks: list[dict] = []
    error_count = 0
    warning_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_hooks = entry.get("hooks", [])
        if isinstance(entry_hooks, list):
            hooks.extend(item for item in entry_hooks if isinstance(item, dict))
        errors = entry.get("errors", [])
        warnings = entry.get("warnings", [])
        if isinstance(errors, list):
            error_count += len(errors)
        if isinstance(warnings, list):
            warning_count += len(warnings)
    return {
        "entry_count": len(entries),
        "hook_count": len(hooks),
        "error_count": error_count,
        "warning_count": warning_count,
        "event_counts": _count(hooks, "eventName"),
        "enabled_counts": {
            "enabled": sum(1 for item in hooks if item.get("enabled") is True),
            "disabled": sum(1 for item in hooks if item.get("enabled") is False),
            "unknown": sum(1 for item in hooks if not isinstance(item.get("enabled"), bool)),
        },
        "trust_counts": _count(hooks, "trustStatus"),
        "source_counts": _count(hooks, "source"),
        "handler_counts": _count(hooks, "handlerType"),
        "raw_hook_commands_persisted": False,
        "raw_hook_paths_persisted": False,
    }


def _formal_trust_state(response: dict) -> dict[str, dict[str, str]]:
    entries = response.get("result", {}).get("data", [])
    if not isinstance(entries, list):
        return {}
    updates: dict[str, dict[str, str]] = {}
    for entry in entries:
        hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if not isinstance(hook, dict):
                continue
            key = hook.get("key")
            current_hash = hook.get("currentHash")
            if isinstance(key, str) and key and isinstance(current_hash, str) and current_hash:
                updates[key] = {"trusted_hash": current_hash}
    return dict(sorted(updates.items()))


def _error_info(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value:
        key = sorted(value)[0]
        payload = value.get(key)
        status = None
        if isinstance(payload, dict):
            status = payload.get("httpStatusCode")
        if isinstance(status, int):
            return f"{key}:{status // 100}xx"
        return key
    return "unknown"


def _error_diagnostic(error: object) -> dict[str, str]:
    """Return a non-reversible live diagnostic; never persist app-server text."""
    message = error.get("message") if isinstance(error, dict) else ""
    if not isinstance(message, str):
        message = ""
    normalized = message.casefold()
    info = _error_info(error.get("info") if isinstance(error, dict) else None).casefold()
    if info in {"serveroverloaded", "server_overloaded"} or any(token in info for token in ("502", "503", "504")):
        normalized = f"{normalized} transport server overloaded"
    category = next((name for name, marker in (
        ("provider", "provider"), ("authentication", "auth"),
        ("rate-limit", "rate limit"), ("timeout", "timeout"),
        ("hook", "hook"), ("tool", "tool"), ("protocol", "invalid"),
    ) if marker in normalized), "other")
    recovery = classify_failure(category, message=normalized)
    return {
        "category": category,
        "recovery_class": str(recovery["recovery_class"]),
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }


def _configured_model(home: Path) -> str:
    """Use the fresh host's declared model without persisting its config."""
    if tomllib is not None:
        try:
            payload = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
            model = payload.get("model") if isinstance(payload, dict) else None
            if isinstance(model, str) and model.strip():
                return model.strip()
        except (OSError, UnicodeError, ValueError, TypeError):
            pass
    return "gpt-5.6-sol"


def evaluate_stop_first(*, trust_ready: bool, hook_counts: dict[str, int], summary_completed: bool,
                        terminal: str, continuation_observed: bool = False) -> tuple[str, str]:
    """Retire Stop-first external continuation as a non-passing protocol."""
    del trust_ready, hook_counts, summary_completed, terminal, continuation_observed
    return "blocked", "legacy-stop-first-semantics"


def evaluate_session_control(*, trust_ready: bool, hook_counts: dict[str, int], summary_completed: bool,
                             terminal: str, error_count: int) -> tuple[str, str]:
    """Validate the UserPrompt-first foreground conversation-control protocol."""
    prompt_completed = hook_counts.get("user-prompt-submit:allow", 0) > 0
    stop_allow = hook_counts.get("stop:allow", 0) > 0
    if trust_ready and prompt_completed and summary_completed and stop_allow and terminal == "turn/completed" and error_count == 0:
        return "passed", "none"
    return "blocked", "app-server-conversation-control"


def run(codex_bin: Path, home: Path, workspace: Path, hook_events: Path, output: Path, timeout: int,
        plugin_root: Path | None = None, diagnostic: bool = False, show_live_error: bool = False,
        direct_egress: bool = False) -> dict:
    home = home.resolve()
    workspace = workspace.resolve()
    hook_events = hook_events.resolve()
    output = output.resolve()
    if plugin_root is not None:
        plugin_root = plugin_root.resolve()
        if not (plugin_root / "scripts" / "ds_lite_autonomy.py").is_file():
            raise RuntimeError("plugin root does not contain the DS Lite autonomy controller")
    if output.exists():
        raise RuntimeError("refusing to overwrite an acceptance receipt")
    env = os.environ.copy()
    proxy_env_cleared = False
    if direct_egress:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            proxy_env_cleared = env.pop(name, None) is not None or proxy_env_cleared
        # reqwest on Windows may still consult system proxy settings. Make the
        # explicitly authorized direct route unambiguous for this child only.
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"
    env["CODEX_HOME"] = str(home)
    env["DS_LITE_HOOK_ACCEPTANCE_DIR"] = str(hook_events)
    if plugin_root is not None:
        # The Hook child inherits this only to resolve the generated project
        # runner. The local source path is intentionally absent from receipts.
        env["DS_LITE_PLUGIN_ROOT"] = str(plugin_root)
    process = subprocess.Popen(
        [str(codex_bin), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env,
    )
    methods: list[str] = []
    initialized: dict = {}
    thread = ""
    hook_listing: dict = {}
    hook_listing_summary = _hooks_list_summary(hook_listing)
    formal_trust_state: dict[str, dict[str, str]] = {}
    formal_trust_write_observed = False
    post_trust_hooks_list_summary: dict | None = None
    trust_ready = False
    terminal = "precondition"
    error_count = 0
    error_will_retry_count = 0
    error_info_counts: dict[str, int] = {}
    error_recovery_counts: dict[str, int] = {}
    app_server_hook_notifications: dict[str, int] = {}
    continuation_requested = False
    continuation_terminal = "not-requested"
    external_runner_completed = False
    protocol_failure: str | None = None
    protocol_phase: str | None = None
    model = _configured_model(home)
    try:
        _send(process, 1, "initialize", {"clientInfo": {"name": "ds-lite-acceptance", "version": "0.8.1"}})
        initialized = _response(process, 1)
        if not isinstance(initialized.get("result"), dict):
            raise AppServerProtocolError("initialize")
        _send(process, 2, "thread/start", {
            "cwd": str(workspace), "approvalPolicy": "never", "ephemeral": True,
            "model": model, "modelProvider": "custom",
        })
        thread = _thread_id(_response(process, 2))
        _send(process, 3, "hooks/list", {"threadId": thread})
        hook_listing = _response(process, 3)
        hook_listing_summary = _hooks_list_summary(hook_listing)
        formal_trust_state = _formal_trust_state(hook_listing)
        if formal_trust_state:
            _send(process, 4, "config/batchWrite", {
                "edits": [{"keyPath": "hooks.state", "value": formal_trust_state, "mergeStrategy": "upsert"}],
                "reloadUserConfig": True,
            })
            formal_trust_write_observed = "result" in _response(process, 4)
            _send(process, 5, "hooks/list", {"threadId": thread})
            post_trust_hooks_list_summary = _hooks_list_summary(_response(process, 5))
            trust_ready = (
                formal_trust_write_observed
                and post_trust_hooks_list_summary["hook_count"] == len(formal_trust_state)
                and post_trust_hooks_list_summary["trust_counts"].get("trusted") == len(formal_trust_state)
            )
        if trust_ready:
            _send(process, 6, "turn/start", {
                "threadId": thread, "cwd": str(workspace), "approvalPolicy": "never",
                "model": model, "modelProvider": "custom",
                "input": [{"type": "text", "text": "End now."}],
            })
            deadline = time.monotonic() + timeout
            terminal = "timeout"
            stdout_events = _start_stdout_reader(process)
            while time.monotonic() < deadline:
                line = _next_stdout_event(stdout_events, deadline)
                if line is None:
                    terminal = "closed"
                    break
                if not line:
                    continue
                value = json.loads(line)
                method = value.get("method")
                if isinstance(method, str):
                    methods.append(method)
                    if method == "error":
                        error_count += 1
                        params = value.get("params", {})
                        if isinstance(params, dict):
                            if params.get("willRetry") is True:
                                error_will_retry_count += 1
                            error = params.get("error", {})
                            if isinstance(error, dict):
                                info = _error_info(error.get("codexErrorInfo"))
                                error_info_counts[info] = error_info_counts.get(info, 0) + 1
                                recovery_class = _error_diagnostic(error)["recovery_class"]
                                error_recovery_counts[recovery_class] = error_recovery_counts.get(recovery_class, 0) + 1
                                if diagnostic:
                                    print(json.dumps({"diagnostic": _error_diagnostic(error)}, ensure_ascii=True))
                                if show_live_error:
                                    message = error.get("message")
                                    if isinstance(message, str):
                                        print(json.dumps({"live_error_message": message}, ensure_ascii=False))
                    if method in {"hook/started", "hook/completed"}:
                        params = value.get("params", {})
                        event = "unknown"
                        status = "unknown"
                        if isinstance(params, dict):
                            run_summary = params.get("run", {})
                            if isinstance(run_summary, dict):
                                if isinstance(run_summary.get("eventName"), str):
                                    event = run_summary["eventName"]
                                if isinstance(run_summary.get("status"), str):
                                    status = run_summary["status"]
                        key = f"{method}:{event}:{status}"
                        app_server_hook_notifications[key] = app_server_hook_notifications.get(key, 0) + 1
                if method in {"turn/completed", "turn/failed"}:
                    terminal = method
                    break
        hooks = _hook_counts(hook_events)
        summary = workspace / "research" / "autonomy" / "run" / "summary.json"
        completion = False
        if summary.is_file():
            try:
                completion = json.loads(summary.read_text(encoding="utf-8")).get("status") == "completed"
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        status, failure = evaluate_stop_first(
            trust_ready=trust_ready, hook_counts=hooks,
            summary_completed=completion, terminal=terminal,
            continuation_observed=(
                continuation_requested and external_runner_completed and continuation_terminal == "turn/completed"
            ),
        )
        receipt = {
            "schema_version": "ds-lite.legacy-stop-first-continuation.v1", "status": status,
            "failure_layer": failure, "terminal": terminal, "method_sequence": methods,
            "hook_event_counts": hooks, "autonomy_summary_completed": completion,
            "thread_id_sha256": hashlib.sha256(thread.encode()).hexdigest(),
            "app_server_user_agent": initialized.get("result", {}).get("userAgent", "unknown"),
            "hooks_list_observed": "result" in hook_listing,
            "hooks_list_summary": hook_listing_summary,
            "formal_trust_update_requested_count": len(formal_trust_state),
            "formal_trust_write_observed": formal_trust_write_observed,
            "post_trust_hooks_list_summary": post_trust_hooks_list_summary,
            "app_server_hook_notifications": dict(sorted(app_server_hook_notifications.items())),
            "continuation_requested": continuation_requested,
            "continuation_terminal": continuation_terminal,
            "external_runner_completed": external_runner_completed,
            "protocol_error_phase": protocol_phase,
            "error_notification_count": error_count,
            "error_will_retry_count": error_will_retry_count,
            "error_info_counts": dict(sorted(error_info_counts.items())),
            "error_recovery_counts": dict(sorted(error_recovery_counts.items())),
            "direct_egress_requested": direct_egress,
            "proxy_env_cleared": proxy_env_cleared,
            "no_proxy_forced": direct_egress,
            "raw_output_persisted": False,
            "raw_error_text_persisted": False,
        }
    except (AppServerProtocolError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        # The exact transport error is intentionally never persisted.
        protocol_failure = "app-server-response-error"
        protocol_phase = getattr(exc, "phase", "transport")
        terminal = "response-error"
        status = "blocked"
        failure = protocol_failure
        hooks = _hook_counts(hook_events)
        receipt = {
            "schema_version": "ds-lite.legacy-stop-first-continuation.v1", "status": status,
            "failure_layer": failure, "terminal": terminal, "method_sequence": methods,
            "hook_event_counts": hooks, "autonomy_summary_completed": False,
            "thread_id_sha256": hashlib.sha256(thread.encode()).hexdigest() if thread else None,
            "app_server_user_agent": initialized.get("result", {}).get("userAgent", "unknown") if isinstance(initialized.get("result"), dict) else "unknown",
            "hooks_list_observed": "result" in hook_listing,
            "hooks_list_summary": hook_listing_summary,
            "formal_trust_update_requested_count": len(formal_trust_state),
            "formal_trust_write_observed": formal_trust_write_observed,
            "post_trust_hooks_list_summary": post_trust_hooks_list_summary,
            "app_server_hook_notifications": dict(sorted(app_server_hook_notifications.items())),
            "continuation_requested": continuation_requested,
            "continuation_terminal": continuation_terminal,
            "external_runner_completed": external_runner_completed,
            "protocol_error_phase": protocol_phase,
            "error_notification_count": error_count,
            "error_will_retry_count": error_will_retry_count,
            "error_info_counts": dict(sorted(error_info_counts.items())),
            "error_recovery_counts": dict(sorted(error_recovery_counts.items())),
            "direct_egress_requested": direct_egress,
            "proxy_env_cleared": proxy_env_cleared,
            "no_proxy_forced": direct_egress,
            "raw_output_persisted": False,
            "raw_error_text_persisted": False,
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--hook-events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--plugin-root", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=150)
    parser.add_argument("--diagnostic", action="store_true", help="Print a non-reversible live error category; never write it to the receipt.")
    parser.add_argument("--show-live-error", action="store_true", help="Print the current app-server error message only; never write it to the receipt.")
    parser.add_argument("--direct-egress", action="store_true", help="Bypass inherited proxy variables for this explicitly authorized host run.")
    args = parser.parse_args()
    receipt = run(args.codex_bin, args.home, args.workspace, args.hook_events, args.output, args.timeout,
                  plugin_root=args.plugin_root, diagnostic=args.diagnostic, show_live_error=args.show_live_error,
                  direct_egress=args.direct_egress)
    print(json.dumps({"status": receipt["status"], "failure_layer": receipt["failure_layer"]}, ensure_ascii=True))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
