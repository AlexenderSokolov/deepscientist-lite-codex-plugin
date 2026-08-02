"""Small schema-bound JSON-RPC transport for the Codex app-server."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Protocol


class _TextProcess(Protocol):
    stdin: Any
    stdout: Any


class AppServerProtocolError(RuntimeError):
    """The app-server exchange violated the pinned transport contract."""


class AppServerClosed(RuntimeError):
    """The process closed stdout before the requested response arrived."""


class AppServerResponseTimeout(RuntimeError):
    """The pinned app-server did not answer before the request deadline."""


def validate_params(method: str, params: dict[str, Any], contract: dict[str, dict[str, list[str]]]) -> None:
    """Reject guessed RPC fields before anything reaches the host."""
    specification = contract.get(method)
    if specification is None:
        raise AppServerProtocolError(f"method-not-pinned:{method}")
    required = specification.get("required", [])
    properties = specification.get("properties", [])
    missing = sorted(name for name in required if name not in params)
    unknown = sorted(name for name in params if name not in properties)
    if missing:
        raise AppServerProtocolError(f"required-field-missing:{','.join(missing)}")
    if unknown:
        raise AppServerProtocolError(f"unrecognized-field:{','.join(unknown)}")


class JsonRpcTransport:
    """One-request-at-a-time transport that preserves early notifications."""

    def __init__(self, process: _TextProcess, *, response_timeout: float = 30.0) -> None:
        if response_timeout <= 0:
            raise ValueError("response_timeout must be positive")
        self.process = process
        self.response_timeout = response_timeout
        self.next_request_id = 1
        self.notifications: list[dict[str, Any]] = []
        self.malformed_message_count = 0
        self.unmatched_response_count = 0
        self._lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read_stdout, name="ds-lite-app-server-stdout", daemon=True).start()

    def _read_stdout(self) -> None:
        while True:
            line = self.process.stdout.readline()
            self._lines.put(line)
            if line == "":
                return

    def notify(self, method: str, allowed_methods: set[str]) -> None:
        if method not in allowed_methods:
            raise AppServerProtocolError(f"notification-not-pinned:{method}")
        self.process.stdin.write(json.dumps({"method": method}) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self.next_request_id
        self.next_request_id += 1
        self.process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + self.response_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AppServerResponseTimeout("app-server-response-timeout")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise AppServerResponseTimeout("app-server-response-timeout") from exc
            if line == "":
                raise AppServerClosed("app-server-closed")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.malformed_message_count += 1
                continue
            if not isinstance(message, dict):
                self.malformed_message_count += 1
                continue
            if "method" in message and "id" not in message:
                self.notifications.append(message)
                continue
            if message.get("id") == request_id:
                return message
            self.unmatched_response_count += 1

    def wait_for_notification(self, method: str, predicate: Any, *, timeout: float) -> dict[str, Any] | None:
        """Wait for one pinned notification without issuing another host action."""
        for notification in self.notifications:
            if notification.get("method") == method and predicate(notification):
                return notification
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                return None
            if line == "":
                raise AppServerClosed("app-server-closed")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.malformed_message_count += 1
                continue
            if not isinstance(message, dict):
                self.malformed_message_count += 1
                continue
            if "method" in message and "id" not in message:
                self.notifications.append(message)
                if message.get("method") == method and predicate(message):
                    return message
                continue
            self.unmatched_response_count += 1

def classify_thread_observation(*, thread_id: str, response: dict[str, Any] | None,
                                notifications: list[dict[str, Any]]) -> str:
    """Classify facts without issuing a second thread or turn request."""
    for notification in reversed(notifications):
        params = notification.get("params")
        if not isinstance(params, dict) or params.get("threadId") != thread_id:
            continue
        if notification.get("method") in {"turn/completed", "turn/failed"}:
            return "terminal"
        if notification.get("method") in {"thread/started", "turn/started"}:
            return "active"
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        thread = response["result"].get("thread")
        if isinstance(thread, dict) and thread.get("id") == thread_id:
            return "active"
    return "ambiguous"
